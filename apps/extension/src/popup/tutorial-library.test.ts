import { describe, expect, it, vi } from "vitest";
import { tutorialPlanFixture } from "../overlay/test-fixtures";
import {
  loadTutorialLibrary,
  saveTutorial,
  TUTORIAL_LIBRARY_KEY,
  tutorialTitle,
  type SavedTutorial
} from "./tutorial-library";

const savedTutorial = (tutorialId: string): SavedTutorial => ({
  tutorialId,
  videoUrl: `https://youtu.be/${tutorialId}`,
  title: "Select Sketch 1",
  createdAt: "2026-08-22T12:00:00.000Z",
  plan: { ...tutorialPlanFixture, tutorial_id: tutorialId }
});

describe("tutorial library", () => {
  it("uses the first tutorial goal as a concise title", () => {
    expect(tutorialTitle(tutorialPlanFixture)).toBe("Select Sketch 1");
  });

  it("stores the newest tutorial first and preserves earlier tutorials", async () => {
    let value: unknown = [savedTutorial("first")];
    const storage = {
      get: vi.fn(async () => ({ [TUTORIAL_LIBRARY_KEY]: value })),
      set: vi.fn(async (items: Record<string, unknown>) => {
        value = items[TUTORIAL_LIBRARY_KEY];
      })
    };

    await expect(saveTutorial(storage, savedTutorial("second"))).resolves.toEqual([
      savedTutorial("second"),
      savedTutorial("first")
    ]);
    await expect(loadTutorialLibrary(storage)).resolves.toHaveLength(2);
  });

  it("ignores malformed storage entries", async () => {
    const storage = {
      get: vi.fn(async () => ({ [TUTORIAL_LIBRARY_KEY]: [null, { tutorialId: "broken" }] })),
      set: vi.fn(async () => undefined)
    };

    await expect(loadTutorialLibrary(storage)).resolves.toEqual([]);
  });
});
