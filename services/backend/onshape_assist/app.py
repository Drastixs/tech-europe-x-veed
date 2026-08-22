from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ValidationError

from onshape_assist.analysis import fal
from onshape_assist.analysis.models import AnalysisRequest, AnalysisResult
from onshape_assist.analysis.pipeline import AnalysisError, analyze_video_async

from .contracts import (
    CONTRACT_VERSION,
    RuntimePreferences,
    RuntimeSession,
    RuntimeStateSnapshot,
    TutorialPlan,
    Voice,
)
from .config import load_backend_env
from .launcher_page import render_launcher_page
from .narration import (
    NarrationConfigurationError,
    NarrationError,
    enrich_plan_narration,
)
from .onshape import (
    OnshapeClient,
    OnshapeError,
    OnshapeSnapshot,
    OnshapeTarget,
    RestoreResult,
    ValidationResult,
)
from .planner import OpenAIPlanner, PlannerError, error_envelope

Direction = Literal["left", "right"]
CommandType = Literal[
    "show",
    "hide",
    "move",
    "click",
    "navigate",
    "load_tutorial",
    "arm_takeover",
    "disarm_takeover",
]


class TutorialPlanningRequest(BaseModel):
    video_analysis: dict[str, Any]
    tutorial_id: str = Field(min_length=1)
    application: str = Field(default="Onshape", min_length=1)
    output_language: str = Field(default="en", min_length=1)
    runtime_preferences: RuntimePreferences = Field(
        default_factory=lambda: RuntimePreferences(detailed_narration=False)
    )
    voice: Voice
    step: Annotated[int, Field(ge=1)] = 1


class TutorialFromVideoRequest(AnalysisRequest):
    """One-call handoff from a tutorial video to a relayed tutorial plan."""

    tutorial_id: str = Field(min_length=1)
    runtime_preferences: RuntimePreferences = Field(
        default_factory=lambda: RuntimePreferences(detailed_narration=False)
    )
    voice: Voice = Field(
        default_factory=lambda: Voice(
            provider="fal_elevenlabs",
            voice_id="Rachel",
            speaking_rate=1.0,
        )
    )
    step: Annotated[int, Field(ge=1)] = 1


class RestoreRequest(BaseModel):
    baseline: OnshapeSnapshot
    expected_microversion_id: str = Field(min_length=1)


class ValidationRequest(BaseModel):
    baseline: OnshapeSnapshot
    expected_feature_type: str = Field(min_length=1)
    expected_microversion_id: str | None = None


class DocumentUrlRequest(BaseModel):
    document_url: str = Field(min_length=1)


class DemoCommand(BaseModel):
    type: CommandType
    x: Annotated[int | None, Field(ge=0)] = None
    y: Annotated[int | None, Field(ge=0)] = None
    duration_ms: Annotated[int | None, Field(ge=0, le=10_000)] = None
    direction: Direction | None = None
    plan: TutorialPlan | None = None
    step: Annotated[int | None, Field(ge=1)] = None
    runtime_session: RuntimeSession | None = None


class DemoEnvelope(BaseModel):
    version: Literal[1] = 1
    sequence: int
    sent_at: str
    command: DemoCommand


class Relay:
    def __init__(self) -> None:
        self._sequence = 0
        self._clients: set[WebSocket] = set()
        self.last_envelope: DemoEnvelope | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        if self.last_envelope:
            await websocket.send_json(self.last_envelope.model_dump())

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def publish(self, command: DemoCommand) -> DemoEnvelope:
        self._sequence += 1
        envelope = DemoEnvelope(
            sequence=self._sequence,
            sent_at=datetime.now(UTC).isoformat(),
            command=command,
        )
        self.last_envelope = envelope
        disconnected: list[WebSocket] = []
        for client in self._clients:
            try:
                await client.send_json(envelope.model_dump())
            except RuntimeError:
                disconnected.append(client)
        for client in disconnected:
            self.disconnect(client)
        return envelope

    @property
    def client_count(self) -> int:
        return len(self._clients)


relay = Relay()

PlannerFactory = Callable[[], OpenAIPlanner]
NarrationEnricher = Callable[[TutorialPlan], Awaitable[TutorialPlan]]


