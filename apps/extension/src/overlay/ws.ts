import { dispatchOverlayCommand } from "./Overlay";
import { isDemoEnvelope, isOverlayCommand } from "./protocol";

export function connectOverlayRelay(url = "ws://127.0.0.1:8000/ws/extension") {
  let socket: WebSocket | null = null;
  let stopped = false;
  let retryTimer: number | undefined;

  const connect = () => {
    if (stopped) return;
    socket = new WebSocket(url);

    socket.addEventListener("message", (event) => {
      try {
        const envelope = JSON.parse(String(event.data));
        if (isDemoEnvelope(envelope) && isOverlayCommand(envelope.command)) {
          dispatchOverlayCommand(envelope.command);
        }
      } catch {
        // Ignore malformed demo traffic.
      }
    });

    socket.addEventListener("close", () => {
      if (!stopped) retryTimer = window.setTimeout(connect, 1000);
    });
  };

  connect();

  return () => {
    stopped = true;
    if (retryTimer) window.clearTimeout(retryTimer);
    socket?.close();
  };
}
