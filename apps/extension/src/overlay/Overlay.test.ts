import { describe, expect, it } from "vitest";
import { createStepRedoRequestedEvent } from "./Overlay";

describe("overlay step redo", () => {
  it("identifies the active tutorial step for orchestration", () => {
    expect(createStepRedoRequestedEvent("tutorial-7", "make-sketch", 3, 1_700_000_000_000)).toEqual({
      type: "tutorial.step.redo.requested",
      tutorial_id: "tutorial-7",
      step_id: "make-sketch",
      step_number: 3,
      timestamp_ms: 1_700_000_000_000
    });
  });
});
