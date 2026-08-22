import { createRoot, type Root } from "react-dom/client";
import { dispatchOverlayCommand, Overlay } from "./Overlay";
import type { DemoCommand } from "./protocol";

export type OverlayMount = {
  element: HTMLDivElement;
  root: Root;
  dispatch: (command: DemoCommand) => void;
  unmount: () => void;
};

export function mountOverlay(container?: HTMLElement): OverlayMount {
  const element = document.createElement("div");
  element.id = "onshape-assist-root";
  (container ?? document.documentElement).appendChild(element);

  const root = createRoot(element);
  root.render(<Overlay />);

  return {
    element,
    root,
    dispatch: dispatchOverlayCommand,
    unmount() {
      root.unmount();
      element.remove();
    }
  };
}
