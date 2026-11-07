import { captureObservation } from "../src/computer-use/capture";
import {
  isCaptureObservationCommand,
  isDemoEnvelope,
  isExecuteActionCommand,
  isTutorialStepStatusCommand,
  type ActionCompletedEvent,
  type ExecuteActionCommand,
  type TutorialPlan,
  type TutorialStepStatusCommand
} from "../src/overlay/protocol";
import { createTutorialFromVideo } from "../src/popup/tutorial-api";
import {
  loadTutorialLibrary,
  saveTutorial,
  tutorialTitle
} from "../src/popup/tutorial-library";
import { completedUndoCount } from "../src/computer-use/undo";

const RELAY_URL = "ws://127.0.0.1:8000/ws/extension";
const ONSHAPE_URL = "https://cad.onshape.com/documents/*";
const KEEPALIVE_INTERVAL_MS = 20_000;
const LEARNER_OBSERVATION_INTERVAL_MS = 1_000;
const DEMONSTRATE_STEP_URL = "http://127.0.0.1:8000/computer-use/demonstrate-step";

type CdpDebuggee = { tabId: number };
type CdpApi = {
  attach: (target: CdpDebuggee, version: string) => Promise<void>;
  detach: (target: CdpDebuggee) => Promise<void>;
  sendCommand: (
    target: CdpDebuggee,
    method: string,
    parameters?: Record<string, unknown>
  ) => Promise<unknown>;
};

const cdp = () => (globalThis as unknown as { chrome: { debugger: CdpApi } }).chrome.debugger;

const isCdpPointerAction = (command: ExecuteActionCommand) =>
  command.action.action_type === "click" ||
  command.action.action_type === "double_click" ||
  command.action.action_type === "selection";

const executeCdpPointerAction = async (
  tabId: number,
  command: ExecuteActionCommand
): Promise<ActionCompletedEvent> => {
  const debuggee = { tabId };
  const action = command.action;
  const namedButton = action.action_type === "click" || action.action_type === "double_click"
    ? action.parameters.button
    : "primary";
  const button = namedButton === "secondary" ? "right" : namedButton === "middle" ? "middle" : "left";
  const clickTotal = action.action_type === "double_click" ? 2 : 1;

  try {
    await cdp().attach(debuggee, "1.3");
    await cdp().sendCommand(debuggee, "Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: command.target.x,
      y: command.target.y
    });
    for (let clickCount = 1; clickCount <= clickTotal; clickCount += 1) {
      await cdp().sendCommand(debuggee, "Input.dispatchMouseEvent", {
        type: "mousePressed",
        x: command.target.x,
        y: command.target.y,
        button,
        buttons: button === "left" ? 1 : button === "right" ? 2 : 4,
        clickCount
      });
      await cdp().sendCommand(debuggee, "Input.dispatchMouseEvent", {
        type: "mouseReleased",
        x: command.target.x,
        y: command.target.y,
        button,
        buttons: 0,
        clickCount
      });
      if (clickCount < clickTotal) {
        const interval = action.action_type === "double_click" ? action.parameters.interval_ms : 0;
        await new Promise((resolve) => setTimeout(resolve, interval));
      }
    }
    return {
      type: "action.completed",
      action_id: command.action_id,
      success: true,
      reason: null,
      element_description: `CDP click at (${command.target.x}, ${command.target.y})`
    };
  } catch (error) {
    return {
      type: "action.failed",
      action_id: command.action_id,
      success: false,
      reason: error instanceof Error ? error.message : "CDP pointer execution failed",
      element_description: null
    };
  } finally {
    await cdp().detach(debuggee).catch(() => undefined);
  }
};

