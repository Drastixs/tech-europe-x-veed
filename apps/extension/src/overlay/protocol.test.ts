import { describe, expect, it } from "vitest";
import { isDemoEnvelope } from "./protocol";
import { tutorialPlanFixture } from "./test-fixtures";

const envelope = (plan: unknown) => ({
  version: 1,
  sequence: 1,
  sent_at: "2026-08-22T12:00:00Z",
  command: { type: "load_tutorial", plan, step: 1 as number | null }
});

describe("tutorial plan protocol", () => {
  it("accepts a complete tutorial plan envelope", () => {
    expect(isDemoEnvelope(envelope(tutorialPlanFixture))).toBe(true);
  });

  it("accepts the backend's nullable optional step field", () => {
    const value = envelope(tutorialPlanFixture);
    value.command.step = null;
    expect(isDemoEnvelope(value)).toBe(true);
  });

  it("rejects empty tutorial plans", () => {
    expect(isDemoEnvelope(envelope({ ...tutorialPlanFixture, steps: [] }))).toBe(false);
  });

  it("rejects invalid nested plan data", () => {
    const invalidPlan = structuredClone(tutorialPlanFixture) as unknown as {
      steps: Array<{ actions: Array<{ action_type: string }> }>;
    };
    invalidPlan.steps[0]!.actions[0]!.action_type = "teleport";

    expect(isDemoEnvelope(envelope(invalidPlan))).toBe(false);
  });
});