planner_factory: PlannerFactory = OpenAIPlanner
narration_enricher: NarrationEnricher = enrich_plan_narration


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.relay = relay
    yield


app = FastAPI(title="Onshape Assist Relay", version="0.1.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def launcher_home() -> HTMLResponse:
    project_dir = Path(__file__).resolve().parents[3]
    extension_dir = project_dir / "apps" / "extension" / ".output" / "chrome-mv3"
    return HTMLResponse(render_launcher_page(extension_dir))


@app.get("/health")
async def health() -> dict[str, int | str]:
    return {"status": "ok", "clients": relay.client_count}


@app.post("/onshape/baselines", response_model=OnshapeSnapshot)
async def capture_onshape_baseline(target: OnshapeTarget) -> OnshapeSnapshot:
    return _with_onshape_client(lambda client: client.snapshot(target))


@app.post("/onshape/baselines/from-url", response_model=OnshapeSnapshot)
async def capture_onshape_baseline_from_url(request: DocumentUrlRequest) -> OnshapeSnapshot:
    try:
        target = OnshapeTarget.from_document_url(request.document_url)
    except OnshapeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _with_onshape_client(lambda client: client.snapshot(target))


@app.post("/onshape/restores", response_model=RestoreResult)
async def restore_onshape_baseline(request: RestoreRequest) -> RestoreResult:
    return _with_onshape_client(
        lambda client: client.restore_baseline(
            request.baseline,
            expected_microversion_id=request.expected_microversion_id,
        )
    )


@app.post("/onshape/validations", response_model=ValidationResult)
async def validate_onshape_attempt(request: ValidationRequest) -> ValidationResult:
    return _with_onshape_client(
        lambda client: client.validate_attempt(
            request.baseline,
            expected_feature_type=request.expected_feature_type,
            expected_microversion_id=request.expected_microversion_id,
        )
    )


@app.post("/commands", response_model=DemoEnvelope)
async def command(command: DemoCommand) -> DemoEnvelope:
    try:
        normalized = normalize_command(command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await relay.publish(normalized)


@app.post("/analyze", response_model=AnalysisResult)
async def analyze(
    request: AnalysisRequest,
    gemini_model: str = fal.DEFAULT_GEMINI_MODEL,
    enrichment: bool = True,
) -> AnalysisResult:
    return await _analyze_video(
        request,
        gemini_model=gemini_model,
        enrichment=enrichment,
    )


@app.post("/tutorials/from-video", response_model=DemoEnvelope)
async def tutorial_from_video(
    request: TutorialFromVideoRequest,
    gemini_model: str = fal.DEFAULT_GEMINI_MODEL,
    enrichment: bool = True,
) -> DemoEnvelope:
    """Analyze a video, plan it, generate narration, and relay the completed tutorial."""
    analysis_request = AnalysisRequest.model_validate(request.model_dump())
    analysis = await _analyze_video(
        analysis_request,
        gemini_model=gemini_model,
        enrichment=enrichment,
    )
    return await _plan_tutorial(
        TutorialPlanningRequest(
            video_analysis=analysis.model_dump(exclude_none=True),
            tutorial_id=request.tutorial_id,
            application=request.application,
            output_language=request.output_language,
            runtime_preferences=request.runtime_preferences,
            voice=request.voice,
            step=request.step,
        )
    )


async def _analyze_video(
    request: AnalysisRequest,
    *,
    gemini_model: str,
    enrichment: bool,
) -> AnalysisResult:
    load_backend_env()
    if not os.environ.get("FAL_KEY"):
        raise HTTPException(status_code=503, detail="FAL_KEY is not configured on the server")
    try:
        return await analyze_video_async(
            request,
            gemini_model=gemini_model,
            with_enrichment=enrichment,
        )
    except AnalysisError as exc:
        raise HTTPException(status_code=422, detail=exc.detail or str(exc)) from exc


@app.post("/tutorials/plan", response_model=DemoEnvelope)
async def plan_tutorial(request: TutorialPlanningRequest) -> DemoEnvelope:
    return await _plan_tutorial(request)


async def _plan_tutorial(request: TutorialPlanningRequest) -> DemoEnvelope:
    planning_input = {
        "video_analysis": request.video_analysis,
        "tutorial_metadata": {
            "tutorial_id": request.tutorial_id,
            "application": request.application,
            "output_language": request.output_language,
            "runtime_preferences": request.runtime_preferences.model_dump(),
            "voice": request.voice.model_dump(),
        },
    }
    try:
        generated = await planner_factory().generate(
            input_payload=planning_input,
            schema=TutorialPlan.model_json_schema(),
        )
        plan = TutorialPlan.model_validate(generated)
    except PlannerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.envelope()) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=error_envelope(
                "contract_validation_failed",
                "OpenAI generated a tutorial plan that failed contract validation",
            ),
        ) from exc

    # Request metadata is authoritative even if the model tried to alter it.
    plan = plan.model_copy(
        update={
            "tutorial_id": request.tutorial_id,
            "application": request.application,
            "output_language": request.output_language,
            "runtime_preferences": request.runtime_preferences,
            "voice": request.voice,
        }
    )
    # Planner-provided asset URLs are untrusted placeholders. Always synthesize
    # both variants so a plausible-looking model URL cannot bypass TTS.
    for tutorial_step in plan.steps:
        for variant_name in ("concise", "detailed"):
            variant = getattr(tutorial_step.narration, variant_name)
            variant.fal_elevenlabs_audio_url = (
                f"pending://tts/{tutorial_step.step_id}/{variant_name}"
            )
            variant.duration_ms = 0
    try:
        enriched = TutorialPlan.model_validate(await narration_enricher(plan))
    except NarrationConfigurationError as exc:
        raise HTTPException(
            status_code=503, detail=error_envelope("narration_configuration_error", str(exc))
        ) from exc
    except NarrationError as exc:
        raise HTTPException(
            status_code=502, detail=error_envelope("narration_error", str(exc))
        ) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=error_envelope(
                "narration_contract_validation_failed",
                "Narration enrichment produced an invalid tutorial plan",
            ),
        ) from exc

    active_step = enriched.steps[request.step - 1]
    session_id = f"{enriched.tutorial_id}:{uuid4()}"
    runtime_session = RuntimeSession(
        contract_version=CONTRACT_VERSION,
        session_id=session_id,
        state_snapshot=RuntimeStateSnapshot(
            session_id=session_id,
            tutorial_id=enriched.tutorial_id,
            step_id=active_step.step_id,
            state="waiting",
            sequence=0,
        ),
    )
    command = DemoCommand(
        type="load_tutorial", plan=enriched, step=request.step, runtime_session=runtime_session
    )
    try:
        normalized = normalize_command(command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await relay.publish(normalized)


@app.websocket("/ws/extension")
async def extension_socket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    allowed_origin = (
        origin is None
        or origin == "https://cad.onshape.com"
        or origin.startswith("chrome-extension://")
    )
    if not allowed_origin:
        await websocket.close(code=1008, reason="Origin not allowed")
        return
    await relay.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        relay.disconnect(websocket)


def normalize_command(command: DemoCommand) -> DemoCommand:
    if command.type == "move" and (command.x is None or command.y is None):
        raise ValueError("move requires x and y")
    if command.type == "navigate" and command.direction is None:
        raise ValueError("navigate requires direction")
    if command.type == "load_tutorial":
        if command.plan is None:
            raise ValueError("load_tutorial requires a plan")
        if command.step is not None and command.step > len(command.plan.steps):
            raise ValueError("load_tutorial step exceeds the number of steps")
        if command.runtime_session is not None:
            if command.runtime_session.state_snapshot.tutorial_id != command.plan.tutorial_id:
                raise ValueError("runtime session must reference the loaded tutorial")
            step_ids = {step.step_id for step in command.plan.steps}
            if command.runtime_session.state_snapshot.step_id not in step_ids:
                raise ValueError("runtime session must reference a loaded tutorial step")
            if any(event.tutorial_id != command.plan.tutorial_id for event in command.runtime_session.runtime_events):
                raise ValueError("runtime events must reference the loaded tutorial")
            if any(event.step_id not in step_ids for event in command.runtime_session.runtime_events):
                raise ValueError("runtime events must reference a loaded tutorial step")
    return command


def _with_onshape_client(operation: Callable[[OnshapeClient], Any]) -> Any:
    try:
        client = OnshapeClient.from_env()
    except OnshapeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return operation(client)
    except OnshapeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        client.close()
