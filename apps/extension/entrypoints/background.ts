import { captureObservation } from "../src/computer-use/capture";
import {
  isCaptureObservationCommand,
  isDemoEnvelope,
  isTutorialStepStatusCommand,
  type TutorialPlan,
  type TutorialStepStatusCommand
} from "../src/overlay/protocol";
import { createTutorialFromVideo } from "../src/popup/tutorial-api";

const RELAY_URL = "ws://127.0.0.1:8000/ws/extension";
const ONSHAPE_URL = "https://cad.onshape.com/documents/*";
const KEEPALIVE_INTERVAL_MS = 20_000;
const LEARNER_OBSERVATION_INTERVAL_MS = 1_000;
const DEMONSTRATE_STEP_URL = "http://127.0.0.1:8000/tutorials/demonstrate-step";

export default defineBackground(() => {
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let keepaliveTimer: ReturnType<typeof setInterval> | undefined;
  let registeredTabId: number | undefined;
  let tutorialPlan: TutorialPlan | null = null;
  let tutorialStep = 1;
  let runtimeSession: TutorialStepStatusCommand | null = null;
  let observationTimer: ReturnType<typeof setInterval> | undefined;
  let observationPending = false;
  let stopped = false;

  const activeOnshapeTab = async () => {
    const [tab] = await browser.tabs.query({ active: true, currentWindow: true, url: ONSHAPE_URL });
    return tab;
  };

  const registerTab = async (tabId: number) => {
    const tab = await browser.tabs.get(tabId).catch(() => undefined);
    if (!tab?.active || !tab.url?.startsWith("https://cad.onshape.com/documents/")) return;
    registeredTabId = tabId;
  };

  const sendToRegisteredTab = async (command: unknown) => {
    let tabId = registeredTabId;
    if (tabId !== undefined) {
      const tab = await browser.tabs.get(tabId).catch(() => undefined);
      if (!tab?.active || !tab.url?.startsWith("https://cad.onshape.com/documents/")) {
        tabId = undefined;
      }
    }
    if (tabId === undefined) {
      const tab = await activeOnshapeTab();
      tabId = tab?.id;
      registeredTabId = tabId;
    }
    if (tabId !== undefined) {
      await browser.tabs
        .sendMessage(tabId, { channel: "onshape-assist", command })
        .catch(() => undefined);
    }
  };

  const sendEvent = (event: unknown) => {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(event));
  };

  const sendExtensionEvent = (event: unknown, tabId?: number) => {
    sendEvent({
      version: 1,
      type: "extension.event",
      tab_id: tabId ?? registeredTabId ?? null,
      event
    });
  };

  const stopLearnerMonitoring = () => {
    if (observationTimer) clearInterval(observationTimer);
    observationTimer = undefined;
    observationPending = false;
  };

  const captureLearnerObservation = async () => {
    if (observationPending || runtimeSession?.status !== "learner_attempt") return;
    observationPending = true;
    try {
      const tab = await activeOnshapeTab();
      const requestId = `learner_${crypto.randomUUID()}`;
      const captured = await captureObservation(
        { type: "capture_observation", request_id: requestId },
        tab?.id !== undefined && tab.windowId !== undefined
          ? { id: tab.id, windowId: tab.windowId, url: tab.url }
          : undefined,
        {
          captureVisibleTab: (windowId) =>
            browser.tabs.captureVisibleTab(windowId, { format: "png" }),
          readViewport: async (tabId) => {
            const response = await browser.tabs.sendMessage(tabId, {
              channel: "onshape-assist",
              type: "viewport.request"
            });
            return response as { width: number; height: number; device_pixel_ratio: number };
          }
        }
      );
      sendExtensionEvent({
        ...captured,
        type: captured.type === "observation.captured"
          ? "learner.observation.captured"
          : "learner.observation.failed",
        session_id: runtimeSession.session_id,
        tutorial_id: runtimeSession.tutorial_id,
        step_id: runtimeSession.step_id,
        timestamp_ms: Date.now()
      }, tab?.id);
    } finally {
      observationPending = false;
    }
  };

  const startLearnerMonitoring = () => {
    stopLearnerMonitoring();
    observationTimer = setInterval(() => {
      void captureLearnerObservation();
    }, LEARNER_OBSERVATION_INTERVAL_MS);
  };

  const applyRuntimeStatus = (command: TutorialStepStatusCommand) => {
    runtimeSession = command;
    if (command.status === "learner_attempt") startLearnerMonitoring();
    else stopLearnerMonitoring();
  };

  const runTutorialStep = async (requestedStep?: number, requestedStepId?: string) => {
    if (!tutorialPlan) throw new Error("No tutorial plan is loaded");
    const matchingIndex = requestedStepId
      ? tutorialPlan.steps.findIndex((step) => step.step_id === requestedStepId)
      : -1;
    const step = matchingIndex >= 0 ? matchingIndex + 1 : requestedStep ?? tutorialStep;
    const plannedStep = tutorialPlan.steps[step - 1];
    const tab = await activeOnshapeTab();
    if (!plannedStep) throw new Error("The requested tutorial step does not exist");
    if (!tab?.url) throw new Error("No active Onshape document tab is available");
    tutorialStep = step;
    stopLearnerMonitoring();

    try {
      const response = await fetch(DEMONSTRATE_STEP_URL, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          plan: tutorialPlan,
          step,
          document_url: tab.url,
          execute: true
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Step demonstration failed (${response.status})`);
      }
    } catch (error) {
      await sendToRegisteredTab({
        type: "tutorial_step_status",
        session_id: runtimeSession?.session_id ?? `failed-${tutorialPlan.tutorial_id}`,
        tutorial_id: tutorialPlan.tutorial_id,
        step_id: plannedStep.step_id,
        status: "failed",
        message: error instanceof Error ? error.message : "Step demonstration failed"
      } satisfies TutorialStepStatusCommand);
      throw error;
    }
  };

  const connect = () => {
    if (stopped) return;
    socket = new WebSocket(RELAY_URL);

    socket.addEventListener("open", async () => {
      const tab = await activeOnshapeTab();
      if (tab?.id !== undefined) registeredTabId = tab.id;
      sendEvent({
        version: 1,
        type: "extension.hello",
        tab: tab ? { id: tab.id, url: tab.url } : null
      });
      keepaliveTimer = setInterval(() => {
        sendEvent({ version: 1, type: "extension.keepalive" });
      }, KEEPALIVE_INTERVAL_MS);
    });

    socket.addEventListener("message", (event) => {
      try {
        const envelope = JSON.parse(String(event.data));
        if (!isDemoEnvelope(envelope)) return;
        const command = envelope.command;
        if (command.type === "load_tutorial") {
          tutorialPlan = command.plan;
          tutorialStep = command.step ?? 1;
          runtimeSession = null;
          stopLearnerMonitoring();
          void sendToRegisteredTab(command)
            .then(() => runTutorialStep(tutorialStep))
            .catch(() => undefined);
          return;
        }
        if (isTutorialStepStatusCommand(command)) {
          applyRuntimeStatus(command);
          void sendToRegisteredTab(command);
          return;
        }
        if (isCaptureObservationCommand(command)) {
          void (async () => {
            const tab = await activeOnshapeTab();
            const captured = await captureObservation(
              command,
              tab?.id !== undefined && tab.windowId !== undefined
                ? { id: tab.id, windowId: tab.windowId, url: tab.url }
                : undefined,
              {
                captureVisibleTab: (windowId) =>
                  browser.tabs.captureVisibleTab(windowId, { format: "png" }),
                readViewport: async (tabId) => {
                  const response = await browser.tabs.sendMessage(tabId, {
                    channel: "onshape-assist",
                    type: "viewport.request"
                  });
                  return response as { width: number; height: number; device_pixel_ratio: number };
                }
              }
            );
            sendExtensionEvent(captured, tab?.id);
          })();
          return;
        }
        void sendToRegisteredTab(command);
      } catch {
        // Ignore malformed local relay traffic.
      }
    });

    socket.addEventListener("close", () => {
      if (keepaliveTimer) clearInterval(keepaliveTimer);
      keepaliveTimer = undefined;
      if (!stopped) reconnectTimer = setTimeout(connect, 1000);
    });
  };

  browser.runtime.onMessage.addListener((message: unknown, sender) => {
    const candidate = message as {
      channel?: string;
      type?: string;
      event?: unknown;
      videoUrl?: unknown;
    };
    if (
      candidate.channel === "onshape-assist" &&
      candidate.type === "tutorial.create" &&
      typeof candidate.videoUrl === "string"
    ) {
      return createTutorialFromVideo(candidate.videoUrl, crypto.randomUUID());
    }
    if (candidate.channel !== "onshape-assist" || sender.tab?.id === undefined) return;
    if (candidate.type === "tab.ready") void registerTab(sender.tab.id);
    if (candidate.event) {
      const localEvent = candidate.event as { type?: string; step_id?: string };
      if (localEvent.type === "tutorial.step.redo.requested") {
        return runTutorialStep(undefined, localEvent.step_id);
      }
      if (localEvent.type === "user.takeover" && runtimeSession) {
        stopLearnerMonitoring();
        void sendToRegisteredTab({ ...runtimeSession, status: "restoring", message: null });
        sendExtensionEvent({
          ...localEvent,
          session_id: runtimeSession.session_id,
          tutorial_id: runtimeSession.tutorial_id,
          step_id: runtimeSession.step_id
        }, sender.tab.id);
        return;
      }
      sendExtensionEvent(candidate.event, sender.tab.id);
    }
  });

  browser.tabs.onActivated.addListener(({ tabId }) => {
    void registerTab(tabId);
  });

  browser.runtime.onInstalled.addListener(() => {
    void browser.action.setBadgeText({ text: "ON" });
    void browser.action.setBadgeBackgroundColor({ color: "#2dd4bf" });
  });

  browser.runtime.onSuspend.addListener(() => {
    stopped = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (keepaliveTimer) clearInterval(keepaliveTimer);
    stopLearnerMonitoring();
    socket?.close();
  });

  connect();
});
