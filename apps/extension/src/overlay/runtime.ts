import type { TutorialStepRuntimeStatus } from "./protocol";

const transitions: Record<TutorialStepRuntimeStatus, ReadonlySet<TutorialStepRuntimeStatus>> = {
  demonstrating: new Set(["demo_visible", "restoring", "paused", "failed"]),
  demo_visible: new Set(["restoring", "paused", "failed"]),
  restoring: new Set(["learner_attempt", "paused", "failed"]),
  waiting: new Set(["demonstrating", "paused", "failed"]),
  learner_attempt: new Set(["validating", "paused", "failed"]),
  validating: new Set(["complete", "paused", "failed"]),
  complete: new Set(["waiting", "demonstrating"]),
  paused: new Set(["waiting", "demonstrating", "restoring", "failed"]),
  failed: new Set(["waiting", "demonstrating"])
};

export function canTransitionRuntime(
  from: TutorialStepRuntimeStatus | null,
  to: TutorialStepRuntimeStatus
): boolean {
  return from === null || from === to || transitions[from].has(to);
}
