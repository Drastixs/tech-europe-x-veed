"""Versioned payloads shared by the planner, relay, and browser extension."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = 1


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RuntimePreferences(ContractModel):
    detailed_narration: bool


class Voice(ContractModel):
    provider: Literal["fal_elevenlabs"]
    voice_id: str = Field(min_length=1)
    speaking_rate: Annotated[float, Field(gt=0)]


class TutorialAction(ContractModel):
    sequence: Annotated[int, Field(ge=1)]
    action_type: Literal[
        "move", "click", "double_click", "drag", "keypress", "type", "scroll", "wait", "selection"
    ]
    ui_region: str = Field(min_length=1)
    target_label: str | None
    target_description: str = Field(min_length=1)
    semantic_action: str = Field(min_length=1)
    expected_visible_result: str = Field(min_length=1)
    preferred_activation: Literal["dom_js", "cdp", "vision_only"]
    fallback_activation: Literal["cdp"] | None


class NarrationVariant(ContractModel):
    text: str = Field(min_length=1)
    fal_elevenlabs_audio_url: str = Field(min_length=1)
    duration_ms: Annotated[int, Field(ge=0)]


class Narration(ContractModel):
    concise: NarrationVariant
    detailed: NarrationVariant


class VoiceCue(ContractModel):
    cue_id: str = Field(min_length=1)
    phase: Literal[
        "before_step", "before_action", "during_action", "after_action", "after_step", "on_retry", "on_user_interrupt"
    ]
    action_sequence: Annotated[int, Field(ge=1)]
    variant: Literal["concise", "detailed", "both"]
    text_ref: str = Field(min_length=1)
    start_policy: Literal[
        "play_before_motion", "play_with_motion", "play_after_validation", "play_on_event"
    ]
    blocking: bool


class DynamicCorrections(ContractModel):
    retry: str = Field(min_length=1)
    target_relocated: str = Field(min_length=1)
    validation_failed: str = Field(min_length=1)
    user_interrupt: str = Field(min_length=1)


class TutorialStep(ContractModel):
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
        if sequences != list(range(1, len(self.actions) + 1)):
            raise ValueError("tutorial action sequences must be contiguous and ordered from 1")
        if any(cue.action_sequence not in sequences for cue in self.voice_cues):
            raise ValueError("voice cue action_sequence must reference an action in its step")
        if any(
            action.preferred_activation == "dom_js" and action.fallback_activation != "cdp"
            for action in self.actions
        ):
            raise ValueError("dom_js actions must use cdp as their fallback activation")
        return self


class TutorialPlan(ContractModel):
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


class RuntimeStateSnapshot(ContractModel):
    session_id: str = Field(min_length=1)
    tutorial_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    state: Literal[
        "demonstrating", "demo_visible", "restoring", "waiting", "learner_attempt",
        "validating", "complete", "paused", "failed",
    ]
    sequence: Annotated[int, Field(ge=0)]


class RuntimeEvent(ContractModel):
    event: Literal[
        "runtime.state.changed", "demo.action.completed", "user.takeover.detected",
        "user.takeover.clicked", "baseline.restore.confirmed", "learner.observation.captured",
        "validation.completed", "runtime.failed",
    ]
    session_id: str = Field(min_length=1)
    tutorial_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    timestamp_ms: Annotated[int, Field(ge=0)]
    source: Literal["runtime", "learner", "executor", "validator", "observer"]


class ValidationOutcome(ContractModel):
    outcome: Literal[
        "correct", "wrong_tool", "no_committed_change", "unexpected_geometry", "concurrent_edit"
    ]
    microversion_id: str = Field(min_length=1)


class RuntimeErrorPayload(ContractModel):
    code: Literal[
        "baseline_capture_failed", "target_not_found", "provider_unavailable", "restore_failed",
        "validation_failed", "relay_disconnected",
    ]
    message: str = Field(min_length=1)
    recoverable: bool


class RuntimeSession(ContractModel):
    """Versioned runtime context transported with a tutorial relay command."""

    contract_version: Literal[CONTRACT_VERSION]
    session_id: str = Field(min_length=1)
    state_snapshot: RuntimeStateSnapshot
    runtime_events: list[RuntimeEvent] = Field(default_factory=list)
    validation_outcome: ValidationOutcome | None = None
    error: RuntimeErrorPayload | None = None

    @model_validator(mode="after")
    def validate_session_references(self) -> RuntimeSession:
        if self.state_snapshot.session_id != self.session_id:
            raise ValueError("runtime state session_id must match runtime session")
        if any(event.session_id != self.session_id for event in self.runtime_events):
            raise ValueError("runtime events must belong to the active session")
        return self


class RuntimeContractBundle(ContractModel):
    """Canonical v1 fixture for a planner-produced tutorial runtime session."""

    contract_version: Literal[CONTRACT_VERSION]
    tutorial_plan: TutorialPlan
    state_snapshot: RuntimeStateSnapshot
    runtime_events: list[RuntimeEvent]
    validation_outcome: ValidationOutcome
    error: RuntimeErrorPayload

    @model_validator(mode="after")
    def validate_session_references(self) -> RuntimeContractBundle:
        plan = self.tutorial_plan
        session = self.state_snapshot
        if session.tutorial_id != plan.tutorial_id:
            raise ValueError("runtime state tutorial_id must reference tutorial_plan")
        step_ids = {step.step_id for step in plan.steps}
        if session.step_id not in step_ids:
            raise ValueError("runtime state step_id must reference tutorial_plan")
        for event in self.runtime_events:
            if event.session_id != session.session_id or event.tutorial_id != plan.tutorial_id:
                raise ValueError("runtime events must belong to the active session and tutorial")
            if event.step_id not in step_ids:
                raise ValueError("runtime event step_id must reference tutorial_plan")
        return self
