export type IntervalClock = Pick<typeof globalThis, "setInterval" | "clearInterval">;

export class LearnerObservationMonitor {
  private interval: ReturnType<typeof setInterval> | undefined;
  private capturePending = false;

  constructor(
    private readonly capture: () => Promise<void>,
    private readonly clock: IntervalClock = globalThis
  ) {}

  start(): void {
    this.stop();
    this.interval = this.clock.setInterval(() => {
      void this.captureOnce();
    }, 1_000);
  }

  stop(): void {
    if (this.interval) this.clock.clearInterval(this.interval);
    this.interval = undefined;
    this.capturePending = false;
  }

  private async captureOnce(): Promise<void> {
    if (this.capturePending) return;
    this.capturePending = true;
    try {
      await this.capture();
    } finally {
      this.capturePending = false;
    }
  }
}
