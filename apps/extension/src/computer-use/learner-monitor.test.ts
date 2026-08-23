import { describe, expect, it, vi } from "vitest";
import { LearnerObservationMonitor } from "./learner-monitor";

describe("LearnerObservationMonitor", () => {
  it("captures at one-second intervals only while active", async () => {
    vi.useFakeTimers();
    const capture = vi.fn().mockResolvedValue(undefined);
    const monitor = new LearnerObservationMonitor(capture);

    monitor.start();
    await vi.advanceTimersByTimeAsync(3_000);
    expect(capture).toHaveBeenCalledTimes(3);

    monitor.stop();
    await vi.advanceTimersByTimeAsync(3_000);
    expect(capture).toHaveBeenCalledTimes(3);
    vi.useRealTimers();
  });

  it("does not overlap a slow screenshot capture", async () => {
    vi.useFakeTimers();
    let finishCapture: (() => void) | undefined;
    const capture = vi.fn().mockImplementation(
      () => new Promise<void>((resolve) => { finishCapture = resolve; })
    );
    const monitor = new LearnerObservationMonitor(capture);

    monitor.start();
    await vi.advanceTimersByTimeAsync(3_000);
    expect(capture).toHaveBeenCalledOnce();

    finishCapture?.();
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(capture).toHaveBeenCalledTimes(2);
    monitor.stop();
    vi.useRealTimers();
  });
});
