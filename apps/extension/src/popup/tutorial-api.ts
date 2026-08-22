export const TUTORIAL_PIPELINE_URL = "http://127.0.0.1:8000/tutorials/from-video";

export type TutorialCreationResult =
  | { ok: true; tutorialId: string }
  | { ok: false; message: string };

const errorMessage = (value: unknown) => {
  if (typeof value === "string" && value.trim()) return value;
  if (value && typeof value === "object" && "detail" in value) {
    const detail = (value as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return "The tutorial pipeline could not process this video.";
};

export async function createTutorialFromVideo(
  videoUrl: string,
  tutorialId: string,
  request: typeof fetch = fetch
): Promise<TutorialCreationResult> {
  try {
    const response = await request(TUTORIAL_PIPELINE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_url: videoUrl, tutorial_id: tutorialId })
    });
    const body: unknown = await response.json().catch(() => undefined);
    if (!response.ok) return { ok: false, message: errorMessage(body) };
    return { ok: true, tutorialId };
  } catch {
    return {
      ok: false,
      message: "The local Onshape Assist relay is unavailable. Start it and try again."
    };
  }
}


