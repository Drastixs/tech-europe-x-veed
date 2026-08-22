import type {
  CaptureObservationCommand,
  ObservationCapturedEvent,
  ObservationFailedEvent,
  ViewportObservation
} from "../overlay/protocol";

export type CaptureTab = {
  id: number;
  windowId: number;
  url?: string;
};

export type CaptureDependencies = {
  captureVisibleTab: (windowId: number) => Promise<string>;
  readViewport: (tabId: number) => Promise<ViewportObservation>;
};

export async function captureObservation(
  command: CaptureObservationCommand,
  tab: CaptureTab | undefined,
  dependencies: CaptureDependencies
): Promise<ObservationCapturedEvent | ObservationFailedEvent> {
  if (!tab?.url?.startsWith("https://cad.onshape.com/documents/")) {
    return {
      type: "observation.failed",
      request_id: command.request_id,
      reason: "No active Onshape document tab is available"
    };
  }

  try {
    const [screenshot, viewport] = await Promise.all([
      dependencies.captureVisibleTab(tab.windowId),
      dependencies.readViewport(tab.id)
    ]);
    if (!screenshot.startsWith("data:image/")) throw new Error("Invalid screenshot data");
    if (!validViewport(viewport)) throw new Error("Invalid viewport dimensions");
    return {
      type: "observation.captured",
      request_id: command.request_id,
      screenshot_data_url: screenshot,
      viewport,
      url: tab.url
    };
  } catch (error) {
    return {
      type: "observation.failed",
      request_id: command.request_id,
      reason: error instanceof Error ? error.message : "Screenshot capture failed"
    };
  }
}

const validViewport = (viewport: ViewportObservation) =>
  Number.isFinite(viewport.width) && viewport.width > 0 &&
  Number.isFinite(viewport.height) && viewport.height > 0 &&
  Number.isFinite(viewport.device_pixel_ratio) && viewport.device_pixel_ratio > 0;
