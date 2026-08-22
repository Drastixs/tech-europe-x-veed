import { isDemoEnvelope } from "../src/overlay/protocol";

const RELAY_URL = "ws://127.0.0.1:8000/ws/extension";
const ONSHAPE_URL = "https://cad.onshape.com/documents/*";

export default defineBackground(() => {
  let socket: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

  const broadcastToOnshapeTabs = async (command: unknown) => {
    const tabs = await browser.tabs.query({ url: ONSHAPE_URL });
    await Promise.all(
      tabs
        .filter((tab) => tab.id !== undefined)
        .map((tab) =>
          browser.tabs
            .sendMessage(tab.id!, { channel: "onshape-assist", command })
            .catch(() => undefined)
        )
    );
  };

  const connect = () => {
    socket = new WebSocket(RELAY_URL);

    socket.addEventListener("message", (event) => {
      try {
        const envelope = JSON.parse(String(event.data));
        if (isDemoEnvelope(envelope)) void broadcastToOnshapeTabs(envelope.command);
      } catch {
        // Ignore malformed local relay traffic.
      }
    });

    socket.addEventListener("close", () => {
      reconnectTimer = setTimeout(connect, 1000);
    });
  };

  browser.runtime.onInstalled.addListener(() => {
    void browser.action.setBadgeText({ text: "ON" });
    void browser.action.setBadgeBackgroundColor({ color: "#2dd4bf" });
  });

  browser.runtime.onSuspend.addListener(() => {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    socket?.close();
  });

  connect();
});
