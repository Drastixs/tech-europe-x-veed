import { isTutorialPlan, type TutorialPlan } from "../overlay/protocol";

export const CONTRACT_VERSION = 1 as const;

export const runtimeStates = [
  "demonstrating", "demo_visible", "restoring", "waiting", "learner_attempt",
  "validating", "complete", "paused", "failed"
] as const;

export const runtimeEventTypes = [
  "runtime.state.changed", "demo.action.completed", "user.takeover.detected",
  "user.takeover.clicked", "baseline.restore.confirmed", "learner.observation.captured",
  "validation.completed", "runtime.failed"
] as const;

export const validationOutcomes = [
  "correct", "wrong_tool", "no_committed_change", "unexpected_geometry", "concurrent_edit"
] as const;

export const runtimeErrorCodes = [
  "baseline_capture_failed", "target_not_found", "provider_unavailable", "restore_failed",
  "validation_failed", "relay_disconnected"
] as const;

type RuntimeState = (typeof runtimeStates)[number];
type RuntimeEventType = (typeof runtimeEventTypes)[number];

export type RuntimeContractBundle = {
  contract_version: typeof CONTRACT_VERSION;
  tutorial_plan: TutorialPlan;
  state_snapshot: {
    session_id: string;
    tutorial_id: string;
    step_id: string;
    state: RuntimeState;
    sequence: number;
  };
  runtime_events: Array<{
    event: RuntimeEventType;
    session_id: string;
    tutorial_id: string;
    step_id: string;
    timestamp_ms: number;
    source: "runtime" | "learner" | "executor" | "validator" | "observer";
  }>;
  validation_outcome: { outcome: (typeof validationOutcomes)[number]; microversion_id: string };
  error: { code: (typeof runtimeErrorCodes)[number]; message: string; recoverable: boolean };
};

const nonEmptyString = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object";

export function isRuntimeContractBundle(value: unknown): value is RuntimeContractBundle {
  if (!isRecord(value) || value.contract_version !== CONTRACT_VERSION) {
    return false;
  }
  const tutorialPlan = value.tutorial_plan;
  if (!isTutorialPlan(tutorialPlan)) return false;
  const snapshot = value.state_snapshot;
  const outcome = value.validation_outcome;
  const error = value.error;
  if (!isRecord(snapshot) || !isRecord(outcome) || !isRecord(error) || !Array.isArray(value.runtime_events)) {
    return false;
  }
  if (
    !nonEmptyString(snapshot.session_id) || snapshot.tutorial_id !== tutorialPlan.tutorial_id ||
    !nonEmptyString(snapshot.step_id) || !runtimeStates.includes(snapshot.state as RuntimeState) ||
    !Number.isInteger(snapshot.sequence) || (snapshot.sequence as number) < 0 ||
    !validationOutcomes.includes(outcome.outcome as (typeof validationOutcomes)[number]) ||
    !nonEmptyString(outcome.microversion_id) ||
    !runtimeErrorCodes.includes(error.code as (typeof runtimeErrorCodes)[number]) ||
    !nonEmptyString(error.message) || typeof error.recoverable !== "boolean"
  ) return false;

  const stepIds = new Set(tutorialPlan.steps.map((step) => step.step_id));
  if (!stepIds.has(snapshot.step_id)) return false;
  return value.runtime_events.every((event) => {
    if (!isRecord(event)) return false;
    return runtimeEventTypes.includes(event.event as RuntimeEventType) &&
      event.session_id === snapshot.session_id && event.tutorial_id === tutorialPlan.tutorial_id &&
      typeof event.step_id === "string" && stepIds.has(event.step_id) &&
      Number.isInteger(event.timestamp_ms) && (event.timestamp_ms as number) >= 0 &&
      ["runtime", "learner", "executor", "validator", "observer"].includes(event.source as string);
  });
}
