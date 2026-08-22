import { mountOverlay } from "./overlay/mount";
import { connectOverlayRelay } from "./overlay/ws";
import { dispatchOverlayCommand } from "./overlay/Overlay";
import type { OverlayCommand } from "./overlay/protocol";

declare global {
  interface Window {
    OnshapeAssistPreview?: {
      dispatch: (command: OverlayCommand) => void;
      unmount: () => void;
    };
  }
}

window.OnshapeAssistPreview?.unmount();

const mount = mountOverlay();
const disconnect = connectOverlayRelay();

window.OnshapeAssistPreview = {
  dispatch: dispatchOverlayCommand,
  unmount() {
    disconnect();
    mount.unmount();
    delete window.OnshapeAssistPreview;
  }
};
