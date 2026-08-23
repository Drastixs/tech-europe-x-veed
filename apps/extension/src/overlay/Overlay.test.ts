import { describe, expect, it } from "vitest";
import { createStepRedoRequestedEvent, runtimeStatusText } from "./Overlay";

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

describe("overlay runtime status", () => {
  it("gives every runtime state a textual status", () => {
    expect(runtimeStatusText("demonstrating", null)).toBe("Showing the next step…");
    expect(runtimeStatusText("demo_visible", null)).toBe("Click when you’re ready to try.");
    expect(runtimeStatusText("restoring", null)).toBe("Resetting the demo state…");
    expect(runtimeStatusText("waiting", null)).toBe("Waiting for the next step…");
    expect(runtimeStatusText("learner_attempt", null)).toBe("Your turn.");
    expect(runtimeStatusText("validating", null)).toBe("Checking your result…");
    expect(runtimeStatusText("complete", null)).toBe("Step complete.");
    expect(runtimeStatusText("paused", "Waiting for a dimension.")).toBe("Waiting for a dimension.");
    expect(runtimeStatusText("failed", "Target not found.")).toBe("Target not found.");
  });
});
