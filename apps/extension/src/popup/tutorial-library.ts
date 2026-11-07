import { isTutorialPlan, type TutorialPlan } from "../overlay/protocol";

export const TUTORIAL_LIBRARY_KEY = "tutorialLibrary";

export type SavedTutorial = {
  tutorialId: string;
  videoUrl: string;
  title: string;
  createdAt: string;
  plan: TutorialPlan;
};

type StorageArea = {
  get: (key: string) => Promise<Record<string, unknown>>;
  set: (items: Record<string, unknown>) => Promise<void>;
};

const isSavedTutorial = (value: unknown): value is SavedTutorial => {
  if (!value || typeof value !== "object") return false;
  const tutorial = value as Partial<SavedTutorial>;
  return typeof tutorial.tutorialId === "string" &&
    typeof tutorial.videoUrl === "string" &&
    typeof tutorial.title === "string" &&
    typeof tutorial.createdAt === "string" &&
    isTutorialPlan(tutorial.plan) && tutorial.plan.tutorial_id === tutorial.tutorialId;
};

export const tutorialTitle = (plan: TutorialPlan) => {
  const firstGoal = plan.steps[0]?.goal.trim().replace(/[.!?]+$/, "");
  return firstGoal || "Onshape tutorial";
};

export async function loadTutorialLibrary(storage: StorageArea): Promise<SavedTutorial[]> {
  const stored = await storage.get(TUTORIAL_LIBRARY_KEY);
  const value = stored[TUTORIAL_LIBRARY_KEY];
  return Array.isArray(value) ? value.filter(isSavedTutorial) : [];
}

export async function saveTutorial(
  storage: StorageArea,
  tutorial: SavedTutorial
): Promise<SavedTutorial[]> {
  const existing = await loadTutorialLibrary(storage);
  const tutorials = [
    tutorial,
    ...existing.filter((item) => item.tutorialId !== tutorial.tutorialId)
  ];
  await storage.set({ [TUTORIAL_LIBRARY_KEY]: tutorials });
  return tutorials;
}
