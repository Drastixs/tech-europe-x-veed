import { describe, expect, it } from "vitest";
import { isDemoEnvelope } from "./protocol";
import { tutorialPlanFixture } from "./test-fixtures";

const envelope = (plan: unknown) => ({
  version: 1,
  sequence: 1,
  sent_at: "2026-08-22T12:00:00Z",
  command: { type: "load_tutorial", plan, step: 1 as number | null }
});

const planWithAction = (action: unknown) => {
  const plan = structuredClone(tutorialPlanFixture) as unknown as {
    steps: Array<{ actions: unknown[] }>;
  };
  plan.steps[0]!.actions = [action];
  return plan;
};

const actionWith = (action_type: string, parameters?: unknown) => {
  const action = structuredClone(tutorialPlanFixture.steps[0]!.actions[0]!) as unknown as
    Record<string, unknown>;
  action.action_type = action_type;
  if (parameters === undefined) delete action.parameters;
  else action.parameters = parameters;
  return action;
};

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

  it.each([
    ["move", { duration_ms: 420 }],
    ["click", { button: "primary" }],
    ["double_click", { button: "primary", interval_ms: 120 }],
    ["drag", {
      end_target_label: "Axis",
      end_target_description: "The vertical construction line.",
      duration_ms: 700
    }],
    ["keypress", { key: "Enter", modifiers: ["control"], repeat: 1 }],
    ["type", { text: "25 mm", clear_existing: true, submit: true }],
    ["scroll", { delta_x: 0, delta_y: 640, duration_ms: 300 }],
    ["wait", { duration_ms: null, condition: "The Revolve dialog is visible." }],
    ["selection", { items: ["Sketch 1", "Axis"], mode: "replace", confirm: false }]
  ])("accepts %s action parameters", (actionType, parameters) => {
    expect(isDemoEnvelope(envelope(planWithAction(actionWith(actionType, parameters))))).toBe(true);
  });

  it.each([
    ["type", { button: "primary" }],
    ["scroll", { delta_x: 0, delta_y: 0, duration_ms: 300 }],
    ["wait", { duration_ms: null, condition: null }],
    ["selection", { items: [], mode: "replace", confirm: false }],
    ["click", { button: "primary", text: "unexpected" }]
  ])("rejects invalid %s action parameters", (actionType, parameters) => {
    expect(isDemoEnvelope(envelope(planWithAction(actionWith(actionType, parameters))))).toBe(false);
  });

  it("rejects an action without parameters", () => {
    expect(isDemoEnvelope(envelope(planWithAction(actionWith("click"))))).toBe(false);
  });

  it("accepts correlated screenshot capture commands", () => {
    expect(isDemoEnvelope({
      version: 1,
      sequence: 2,
      sent_at: "2026-08-22T12:00:00Z",
      command: { type: "capture_observation", request_id: "obs_1" }
    })).toBe(true);
  });

  it("accepts executable tutorial actions with localized coordinates", () => {
    expect(isDemoEnvelope({
      version: 1,
      sequence: 3,
      sent_at: "2026-08-22T12:00:00Z",
      command: {
        type: "execute_action",
        action_id: "action_1",
        action: tutorialPlanFixture.steps[0]!.actions[0],
        target: { x: 84, y: 298 },
        end_target: null
      }
    })).toBe(true);
  });
});
