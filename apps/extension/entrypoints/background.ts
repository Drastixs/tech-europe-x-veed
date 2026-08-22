import { isDemoEnvelope } from "../src/overlay/protocol";
import { createTutorialFromVideo } from "../src/popup/tutorial-api";

const RELAY_URL = "ws://127.0.0.1:8000/ws/extension";
const ONSHAPE_URL = "https://cad.onshape.com/documents/*";

export default defineBackground(() => {
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
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
    });

    socket.addEventListener("message", (event) => {
      try {
        const envelope = JSON.parse(String(event.data));
        if (isDemoEnvelope(envelope)) void sendToRegisteredTab(envelope.command);
      } catch {
        // Ignore malformed local relay traffic.
      }
    });

    socket.addEventListener("close", () => {
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
      sendEvent({
        version: 1,
        type: "extension.event",
        tab_id: sender.tab.id,
        event: candidate.event
      });
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
    socket?.close();
  });

  connect();
});
