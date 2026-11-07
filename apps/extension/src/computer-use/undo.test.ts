import { describe, expect, it } from "vitest";
import tutorial from "../../../../tutorial.json";
import type { TutorialPlan } from "../overlay/protocol";
import { completedUndoCount } from "./undo";

const plan = tutorial.plan as TutorialPlan;

describe("completedUndoCount", () => {
  it("counts circle creation and submitted dimension as two undoable mutations", () => {
    expect(completedUndoCount(plan.steps[1]!, 7)).toBe(2);
  });

  it("does not count toolbar choices and selections as undoable mutations", () => {
    expect(completedUndoCount(plan.steps[0]!, 2)).toBe(1);
    expect(completedUndoCount(plan.steps[4]!, 5)).toBe(0);
  });

  it("only counts actions that completed before a failed action", () => {
    expect(completedUndoCount(plan.steps[1]!, 6)).toBe(1);
  });
});
