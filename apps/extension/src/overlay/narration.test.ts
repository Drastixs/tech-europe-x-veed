import { describe, expect, it, vi } from "vitest";
import { entryVoiceCue, NarrationPlayer, shouldAutoplayNarration, type AudioHandle } from "./narration";
import { tutorialPlanFixture } from "./test-fixtures";

function fakeAudio() {
  const handle: AudioHandle = {
    currentTime: 0,
    onended: null,
    onerror: null,
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn()
  };
  return handle;
}

describe("narration playback", () => {
  it("stops and rewinds previous audio before replacing it", async () => {
    const first = fakeAudio();
    const second = fakeAudio();
    const create = vi.fn().mockReturnValueOnce(first).mockReturnValueOnce(second);
    const player = new NarrationPlayer(create);

    await player.play("first.mp3");
    first.currentTime = 4;
    await player.play("second.mp3");

    expect(first.pause).toHaveBeenCalledOnce();
    expect(first.currentTime).toBe(0);
    expect(create).toHaveBeenNthCalledWith(2, "second.mp3");
  });

  it("falls back without rejecting when browser playback fails", async () => {
    const audio = fakeAudio();
    vi.mocked(audio.play).mockRejectedValue(new Error("autoplay blocked"));
    const statuses: string[] = [];
    const player = new NarrationPlayer(() => audio, (status) => statuses.push(status));

    await expect(player.play("voice.mp3")).resolves.toBeUndefined();
    expect(statuses).toContain("failed");
  });

  it("ignores a stale play result after interruption", async () => {
    let resolvePlay: (() => void) | undefined;
    const audio = fakeAudio();
    vi.mocked(audio.play).mockReturnValue(new Promise<void>((resolve) => {
      resolvePlay = resolve;
    }));
    const statuses: string[] = [];
    const player = new NarrationPlayer(() => audio, (status) => statuses.push(status));

    const pending = player.play("voice.mp3");
    player.stop();
    resolvePlay?.();
    await pending;

    expect(audio.pause).toHaveBeenCalledOnce();
    expect(statuses.at(-1)).toBe("idle");
  });

  it("uses entry cue timing and blocking metadata", () => {
    const step = tutorialPlanFixture.steps[0]!;
    expect(entryVoiceCue(step, "concise")?.blocking).toBe(true);
    expect(shouldAutoplayNarration(step, "concise")).toBe(true);

    const eventStep = structuredClone(step);
    eventStep.voice_cues[0]!.start_policy = "play_on_event";
    expect(shouldAutoplayNarration(eventStep, "concise")).toBe(false);
  });

  it("autoplays steps without explicit voice cues", () => {
    expect(shouldAutoplayNarration(tutorialPlanFixture.steps[1]!, "detailed")).toBe(true);
  });
});
