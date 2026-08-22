from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from onshape_assist.analysis import fal
from onshape_assist.analysis.models import AnalysisRequest, AnalysisResult
from onshape_assist.analysis.pipeline import AnalysisError, analyze_video_async

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
from .planner import OpenAIPlanner, PlannerError

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


class TutorialContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimePreferences(TutorialContractModel):
    detailed_narration: bool


class Voice(TutorialContractModel):
    provider: Literal["fal_elevenlabs"]
    voice_id: str = Field(min_length=1)
    speaking_rate: Annotated[float, Field(gt=0)]


class TutorialAction(TutorialContractModel):
    sequence: Annotated[int, Field(ge=1)]
    action_type: Literal[
        "move",
        "click",
        "double_click",
        "drag",
        "keypress",
        "type",
        "scroll",
        "wait",
        "selection",
    ]
    ui_region: str = Field(min_length=1)
    target_label: str | None
    target_description: str = Field(min_length=1)
    semantic_action: str = Field(min_length=1)
    expected_visible_result: str = Field(min_length=1)
    preferred_activation: Literal["dom_js", "cdp", "vision_only"]
    fallback_activation: Literal["cdp"] | None


class NarrationVariant(TutorialContractModel):
    text: str = Field(min_length=1)
    fal_elevenlabs_audio_url: str = Field(min_length=1)
    duration_ms: Annotated[int, Field(ge=0)]


class Narration(TutorialContractModel):
    concise: NarrationVariant
    detailed: NarrationVariant


class VoiceCue(TutorialContractModel):
    cue_id: str = Field(min_length=1)
    phase: Literal[
        "before_step",
        "before_action",
        "during_action",
        "after_action",
        "after_step",
        "on_retry",
        "on_user_interrupt",
    ]
    action_sequence: Annotated[int, Field(ge=1)]
    variant: Literal["concise", "detailed", "both"]
    text_ref: str = Field(min_length=1)
    start_policy: Literal[
        "play_before_motion",
        "play_with_motion",
        "play_after_validation",
        "play_on_event",
    ]
    blocking: bool


class DynamicCorrections(TutorialContractModel):
    retry: str = Field(min_length=1)
    validation_failed: str = Field(min_length=1)
    user_interrupt: str = Field(min_length=1)


class TutorialStep(TutorialContractModel):
    step_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    preconditions: list[str]
    actions: Annotated[list[TutorialAction], Field(min_length=1)]
    narration: Narration
    voice_cues: Annotated[list[VoiceCue], Field(min_length=1)]
    dynamic_corrections: DynamicCorrections
    expected_end_state: str = Field(min_length=1)
    uncertainties: list[str]

    @model_validator(mode="after")
    def validate_action_sequence_and_cues(self) -> TutorialStep:
        sequences = [action.sequence for action in self.actions]
        expected = list(range(1, len(self.actions) + 1))
        if sequences != expected:
            raise ValueError("tutorial action sequences must be contiguous and ordered from 1")
        if any(cue.action_sequence not in sequences for cue in self.voice_cues):
            raise ValueError("voice cue action_sequence must reference an action in its step")
        return self


class TutorialPlan(TutorialContractModel):
    tutorial_id: str = Field(min_length=1)
    application: str = Field(min_length=1)
    output_language: str = Field(min_length=1)
    runtime_preferences: RuntimePreferences
    voice: Voice
    steps: Annotated[list[TutorialStep], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_unique_step_ids(self) -> TutorialPlan:
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("tutorial step_id values must be unique")
        return self


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
    if not os.environ.get("FAL_KEY"):
        raise HTTPException(status_code=503, detail="FAL_KEY is not configured on the server")
    try:
        return await analyze_video_async(
            request,
            gemini_model=gemini_model,
            with_enrichment=enrichment,
        )
    except AnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/tutorials/plan", response_model=DemoEnvelope)
async def plan_tutorial(request: TutorialPlanningRequest) -> DemoEnvelope:
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
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail="OpenAI generated a tutorial plan that failed contract validation",
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
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except NarrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail="Narration enrichment produced an invalid tutorial plan",
        ) from exc

    command = DemoCommand(type="load_tutorial", plan=enriched, step=request.step)
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
