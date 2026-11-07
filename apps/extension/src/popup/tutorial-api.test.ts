import { describe, expect, it, vi } from "vitest";
import { tutorialPlanFixture } from "../overlay/test-fixtures";
import { createTutorialFromVideo, TUTORIAL_PIPELINE_URL } from "./tutorial-api";

const responsePlan = { ...tutorialPlanFixture, tutorial_id: "tutorial-123" };

describe("tutorial video pipeline client", () => {
  it("posts a video URL to the combined analysis and planning endpoint", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({
        version: 1,
        sequence: 1,
        sent_at: "2026-08-22T12:00:00Z",
        command: { type: "load_tutorial", plan: responsePlan, step: 1 }
      }), { status: 200 })
    );

    await expect(
      createTutorialFromVideo("https://youtu.be/tutorial", "tutorial-123", request)
    ).resolves.toEqual({
      ok: true,
      tutorialId: "tutorial-123",
      plan: responsePlan
    });

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

  it("rejects a successful response without a runnable plan", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ command: { type: "load_tutorial" } }), { status: 200 })
    );

    await expect(
      createTutorialFromVideo("https://youtu.be/tutorial", "tutorial-123", request)
    ).resolves.toEqual({
      ok: false,
      message: "The tutorial pipeline returned an invalid tutorial plan."
    });
  });

  it("rejects a plan for a different tutorial", async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({
        version: 1,
        sequence: 1,
        sent_at: "2026-08-22T12:00:00Z",
        command: { type: "load_tutorial", plan: tutorialPlanFixture, step: 1 }
      }), { status: 200 })
    );

    await expect(
      createTutorialFromVideo("https://youtu.be/tutorial", "tutorial-123", request)
    ).resolves.toEqual({
      ok: false,
      message: "The tutorial pipeline returned the wrong tutorial plan."
    });
  });
});
