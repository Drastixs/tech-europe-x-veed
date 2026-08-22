from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from .computer_use import (
    ComputerUseError,
    DemonstrationResult,
    DemoRunner,
    ExtensionEventBroker,
    PixelPoint,
)
from .holo import (
    HoloClient,
    HoloConfigurationError,
    HoloError,
    LocalizationContext,
    LocalizedPoint,
)
from .narration import (
    NarrationConfigurationError,
    NarrationError,
    enrich_plan_narration,
)
from .planner import OpenAIPlanner, PlannerError

Direction = Literal["left", "right"]


class TutorialContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimePreferences(TutorialContractModel):
    detailed_narration: bool


class Voice(TutorialContractModel):
    provider: Literal["fal_elevenlabs"]
    voice_id: str = Field(min_length=1)
    speaking_rate: Annotated[float, Field(gt=0)]


class TutorialActionBase(TutorialContractModel):
    sequence: Annotated[int, Field(ge=1)]
    ui_region: str = Field(min_length=1)
    target_label: str | None
    target_description: str = Field(min_length=1)
    semantic_action: str = Field(min_length=1)
    expected_visible_result: str = Field(min_length=1)
    preferred_activation: Literal["dom_js", "cdp", "vision_only"]
    fallback_activation: Literal["cdp"] | None


class MoveParameters(TutorialContractModel):
    duration_ms: Annotated[int, Field(ge=0, le=10_000)]


class PointerParameters(TutorialContractModel):
    button: Literal["primary", "secondary", "middle"]


class DoubleClickParameters(PointerParameters):
    interval_ms: Annotated[int, Field(ge=0, le=1_000)]


class DragParameters(TutorialContractModel):
    end_target_label: str | None
    end_target_description: str = Field(min_length=1)
    duration_ms: Annotated[int, Field(ge=0, le=10_000)]


class KeypressParameters(TutorialContractModel):
    key: str = Field(min_length=1)
    modifiers: list[Literal["alt", "control", "meta", "shift"]]
    repeat: Annotated[int, Field(ge=1, le=100)]


class TypeParameters(TutorialContractModel):
    text: str = Field(min_length=1)
    clear_existing: bool
    submit: bool


class ScrollParameters(TutorialContractModel):
    delta_x: int
    delta_y: int
    duration_ms: Annotated[int, Field(ge=0, le=10_000)]

    @model_validator(mode="after")
    def validate_nonzero_delta(self) -> ScrollParameters:
        if self.delta_x == 0 and self.delta_y == 0:
            raise ValueError("scroll parameters require a non-zero delta")
        return self


class WaitParameters(TutorialContractModel):
    duration_ms: Annotated[int, Field(ge=0, le=60_000)] | None
    condition: str | None

    @model_validator(mode="after")
    def validate_duration_or_condition(self) -> WaitParameters:
        if self.duration_ms is None and not self.condition:
            raise ValueError("wait parameters require duration_ms or condition")
        return self


class SelectionParameters(TutorialContractModel):
    items: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]
    mode: Literal["replace", "add", "toggle"]
    confirm: bool


class MoveAction(TutorialActionBase):
    action_type: Literal["move"]
    parameters: MoveParameters


class ClickAction(TutorialActionBase):
    action_type: Literal["click"]
    parameters: PointerParameters


class DoubleClickAction(TutorialActionBase):
    action_type: Literal["double_click"]
    parameters: DoubleClickParameters


class DragAction(TutorialActionBase):
    action_type: Literal["drag"]
    parameters: DragParameters


class KeypressAction(TutorialActionBase):
    action_type: Literal["keypress"]
    parameters: KeypressParameters


class TypeAction(TutorialActionBase):
    action_type: Literal["type"]
    parameters: TypeParameters


class ScrollAction(TutorialActionBase):
    action_type: Literal["scroll"]
    parameters: ScrollParameters


class WaitAction(TutorialActionBase):
    action_type: Literal["wait"]
    parameters: WaitParameters


class SelectionAction(TutorialActionBase):
    action_type: Literal["selection"]
    parameters: SelectionParameters


TutorialAction = (
    MoveAction
    | ClickAction
    | DoubleClickAction
    | DragAction
    | KeypressAction
    | TypeAction
    | ScrollAction
    | WaitAction
    | SelectionAction
)


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
    | ExecuteActionCommand,
    Field(discriminator="type"),
]
demo_command_adapter = TypeAdapter(DemoCommand)


class ComputerUseDemonstrationRequest(BaseModel):
    action: TutorialAction
    step_goal: str | None = None
    execute: bool = True


class HoloLocalizationRequest(BaseModel):
    screenshot_data_url: str = Field(min_length=1)
    target_description: str = Field(min_length=1)
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

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        if self.last_envelope and self.last_envelope.command.type not in {
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

PlannerFactory = Callable[[], OpenAIPlanner]
NarrationEnricher = Callable[[TutorialPlan], Awaitable[TutorialPlan]]
HoloFactory = Callable[[], HoloClient]


planner_factory: PlannerFactory = OpenAIPlanner
narration_enricher: NarrationEnricher = enrich_plan_narration
holo_factory: HoloFactory = HoloClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.relay = relay
    yield


app = FastAPI(title="Onshape Assist Relay", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, int | str]:
    return {"status": "ok", "clients": relay.client_count}


@app.post("/commands", response_model=DemoEnvelope)
async def command(command: DemoCommand) -> DemoEnvelope:
    try:
        normalized = normalize_command(command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await relay.publish(normalized)


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
        return await runner.demonstrate(
            request.action, step_goal=request.step_goal, execute=request.execute
        )
    except HoloConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HoloError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except (ComputerUseError, ValidationError) as exc:
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

    command = LoadTutorialCommand(type="load_tutorial", plan=enriched, step=request.step)
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
                extension_events.resolve(message["event"])
    except WebSocketDisconnect:
        relay.disconnect(websocket)


def normalize_command(command: DemoCommand) -> DemoCommand:
    if (
        command.type == "load_tutorial"
        and command.step is not None
        and command.step > len(command.plan.steps)
    ):
        raise ValueError("load_tutorial step exceeds the number of steps")
    return command
