import { describe, expect, it, vi } from "vitest";
import { captureObservation, type CaptureDependencies } from "./capture";

const command = { type: "capture_observation" as const, request_id: "obs_1" };
const tab = { id: 7, windowId: 3, url: "https://cad.onshape.com/documents/demo/w/one/e/two" };

describe("captureObservation", () => {
  it("captures the active Onshape viewport with correlation metadata", async () => {
    const dependencies: CaptureDependencies = {
      captureVisibleTab: vi.fn().mockResolvedValue("data:image/png;base64,c2NyZWVu"),
      readViewport: vi.fn().mockResolvedValue({
        width: 1440,
        height: 900,
        device_pixel_ratio: 2
      })
    };

    const result = await captureObservation(command, tab, dependencies);

    expect(result).toEqual({
      type: "observation.captured",
      request_id: "obs_1",
      screenshot_data_url: "data:image/png;base64,c2NyZWVu",
      viewport: { width: 1440, height: 900, device_pixel_ratio: 2 },
      url: tab.url
    });
    expect(dependencies.captureVisibleTab).toHaveBeenCalledWith(3);
    expect(dependencies.readViewport).toHaveBeenCalledWith(7);
  });

  it("refuses to capture a non-Onshape tab", async () => {
    const dependencies: CaptureDependencies = {
      captureVisibleTab: vi.fn(),
      readViewport: vi.fn()
    };

    const result = await captureObservation(command, {
      id: 7,
      windowId: 3,
      url: "https://example.com"
    }, dependencies);

    expect(result.type).toBe("observation.failed");
    expect(dependencies.captureVisibleTab).not.toHaveBeenCalled();
  });

  it("returns a correlated failure when capture fails", async () => {
    const result = await captureObservation(command, tab, {
      captureVisibleTab: vi.fn().mockRejectedValue(new Error("Permission denied")),
      readViewport: vi.fn().mockResolvedValue({ width: 1440, height: 900, device_pixel_ratio: 1 })
    });

    expect(result).toEqual({
      type: "observation.failed",
      request_id: "obs_1",
      reason: "Permission denied"
    });
  });
});
