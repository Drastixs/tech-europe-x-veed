import type { TutorialStep, VoiceCue } from "./protocol";
import type { NarrationMode } from "./controller";

export type PlaybackStatus = "idle" | "loading" | "playing" | "failed";

export type AudioHandle = {
  currentTime: number;
  onended: ((event: Event) => void) | null;
  onerror: ((event: Event | string) => void) | null;
  play: () => Promise<void>;
  pause: () => void;
};

export type AudioFactory = (url: string) => AudioHandle;

export const browserAudioFactory: AudioFactory = (url) => new Audio(url);

export class NarrationPlayer {
  private audio: AudioHandle | null = null;
  private revision = 0;

  constructor(
    private readonly createAudio: AudioFactory = browserAudioFactory,
    private readonly onStatus: (status: PlaybackStatus) => void = () => undefined
  ) {}

  async play(url: string): Promise<void> {
    this.stop();
    const revision = this.revision;
    const audio = this.createAudio(url);
    this.audio = audio;
    audio.onended = () => {
      if (revision === this.revision) this.finish("idle");
    };
    audio.onerror = () => {
      if (revision === this.revision) this.finish("failed");
    };
    this.onStatus("loading");

    try {
      await audio.play();
      if (revision === this.revision) this.onStatus("playing");
    } catch {
      if (revision === this.revision) this.finish("failed");
    }
  }

  stop(): void {
    this.revision += 1;
    if (this.audio) {
      this.audio.onended = null;
      this.audio.onerror = null;
      this.audio.pause();
      this.audio.currentTime = 0;
      this.audio = null;
    }
    this.onStatus("idle");
  }

  private finish(status: PlaybackStatus): void {
    this.audio = null;
    this.onStatus(status);
  }
}

export function entryVoiceCue(step: TutorialStep, mode: NarrationMode): VoiceCue | null {
  return step.voice_cues.find((cue) => {
    const matchesVariant = cue.variant === "both" || cue.variant === mode;
    const matchesPhase = ["before_step", "before_action", "during_action"].includes(cue.phase);
    return matchesVariant && matchesPhase;
  }) ?? null;
}

export function shouldAutoplayNarration(step: TutorialStep, mode: NarrationMode): boolean {
  const cue = entryVoiceCue(step, mode);
  if (!cue) return true;
  return cue.start_policy === "play_before_motion" || cue.start_policy === "play_with_motion";
}
