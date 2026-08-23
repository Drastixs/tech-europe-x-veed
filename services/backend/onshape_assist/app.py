from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from onshape_assist.analysis import fal
from onshape_assist.analysis.models import AnalysisRequest, AnalysisResult
from onshape_assist.analysis.pipeline import AnalysisError, analyze_video_async

from .computer_use import (
    ComputerUseError,
    DemonstrationResult,
    DemoRunner,
    ExtensionEventBroker,
    PixelPoint,
    StepDemonstrationResult,
)
from .config import load_backend_env
from .contracts import (
    CONTRACT_VERSION,
    ClickAction,
    DragAction,
    RuntimePreferences,
    RuntimeSession,
    RuntimeStateSnapshot,
    TutorialAction,
    TutorialPlan,
    TutorialStep,
    Voice,
)

__all__ = ["ClickAction", "DragAction"]
from .holo import (
    HoloClient,
    HoloConfigurationError,
    HoloError,
    LocalizationContext,
    LocalizedPoint,
)
from .launcher_page import render_launcher_page
from .narration import (
    NarrationConfigurationError,
    NarrationError,
    enrich_plan_narration,
)
from .observation import LearnerObservationContext
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


class CommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ShowCommand(CommandBase):
    type: Literal["show"]


class HideCommand(CommandBase):
    type: Literal["hide"]


class MoveCommand(CommandBase):
    type: Literal["move"]
    x: Annotated[int, Field(ge=0)]
    y: Annotated[int, Field(ge=0)]
    duration_ms: Annotated[int | None, Field(ge=0, le=10_000)] = None


class ClickCommand(CommandBase):
    type: Literal["click"]


class NavigateCommand(CommandBase):
    type: Literal["navigate"]
    direction: Direction


class LoadTutorialCommand(CommandBase):
    type: Literal["load_tutorial"]
    plan: TutorialPlan
    step: Annotated[int | None, Field(ge=1)] = None
    runtime_session: RuntimeSession | None = None


class ArmTakeoverCommand(CommandBase):
    type: Literal["arm_takeover"]


class DisarmTakeoverCommand(CommandBase):
    type: Literal["disarm_takeover"]


class CaptureObservationCommand(CommandBase):
    type: Literal["capture_observation"]
    request_id: str = Field(min_length=1)


class ExecuteActionCommand(CommandBase):
    type: Literal["execute_action"]
    action_id: str = Field(min_length=1)
    action: TutorialAction
    target: PixelPoint
    end_target: PixelPoint | None


class TutorialStepStatusCommand(CommandBase):
    type: Literal["tutorial_step_status"]
    session_id: str = Field(min_length=1)
    tutorial_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    status: Literal[
        "demonstrating",
        "demo_visible",
        "restoring",
        "waiting",
        "learner_attempt",
        "validating",
        "complete",
        "paused",
        "failed",
    ]
    message: str | None = None


DemoCommand = Annotated[
    ShowCommand
    | HideCommand
    | MoveCommand
    | ClickCommand
    | NavigateCommand
    | LoadTutorialCommand
    | ArmTakeoverCommand
    | DisarmTakeoverCommand
    | CaptureObservationCommand
    | ExecuteActionCommand
    | TutorialStepStatusCommand,
    Field(discriminator="type"),
]
demo_command_adapter = TypeAdapter(DemoCommand)


class ComputerUseDemonstrationRequest(BaseModel):
    action: TutorialAction
    step_goal: str | None = None
    execute: bool = True


class ComputerUseStepDemonstrationRequest(BaseModel):
    step: TutorialStep
    execute: bool = True


class TutorialStepExecutionRequest(BaseModel):
    """Execute one already-planned, narrated step in a live Onshape workspace."""

    plan: TutorialPlan
    step: Annotated[int, Field(ge=1)]
    document_url: str = Field(min_length=1)
    execute: bool = True


class TutorialStepExecutionSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1)
    tutorial_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    step_goal: str = Field(min_length=1)
    expected_end_state: str = Field(min_length=1)
    state: Literal[
        "demonstrating",
        "demo_visible",
        "restoring",
        "learner_attempt",
        "waiting",
        "validating",
        "complete",
        "paused",
        "failed",
        "restore_failed",
        "demonstration_failed",
    ]
    baseline: OnshapeSnapshot
    demo_snapshot: OnshapeSnapshot | None = None
    demonstration: StepDemonstrationResult | None = None
    restore: RestoreResult | None = None
    learner_observation_count: Annotated[int, Field(ge=0)] = 0
    latest_learner_observation_at_ms: Annotated[int | None, Field(ge=0)] = None
    learner_observation: LearnerObservationContext = Field(
        default_factory=LearnerObservationContext
    )
    validation: ValidationResult | None = None
    paused_from: Literal[
        "demonstrating", "demo_visible", "restoring", "waiting", "learner_attempt", "validating"
    ] | None = None


class HoloLocalizationRequest(BaseModel):
    screenshot_data_url: str = Field(min_length=1)
    target_description: str = Field(min_length=1)
    icon_description: str | None = None
    target_label: str | None = None
    ui_region: str | None = None
    semantic_action: str | None = None
    step_goal: str | None = None


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
        self._recovery_load: DemoEnvelope | None = None
        self._recovery_status: DemoEnvelope | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        if self.last_envelope is not None and self._recovery_load is not None:
            await websocket.send_json(self._recovery_load.model_dump())
            if self._recovery_status is not None:
                await websocket.send_json(self._recovery_status.model_dump())
        elif self.last_envelope and self.last_envelope.command.type not in {
            "capture_observation",
            "execute_action",
        }:
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
        if command.type == "load_tutorial":
            self._recovery_load = envelope
            self._recovery_status = None
        elif command.type == "tutorial_step_status":
            self._recovery_status = envelope
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
extension_events = ExtensionEventBroker()
computer_use_lock = asyncio.Lock()

PlannerFactory = Callable[[], OpenAIPlanner]
NarrationEnricher = Callable[[TutorialPlan], Awaitable[TutorialPlan]]
HoloFactory = Callable[[], HoloClient]
OnshapeFactory = Callable[[], OnshapeClient]


planner_factory: PlannerFactory = OpenAIPlanner
narration_enricher: NarrationEnricher = enrich_plan_narration
holo_factory: HoloFactory = HoloClient
onshape_factory: OnshapeFactory = OnshapeClient.from_env
tutorial_step_sessions: dict[str, TutorialStepExecutionSession] = {}
active_tutorial_step_session_id: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.relay = relay
    yield


