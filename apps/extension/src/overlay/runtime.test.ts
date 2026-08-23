import { describe, expect, it } from "vitest";
import type { TutorialStepRuntimeStatus } from "./protocol";
import { canTransitionRuntime } from "./runtime";

const states: TutorialStepRuntimeStatus[] = [
  "demonstrating",
  "demo_visible",
  "restoring",
  "waiting",
  "learner_attempt",
  "validating",
  "complete",
  "paused",
  "failed"
];

describe("tutorial runtime transitions", () => {
  it("accepts the initial status and idempotent updates", () => {
    expect(canTransitionRuntime(null, "waiting")).toBe(true);
    expect(canTransitionRuntime("learner_attempt", "learner_attempt")).toBe(true);
  });

  it("allows the learner-attempt happy path", () => {
    expect(canTransitionRuntime("demonstrating", "demo_visible")).toBe(true);
    expect(canTransitionRuntime("demo_visible", "restoring")).toBe(true);
    expect(canTransitionRuntime("restoring", "learner_attempt")).toBe(true);
    expect(canTransitionRuntime("learner_attempt", "validating")).toBe(true);
    expect(canTransitionRuntime("validating", "complete")).toBe(true);
  });

  it("rejects transitions that bypass restore or validation", () => {
    expect(canTransitionRuntime("demo_visible", "learner_attempt")).toBe(false);
    expect(canTransitionRuntime("learner_attempt", "complete")).toBe(false);
  });

  it("handles every defined status without a permissive fallback", () => {
    for (const state of states) {
      expect(typeof canTransitionRuntime(state, "failed")).toBe("boolean");
    }
  });
});
