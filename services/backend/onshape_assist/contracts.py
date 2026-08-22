"""Versioned payloads shared with the browser extension."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = 1


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TutorialAction(ContractModel):
    semantic_target: str = Field(min_length=1)
    precondition: str = Field(min_length=1)
    preferred_activation: Literal["dom", "browser_input"]
    fallback_activation: Literal["browser_input", "none"]


class TutorialPlanStep(ContractModel):
    step_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    actions: list[TutorialAction] = Field(min_length=1)
    expected_visible_result: str = Field(min_length=1)


class TutorialPlan(ContractModel):
    tutorial_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    steps: list[TutorialPlanStep] = Field(min_length=1)


class RuntimeStateSnapshot(ContractModel):
    session_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    state: Literal[
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
    sequence: int = Field(ge=0)


class RuntimeEvent(ContractModel):
    event: Literal[
        "runtime.state.changed",
        "demo.action.completed",
        "user.takeover.detected",
        "baseline.restore.confirmed",
        "learner.observation.captured",
        "validation.completed",
        "runtime.failed",
    ]
    session_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    timestamp_ms: int = Field(ge=0)
    source: Literal["runtime", "learner", "executor", "validator", "observer"]


class ValidationOutcome(ContractModel):
    outcome: Literal[
        "correct", "wrong_tool", "no_committed_change", "unexpected_geometry", "concurrent_edit"
    ]
    microversion_id: str = Field(min_length=1)


class RuntimeErrorPayload(ContractModel):
    code: Literal[
        "baseline_capture_failed",
        "target_not_found",
        "provider_unavailable",
        "restore_failed",
        "validation_failed",
        "relay_disconnected",
    ]
    message: str = Field(min_length=1)
    recoverable: bool


class RuntimeContractBundle(ContractModel):
    contract_version: Literal[CONTRACT_VERSION]
    tutorial_plan: TutorialPlan
    state_snapshot: RuntimeStateSnapshot
    runtime_events: list[RuntimeEvent]
    validation_outcome: ValidationOutcome
    error: RuntimeErrorPayload