app = FastAPI(title="Onshape Assist Relay", version="0.1.0", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def launcher_home() -> HTMLResponse:
    project_dir = Path(__file__).resolve().parents[3]
    extension_dir = project_dir / "apps" / "extension" / "output" / "chrome-mv3"
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


async def publish_computer_use_command(command_data: dict[str, Any]) -> None:
    command = demo_command_adapter.validate_python(command_data)
    await relay.publish(command)


async def request_extension_event(
    command_data: dict[str, Any], correlation_id: str, timeout_seconds: float
) -> dict[str, Any]:
    future = extension_events.prepare(correlation_id)
    try:
        await publish_computer_use_command(command_data)
        return await extension_events.wait(correlation_id, future, timeout_seconds)
    except Exception:
        extension_events.cancel(correlation_id)
        raise


@app.post("/computer-use/localize", response_model=LocalizedPoint)
async def localize_computer_target(request: HoloLocalizationRequest) -> LocalizedPoint:
    try:
        return await holo_factory().localize(
            request.screenshot_data_url,
            LocalizationContext(
                target_description=request.target_description,
                icon_description=request.icon_description,
                target_label=request.target_label,
                ui_region=request.ui_region,
                semantic_action=request.semantic_action,
                step_goal=request.step_goal,
            ),
        )
    except HoloConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HoloError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/computer-use/demonstrate", response_model=DemonstrationResult)
async def demonstrate_computer_action(
    request: ComputerUseDemonstrationRequest,
) -> DemonstrationResult:
    runner = DemoRunner(
        holo=holo_factory(),
        publish_command=publish_computer_use_command,
        request_extension=request_extension_event,
    )
    try:
        async with computer_use_lock:
            return await runner.demonstrate(
                request.action, step_goal=request.step_goal, execute=request.execute
            )
    except HoloConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HoloError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (ComputerUseError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/computer-use/demonstrate-step", response_model=StepDemonstrationResult)
async def demonstrate_computer_step(
    request: ComputerUseStepDemonstrationRequest,
) -> StepDemonstrationResult:
    runner = DemoRunner(
        holo=holo_factory(),
        publish_command=publish_computer_use_command,
        request_extension=request_extension_event,
    )
    try:
        async with computer_use_lock:
            return await runner.demonstrate_step(request.step, execute=request.execute)
    except HoloConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HoloError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (ComputerUseError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/tutorials/demonstrate-step", response_model=TutorialStepExecutionSession)
async def demonstrate_tutorial_step(
    request: TutorialStepExecutionRequest,
) -> TutorialStepExecutionSession:
    """Capture a rollback point, demonstrate a narrated plan step, and arm takeover."""
    global active_tutorial_step_session_id

    if request.step > len(request.plan.steps):
        raise HTTPException(status_code=422, detail="step exceeds the number of plan steps")
    try:
        target = OnshapeTarget.from_document_url(request.document_url)
    except OnshapeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    async with computer_use_lock:
        await _restore_visible_demo_before_redo(target)
        baseline = _run_onshape_operation(lambda client: client.snapshot(target))
        tutorial_step = request.plan.steps[request.step - 1]
        session = TutorialStepExecutionSession(
            session_id=f"tutorial_step_{uuid4().hex}",
            tutorial_id=request.plan.tutorial_id,
            step_id=tutorial_step.step_id,
            step_goal=tutorial_step.goal,
            expected_end_state=tutorial_step.expected_end_state,
            state="demonstrating",
            baseline=baseline,
        )
        tutorial_step_sessions[session.session_id] = session
        active_tutorial_step_session_id = session.session_id
        await _publish_tutorial_step_status(session)

        runner = DemoRunner(
            holo=holo_factory(),
            publish_command=publish_computer_use_command,
            request_extension=request_extension_event,
        )
        try:
            demonstration = await runner.demonstrate_step(tutorial_step, execute=request.execute)
        except HoloConfigurationError as exc:
            await _fail_tutorial_step_session(session, str(exc))
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (HoloError, ComputerUseError, ValidationError) as exc:
            await _fail_tutorial_step_session(session, str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        session.demonstration = demonstration
        if not demonstration.success:
            session.state = "demonstration_failed"
            await _publish_tutorial_step_status(
                session, status="failed", message=demonstration.reason
            )
            return session

        try:
            session.demo_snapshot = _run_onshape_operation(lambda client: client.snapshot(target))
        except HTTPException as exc:
            await _fail_tutorial_step_session(session, str(exc.detail))
            raise
        session.state = "demo_visible"
        await _publish_tutorial_step_status(session)
        await relay.publish(ArmTakeoverCommand(type="arm_takeover"))
        return session


@app.get(
    "/tutorials/demonstration-sessions/{session_id}",
    response_model=TutorialStepExecutionSession,
)
async def get_tutorial_step_session(session_id: str) -> TutorialStepExecutionSession:
    session = tutorial_step_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="tutorial step session not found")
    return session


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

    if request.step > len(enriched.steps):
        raise HTTPException(status_code=422, detail="step exceeds the number of plan steps")
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
    command = LoadTutorialCommand(
        type="load_tutorial",
        plan=enriched,
        step=request.step,
        runtime_session=runtime_session,
    )
    try:
        normalized = normalize_command(command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await relay.publish(normalized)


@app.websocket("/ws/extension")
async def extension_socket(websocket: WebSocket) -> None:
    await relay.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(message, dict)
                and message.get("type") == "extension.event"
                and isinstance(message.get("event"), dict)
            ):
                event = message["event"]
                extension_events.resolve(event)
                if event.get("type") in {
                    "observation.captured",
                    "learner.observation.captured",
                }:
                    asyncio.create_task(_record_learner_observation(event))
                if event.get("type") == "user.takeover":
                    async with computer_use_lock:
                        await _restore_active_tutorial_step(event.get("session_id"))
                if event.get("type") == "tutorial.runtime.pause.requested":
                    await _pause_active_tutorial_step(event.get("session_id"))
                if event.get("type") == "tutorial.runtime.resume.requested":
                    await _resume_active_tutorial_step(event.get("session_id"))
    except WebSocketDisconnect:
        relay.disconnect(websocket)


def normalize_command(command: DemoCommand) -> DemoCommand:
    if command.type == "load_tutorial":
        if command.step is not None and command.step > len(command.plan.steps):
            raise ValueError("load_tutorial step exceeds the number of steps")
        if command.runtime_session is not None:
            runtime_session = command.runtime_session
            snapshot = runtime_session.state_snapshot
            if snapshot.tutorial_id != command.plan.tutorial_id:
                raise ValueError("runtime session must reference the loaded tutorial")
            step_ids = {step.step_id for step in command.plan.steps}
            if snapshot.step_id not in step_ids:
                raise ValueError("runtime session must reference a loaded tutorial step")
            if any(
                event.tutorial_id != command.plan.tutorial_id
                for event in runtime_session.runtime_events
            ):
                raise ValueError("runtime events must reference the loaded tutorial")
            if any(event.step_id not in step_ids for event in runtime_session.runtime_events):
                raise ValueError("runtime events must reference a loaded tutorial step")
    return command


def _with_onshape_client(operation: Callable[[OnshapeClient], Any]) -> Any:
    return _run_onshape_operation(operation)


def _run_onshape_operation(operation: Callable[[OnshapeClient], Any]) -> Any:
    try:
        client = onshape_factory()
    except OnshapeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        return operation(client)
    except OnshapeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        client.close()


async def _publish_tutorial_step_status(
    session: TutorialStepExecutionSession,
    *,
    status: Literal[
        "demonstrating",
        "demo_visible",
        "restoring",
        "waiting",
        "learner_attempt",
        "validating",
        "complete",
        "paused",
        "failed",
    ]
    | None = None,
    message: str | None = None,
) -> None:
    published_status = status or (
        session.state
        if session.state in {
            "demonstrating",
            "demo_visible",
            "restoring",
            "waiting",
            "learner_attempt",
            "validating",
            "complete",
            "paused",
        }
        else "failed"
    )
    await relay.publish(
        TutorialStepStatusCommand(
            type="tutorial_step_status",
            session_id=session.session_id,
            tutorial_id=session.tutorial_id,
            step_id=session.step_id,
            status=published_status,
            message=message,
        )
    )


async def _fail_tutorial_step_session(session: TutorialStepExecutionSession, message: str) -> None:
    session.state = "demonstration_failed"
    await _publish_tutorial_step_status(session, status="failed", message=message)


async def _restore_active_tutorial_step(requested_session_id: Any = None) -> None:
    session_id = active_tutorial_step_session_id
    if session_id is None:
        return
    if isinstance(requested_session_id, str) and requested_session_id != session_id:
        return
    session = tutorial_step_sessions.get(session_id)
    if session is None or session.state != "demo_visible" or session.demo_snapshot is None:
        return

    session.state = "restoring"
    await _publish_tutorial_step_status(session)


    try:
        restore = _run_onshape_operation(
            lambda client: client.restore_baseline(
                session.baseline,
                expected_microversion_id=session.demo_snapshot.microversion_id,
            )
        )
    except HTTPException as exc:
        session.state = "restore_failed"
        await _publish_tutorial_step_status(session, status="failed", message=str(exc.detail))
        return

    session.restore = restore
    if restore.outcome != "restored":
        session.state = "restore_failed"
        await _publish_tutorial_step_status(
            session,
            status="failed",
            message=f"baseline restore failed: {restore.outcome}",
        )
        return

    session.state = "learner_attempt"
    await relay.publish(DisarmTakeoverCommand(type="disarm_takeover"))
    await _publish_tutorial_step_status(session)


async def _pause_active_tutorial_step(requested_session_id: Any = None) -> None:
    session = _active_tutorial_step_session(requested_session_id)
    if session is None or session.state in {"complete", "failed", "paused"}:
        return
    session.paused_from = session.state
    session.state = "paused"
    await _publish_tutorial_step_status(session, message="Tutorial paused.")


async def _resume_active_tutorial_step(requested_session_id: Any = None) -> None:
    session = _active_tutorial_step_session(requested_session_id)
    if session is None or session.state != "paused" or session.paused_from is None:
        return
    session.state = session.paused_from
    session.paused_from = None
    await _publish_tutorial_step_status(session)


def _active_tutorial_step_session(requested_session_id: Any) -> TutorialStepExecutionSession | None:
    session_id = active_tutorial_step_session_id
    if session_id is None:
        return None
    if isinstance(requested_session_id, str) and requested_session_id != session_id:
        return None
    return tutorial_step_sessions.get(session_id)


async def _restore_visible_demo_before_redo(target: OnshapeTarget) -> None:
    """Reset our own still-visible demo before a replay captures a fresh baseline."""
    session_id = active_tutorial_step_session_id
    session = tutorial_step_sessions.get(session_id) if session_id else None
    if (
        session is None
        or session.state != "demo_visible"
        or session.demo_snapshot is None
        or session.baseline.target != target
    ):
        return
    session.state = "restoring"
    await _publish_tutorial_step_status(session)
    await relay.publish(DisarmTakeoverCommand(type="disarm_takeover"))
    try:
        restore = _run_onshape_operation(
            lambda client: client.restore_baseline(
                session.baseline,
                expected_microversion_id=session.demo_snapshot.microversion_id,
            )
        )
    except HTTPException as exc:
        session.state = "restore_failed"
        await _publish_tutorial_step_status(
            session, status="failed", message=f"cannot replay: {exc.detail}"
        )
        raise
    session.restore = restore
    if restore.outcome != "restored":
        session.state = "restore_failed"
        await _publish_tutorial_step_status(
            session, status="failed", message=f"cannot replay: {restore.outcome}"
        )
        raise HTTPException(status_code=409, detail=f"cannot replay step: {restore.outcome}")
    session.state = "learner_attempt"


async def _record_learner_observation(event: dict[str, Any]) -> None:
    session_id = active_tutorial_step_session_id
    session = tutorial_step_sessions.get(session_id) if session_id else None
    if session is None or session.state != "learner_attempt":
        return
    event_session_id = event.get("session_id")
    if isinstance(event_session_id, str) and event_session_id != session.session_id:
        return
    timestamp_ms = event.get("timestamp_ms")
    if not isinstance(timestamp_ms, int) or timestamp_ms < 0:
        timestamp_ms = int(datetime.now(UTC).timestamp() * 1000)
    session.learner_observation_count += 1
    session.latest_learner_observation_at_ms = timestamp_ms
    screenshot = event.get("screenshot_data_url")
    if not isinstance(screenshot, str) or not screenshot.startswith("data:image/"):
        return
    session.learner_observation.add_screenshot(screenshot, timestamp_ms)
    try:
        session.learner_observation.latest_assessment = await holo_factory().assess_learner_progress(
            session.learner_observation,
            step_goal=session.step_goal,
            expected_end_state=session.expected_end_state,
        )
    except HoloError as exc:
        session.state = "paused"
        await _publish_tutorial_step_status(
            session,
            status="paused",
            message=f"Learner observation paused: {exc}",
        )
        return

    if session.learner_observation.latest_assessment.state != "ready_to_validate":
        return

    session.state = "validating"
    await _publish_tutorial_step_status(session)
    try:
        validation = _run_onshape_operation(
            lambda client: client.validate_attempt(
                session.baseline,
                expected_feature_type=_expected_feature_type(session),
            )
        )
    except HTTPException as exc:
        session.state = "failed"
        await _publish_tutorial_step_status(session, status="failed", message=str(exc.detail))
        return

    session.validation = validation
    if validation.outcome == "correct":
        session.state = "complete"
        await _publish_tutorial_step_status(session, message="Step complete.")
        return

    session.state = "paused"
    await _publish_tutorial_step_status(
        session,
        status="paused",
        message=f"Validation outcome: {validation.outcome}",
    )


def _expected_feature_type(session: TutorialStepExecutionSession) -> str:
    """Derive the committed Onshape feature type from the step's modelling language."""
    for candidate in (session.step_goal, session.expected_end_state):
        match = re.search(
            r"\b(create|open|confirm)\s+(?:a\s+|an\s+|the\s+)?([a-z]+)",
            candidate,
            re.IGNORECASE,
        )
        if match:
            return match.group(2).lower()
    raise HTTPException(status_code=422, detail="step does not identify an expected Onshape feature type")
