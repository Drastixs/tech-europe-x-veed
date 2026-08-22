import { mountOverlay, type OverlayMount } from "../../src/overlay/mount";
import {
  isExecuteActionCommand,
  isOverlayCommand,
  type DemoCommand
} from "../../src/overlay/protocol";
import {
  browserActionEnvironment,
  executeOnshapeAction
} from "../../src/computer-use/executor";

export default defineContentScript({
  matches: ["https://cad.onshape.com/documents/*"],
  cssInjectionMode: "ui",
  async main(ctx) {
    let overlay: OverlayMount | undefined;

    const ui = await createShadowRootUi(ctx, {
      name: "onshape-assist",
      position: "inline",
      anchor: "body",
      isolateEvents: false,
      onMount(container) {
        overlay = mountOverlay(container);
        return overlay;
      },
      onRemove(mountedOverlay) {
        mountedOverlay?.unmount();
      }
    });

    ui.mount();
    void browser.runtime.sendMessage({ channel: "onshape-assist", type: "tab.ready" });

    browser.runtime.onMessage.addListener((message: unknown) => {
      const candidate = message as {
        channel?: string;
        type?: string;
        command?: DemoCommand;
      };
      if (candidate.channel !== "onshape-assist") return;
      if (candidate.type === "viewport.request") {
        return Promise.resolve({
          width: window.innerWidth,
          height: window.innerHeight,
          device_pixel_ratio: window.devicePixelRatio
        });
      }
      if (!candidate.command) return;
      if (isExecuteActionCommand(candidate.command)) {
        void executeOnshapeAction(candidate.command, browserActionEnvironment).then((event) =>
          browser.runtime.sendMessage({ channel: "onshape-assist", event })
        );
        return;
      }
      if (isOverlayCommand(candidate.command)) overlay?.dispatch(candidate.command);
    });
  }
});
