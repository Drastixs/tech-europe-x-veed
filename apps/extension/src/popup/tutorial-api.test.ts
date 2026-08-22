import { describe, expect, it, vi } from "vitest";
import { createTutorialFromVideo, TUTORIAL_PIPELINE_URL } from "./tutorial-api";

describe("tutorial video pipeline client", () => {
  it("posts a video URL to the combined analysis and planning endpoint", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ command: { type: "load_tutorial" } }), { status: 200 })
    );

    await expect(
      createTutorialFromVideo("https://youtu.be/tutorial", "tutorial-123", request)
    ).resolves.toEqual({ ok: true, tutorialId: "tutorial-123" });

    expect(request).toHaveBeenCalledWith(TUTORIAL_PIPELINE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_url: "https://youtu.be/tutorial",
        tutorial_id: "tutorial-123"
      })
    });
  });

  it("returns the backend error without throwing", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Video analysis failed" }), { status: 422 })
    );

    await expect(
      createTutorialFromVideo("https://youtu.be/tutorial", "tutorial-123", request)
    ).resolves.toEqual({ ok: false, message: "Video analysis failed" });
  });
});


