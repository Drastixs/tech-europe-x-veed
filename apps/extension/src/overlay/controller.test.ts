import { describe, expect, it } from "vitest";
import {
  hitTestNavigation,
  initialOverlayState,
  reduceOverlayState
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
    let state = reduceOverlayState(initialOverlayState, {
      type: "load_tutorial",
      steps: [
        { step_id: "one", text: "One" },
        { step_id: "two", text: "Two" },
        { step_id: "three", text: "Three" }
      ]
    });
    for (let index = 0; index < 20; index += 1) {
      state = reduceOverlayState(state, { type: "navigate", direction: "right" });
    }
    expect(state.step).toBe(3);
    for (let index = 0; index < 20; index += 1) {
      state = reduceOverlayState(state, { type: "navigate", direction: "left" });
    }
    expect(state.step).toBe(1);
  });

  it("arms takeover explicitly and disarms after takeover", () => {
    const armed = reduceOverlayState(initialOverlayState, { type: "arm_takeover" });
    expect(armed.takeoverArmed).toBe(true);
    const takenOver = reduceOverlayState(armed, { type: "takeover" });
    expect(takenOver.takeoverArmed).toBe(false);
  });

  it("hit-tests virtual clicks against navigation buttons", () => {
    const left = { left: 100, right: 140, top: 200, bottom: 240 };
    const right = { left: 144, right: 184, top: 200, bottom: 240 };
    expect(hitTestNavigation(120, 220, left, right)).toBe("left");
    expect(hitTestNavigation(160, 220, left, right)).toBe("right");
    expect(hitTestNavigation(90, 190, left, right)).toBeNull();
  });
});