const executeCdpUndo = async (tabId: number, count: number) => {
  if (count <= 0) return;
  const debuggee = { tabId };
  try {
    await cdp().attach(debuggee, "1.3");
    for (let index = 0; index < count; index += 1) {
      await cdp().sendCommand(debuggee, "Input.dispatchKeyEvent", {
        type: "rawKeyDown",
        key: "z",
        code: "KeyZ",
        windowsVirtualKeyCode: 90,
        nativeVirtualKeyCode: 90,
        modifiers: 2
      });
      await cdp().sendCommand(debuggee, "Input.dispatchKeyEvent", {
        type: "keyUp",
        key: "z",
        code: "KeyZ",
        windowsVirtualKeyCode: 90,
        nativeVirtualKeyCode: 90,
        modifiers: 2
      });
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
  } finally {
    await cdp().detach(debuggee).catch(() => undefined);
  }
};

const dispatchCdpKey = async (
  debuggee: CdpDebuggee,
  key: string,
  code: string,
  virtualKeyCode: number,
  modifiers = 0
) => {
  await cdp().sendCommand(debuggee, "Input.dispatchKeyEvent", {
    type: "rawKeyDown",
    key,
    code,
    windowsVirtualKeyCode: virtualKeyCode,
    nativeVirtualKeyCode: virtualKeyCode,
    modifiers
  });
  await cdp().sendCommand(debuggee, "Input.dispatchKeyEvent", {
    type: "keyUp",
    key,
    code,
    windowsVirtualKeyCode: virtualKeyCode,
    nativeVirtualKeyCode: virtualKeyCode,
    modifiers
  });
};

const executeCdpKeyboardAction = async (
  tabId: number,
  command: ExecuteActionCommand
): Promise<ActionCompletedEvent> => {
  const debuggee = { tabId };
  const action = command.action;
  try {
    await cdp().attach(debuggee, "1.3");
    if (action.action_type === "type") {
      if (action.parameters.clear_existing) {
        await dispatchCdpKey(debuggee, "a", "KeyA", 65, 2);
        await dispatchCdpKey(debuggee, "Backspace", "Backspace", 8);
      }
      await cdp().sendCommand(debuggee, "Input.insertText", { text: action.parameters.text });
      if (action.parameters.submit) {
        await dispatchCdpKey(debuggee, "Enter", "Enter", 13);
      }
    } else if (action.action_type === "keypress") {
      const modifierMask = action.parameters.modifiers.reduce((mask, modifier) =>
        mask | (modifier === "alt" ? 1 : modifier === "control" ? 2 : modifier === "meta" ? 4 : 8), 0);
      const key = action.parameters.key;
      const code = key.length === 1 ? `Key${key.toUpperCase()}` : key;
      const virtualKeyCode = key.length === 1 ? key.toUpperCase().charCodeAt(0) : key === "Enter" ? 13 : 0;
      for (let index = 0; index < action.parameters.repeat; index += 1) {
        await dispatchCdpKey(debuggee, key, code, virtualKeyCode, modifierMask);
      }
    } else {
      throw new Error("Unsupported CDP keyboard action");
    }
    return {
      type: "action.completed",
      action_id: command.action_id,
      success: true,
      reason: null,
      element_description: "Active Onshape keyboard target"
    };
  } catch (error) {
    return {
      type: "action.failed",
      action_id: command.action_id,
      success: false,
      reason: error instanceof Error ? error.message : "CDP keyboard execution failed",
      element_description: null
    };
  } finally {
    await cdp().detach(debuggee).catch(() => undefined);
  }
};

export default defineBackground(() => {
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let keepaliveTimer: ReturnType<typeof setInterval> | undefined;
  let registeredTabId: number | undefined;
  let tutorialPlan: TutorialPlan | null = null;
  let tutorialStep = 1;
  let runtimeSession: TutorialStepStatusCommand | null = null;
  const completedActionsByStep = new Map<string, number>();
  let observationTimer: ReturnType<typeof setInterval> | undefined;
  let observationPending = false;
  let stopped = false;

  const activeOnshapeTab = async () => {
    const tabs = await browser.tabs.query({ url: ONSHAPE_URL });
    return tabs.find((tab) => tab.id === registeredTabId) ??
      tabs.find((tab) => tab.active) ??
      tabs[0];
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
    const sessionId = runtimeSession?.session_id ?? `demo-${tutorialPlan.tutorial_id}`;
    const demonstratingStatus: TutorialStepStatusCommand = {
      type: "tutorial_step_status",
      session_id: sessionId,
      tutorial_id: tutorialPlan.tutorial_id,
      step_id: plannedStep.step_id,
      status: "demonstrating",
      message: null
    };
    applyRuntimeStatus(demonstratingStatus);
    await sendToRegisteredTab(demonstratingStatus);

    try {
      const response = await fetch(DEMONSTRATE_STEP_URL, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          step: plannedStep,
          execute: true
        })
      });
      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Step demonstration failed (${response.status})`);
      }
      const result = await response.json() as {
        success?: boolean;
        reason?: string | null;
        completed_actions?: number;
      };
      completedActionsByStep.set(plannedStep.step_id, result.completed_actions ?? 0);
      if (!result.success) throw new Error(result.reason || "Step demonstration failed");

      const visibleStatus: TutorialStepStatusCommand = {
        ...demonstratingStatus,
        status: "demo_visible"
      };
      applyRuntimeStatus(visibleStatus);
      await sendToRegisteredTab(visibleStatus);
      await sendToRegisteredTab({ type: "arm_takeover" });
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
          completedActionsByStep.clear();
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
        if (isExecuteActionCommand(command) && isCdpPointerAction(command)) {
          void (async () => {
            const tab = await activeOnshapeTab();
            const result = tab?.id === undefined
              ? {
                  type: "action.failed" as const,
                  action_id: command.action_id,
                  success: false,
                  reason: "No active Onshape tab is available for CDP execution",
                  element_description: null
                }
              : await executeCdpPointerAction(tab.id, command);
            sendExtensionEvent(result, tab?.id);
          })();
          return;
        }
        if (
          isExecuteActionCommand(command) &&
          (command.action.action_type === "type" || command.action.action_type === "keypress")
        ) {
          void (async () => {
            const tab = await activeOnshapeTab();
            const result = tab?.id === undefined
              ? {
                  type: "action.failed" as const,
                  action_id: command.action_id,
                  success: false,
                  reason: "No active Onshape tab is available for CDP keyboard execution",
                  element_description: null
                }
              : await executeCdpKeyboardAction(tab.id, command);
            sendExtensionEvent(result, tab?.id);
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
      tutorialId?: unknown;
    };
    if (
      candidate.channel === "onshape-assist" &&
      candidate.type === "tutorial.create" &&
      typeof candidate.videoUrl === "string"
    ) {
      return (async () => {
        const result = await createTutorialFromVideo(candidate.videoUrl as string, crypto.randomUUID());
        if (!result.ok) return result;
        const tutorial = {
          tutorialId: result.tutorialId,
          videoUrl: candidate.videoUrl as string,
          title: tutorialTitle(result.plan),
          createdAt: new Date().toISOString(),
          plan: result.plan
        };
        await saveTutorial(browser.storage.local, tutorial);
        return { ...result, tutorial };
      })();
    }
    if (candidate.channel === "onshape-assist" && candidate.type === "tutorial.list") {
      return loadTutorialLibrary(browser.storage.local)
        .then((tutorials) => ({ ok: true as const, tutorials }))
        .catch(() => ({ ok: false as const, message: "Saved tutorials could not be loaded." }));
    }
    if (
      candidate.channel === "onshape-assist" &&
      candidate.type === "tutorial.replay" &&
      typeof candidate.tutorialId === "string"
    ) {
      return (async () => {
        const tutorials = await loadTutorialLibrary(browser.storage.local);
        const tutorial = tutorials.find((item) => item.tutorialId === candidate.tutorialId);
        if (!tutorial) return { ok: false as const, message: "That saved tutorial is no longer available." };
        tutorialPlan = tutorial.plan;
        tutorialStep = 1;
        runtimeSession = null;
        completedActionsByStep.clear();
        stopLearnerMonitoring();
        await sendToRegisteredTab({ type: "load_tutorial", plan: tutorial.plan, step: 1 });
        await runTutorialStep(1);
        return { ok: true as const };
      })().catch((error) => ({
        ok: false as const,
        message: error instanceof Error ? error.message : "The tutorial could not be replayed."
      }));
    }
    if (candidate.channel !== "onshape-assist" || sender.tab?.id === undefined) return;
    if (candidate.type === "tab.ready") void registerTab(sender.tab.id);
    if (candidate.event) {
      const localEvent = candidate.event as { type?: string; step_id?: string };
      if (
        localEvent.type === "tutorial.step.redo.requested"
      ) {
        return (async () => {
          const step = tutorialPlan?.steps.find((candidate) => candidate.step_id === localEvent.step_id);
          if (!step) throw new Error("The requested tutorial step does not exist");
          const undoCount = completedUndoCount(
            step,
            completedActionsByStep.get(step.step_id) ?? 0
          );
          await executeCdpUndo(sender.tab!.id!, undoCount);
          completedActionsByStep.set(step.step_id, 0);
          await runTutorialStep(undefined, localEvent.step_id);
        })();
      }
      if (localEvent.type === "tutorial.step.requested") {
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
