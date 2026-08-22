export const CONTRACT_VERSION = 1 as const;

export const runtimeStates = [
  "demonstrating", "demo_visible", "restoring", "waiting", "learner_attempt",
  "validating", "complete", "paused", "failed"
] as const;

export const runtimeEventTypes = [
  "runtime.state.changed", "demo.action.completed", "user.takeover.detected",
  "baseline.restore.confirmed", "learner.observation.captured", "validation.completed",
  "runtime.failed"
] as const;

export const validationOutcomes = [
  "correct", "wrong_tool", "no_committed_change", "unexpected_geometry", "concurrent_edit"
] as const;

export const runtimeErrorCodes = [
  "baseline_capture_failed", "target_not_found", "provider_unavailable", "restore_failed",
  "validation_failed", "relay_disconnected"
] as const;

export type RuntimeContractBundle = {
  contract_version: typeof CONTRACT_VERSION;
  tutorial_plan: {
    tutorial_id: string;
    title: string;
    steps: Array<{
      step_id: string;
      goal: string;
      actions: Array<{
        semantic_target: string;
        precondition: string;
        preferred_activation: "dom" | "browser_input";
        fallback_activation: "browser_input" | "none";
      }>;
      expected_visible_result: string;
    }>;
  };
  state_snapshot: { session_id: string; step_id: string; state: (typeof runtimeStates)[number]; sequence: number };
  runtime_events: Array<{
    event: (typeof runtimeEventTypes)[number];
    session_id: string;
    step_id: string;
    timestamp_ms: number;
    source: "runtime" | "learner" | "executor" | "validator" | "observer";
  }>;
  validation_outcome: { outcome: (typeof validationOutcomes)[number]; microversion_id: string };
  error: { code: (typeof runtimeErrorCodes)[number]; message: string; recoverable: boolean };
};

const nonEmptyString = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0;

function isTutorialPlan(value: unknown): boolean {
  if (!value || typeof value !== "object") return false;
  const plan = value as Record<string, unknown>;
  return nonEmptyString(plan.tutorial_id) && nonEmptyString(plan.title) &&
    Array.isArray(plan.steps) && plan.steps.length > 0 && plan.steps.every((step) => {
      if (!step || typeof step !== "object") return false;
      const candidate = step as Record<string, unknown>;
      return nonEmptyString(candidate.step_id) && nonEmptyString(candidate.goal) &&
        nonEmptyString(candidate.expected_visible_result) && Array.isArray(candidate.actions) &&
        candidate.actions.length > 0 && candidate.actions.every((action) => {
          if (!action || typeof action !== "object") return false;
          const item = action as Record<string, unknown>;
          return nonEmptyString(item.semantic_target) && nonEmptyString(item.precondition) &&
            ["dom", "browser_input"].includes(item.preferred_activation as string) &&
            ["browser_input", "none"].includes(item.fallback_activation as string);
        });
    });
}

export function isRuntimeContractBundle(value: unknown): value is RuntimeContractBundle {
  if (!value || typeof value !== "object") return false;
  const bundle = value as Record<string, unknown>;
  const snapshot = bundle.state_snapshot as Record<string, unknown> | undefined;
  const outcome = bundle.validation_outcome as Record<string, unknown> | undefined;
  const error = bundle.error as Record<string, unknown> | undefined;
  if (
    bundle.contract_version !== CONTRACT_VERSION ||
    !isTutorialPlan(bundle.tutorial_plan) ||
    !snapshot || !runtimeStates.includes(snapshot.state as (typeof runtimeStates)[number]) ||
    !nonEmptyString(snapshot.session_id) || !nonEmptyString(snapshot.step_id) ||
    !Number.isInteger(snapshot.sequence) || (snapshot.sequence as number) < 0 ||
    !outcome || !validationOutcomes.includes(outcome.outcome as (typeof validationOutcomes)[number]) ||
    !nonEmptyString(outcome.microversion_id) ||
    !error || !runtimeErrorCodes.includes(error.code as (typeof runtimeErrorCodes)[number]) ||
    !nonEmptyString(error.message) ||
    typeof error.recoverable !== "boolean" || !Array.isArray(bundle.runtime_events)
  ) return false;

  return bundle.runtime_events.every((event) => {
    if (!event || typeof event !== "object") return false;
    const candidate = event as Record<string, unknown>;
    return runtimeEventTypes.includes(candidate.event as (typeof runtimeEventTypes)[number]) &&
      nonEmptyString(candidate.session_id) && nonEmptyString(candidate.step_id) &&
      Number.isInteger(candidate.timestamp_ms) && (candidate.timestamp_ms as number) >= 0 &&
      ["runtime", "learner", "executor", "validator", "observer"].includes(candidate.source as string);
  });
}
