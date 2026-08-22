import { describe, expect, it } from "vitest";
import { isRelevantTakeoverKey } from "./takeover";

function keyboardEvent(key: string, modifiers: Partial<KeyboardEvent> = {}): KeyboardEvent {
  return { key, ctrlKey: false, metaKey: false, altKey: false, target: null, ...modifiers } as KeyboardEvent;
}

describe("takeover keyboard filtering", () => {
  it("recognizes modelling and editing input", () => {
    expect(isRelevantTakeoverKey(keyboardEvent("s"))).toBe(true);
    expect(isRelevantTakeoverKey(keyboardEvent("Enter"))).toBe(true);
    expect(isRelevantTakeoverKey(keyboardEvent("Delete"))).toBe(true);
  });

  it("ignores browser shortcuts and navigation keys outside fields", () => {
    expect(isRelevantTakeoverKey(keyboardEvent("r", { ctrlKey: true }))).toBe(false);
    expect(isRelevantTakeoverKey(keyboardEvent("ArrowLeft"))).toBe(false);
  });
});
