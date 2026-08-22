import { describe, expect, it } from "vitest";
import {
  directionForKey,
  hitTestNavigation,
  initialOverlayState,
  reduceOverlayState,
  TOTAL_STEPS
} from "./controller";

describe("overlay controller", () => {
  it("hides guidance but keeps navigation available after takeover", () => {
    const state = reduceOverlayState(initialOverlayState, { type: "takeover" });
    expect(state.guidanceVisible).toBe(false);
    expect(state.sessionVisible).toBe(true);
  });

  it("restores guidance when the virtual cursor moves", () => {
    const takenOver = reduceOverlayState(initialOverlayState, { type: "takeover" });
    const state = reduceOverlayState(takenOver, { type: "move", x: 42, y: 84 });
    expect(state).toMatchObject({ guidanceVisible: true, x: 42, y: 84 });
  });

  it("clamps navigation within tutorial bounds", () => {
    let state = initialOverlayState;
    for (let index = 0; index < 20; index += 1) {
      state = reduceOverlayState(state, { type: "navigate", direction: "right" });
    }
    expect(state.step).toBe(TOTAL_STEPS);
    for (let index = 0; index < 20; index += 1) {
      state = reduceOverlayState(state, { type: "navigate", direction: "left" });
    }
    expect(state.step).toBe(1);
  });

  it("maps only left and right arrow keys", () => {
    expect(directionForKey("ArrowLeft")).toBe("left");
    expect(directionForKey("ArrowRight")).toBe("right");
    expect(directionForKey("Enter")).toBeNull();
  });

  it("hit-tests virtual clicks against navigation buttons", () => {
    const left = { left: 100, right: 140, top: 200, bottom: 240 };
    const right = { left: 144, right: 184, top: 200, bottom: 240 };
    expect(hitTestNavigation(120, 220, left, right)).toBe("left");
    expect(hitTestNavigation(160, 220, left, right)).toBe("right");
    expect(hitTestNavigation(90, 190, left, right)).toBeNull();
  });
});
