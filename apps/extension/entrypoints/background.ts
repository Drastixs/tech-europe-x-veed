import { captureObservation } from "../src/computer-use/capture";
import {
  isCaptureObservationCommand,
  isDemoEnvelope
} from "../src/overlay/protocol";

const RELAY_URL = "ws://127.0.0.1:8000/ws/extension";
const ONSHAPE_URL = "https://cad.onshape.com/documents/*";
const KEEPALIVE_INTERVAL_MS = 20_000;

export default defineBackground(() => {
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let keepaliveTimer: ReturnType<typeof setInterval> | undefined;
  let registeredTabId: number | undefined;
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
    const candidate = message as { channel?: string; type?: string; event?: unknown };
    if (candidate.channel !== "onshape-assist" || sender.tab?.id === undefined) return;
    if (candidate.type === "tab.ready") void registerTab(sender.tab.id);
    if (candidate.event) sendExtensionEvent(candidate.event, sender.tab.id);
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
    socket?.close();
  });

  connect();
});
