import { mountOverlay, type OverlayMount } from "../../src/overlay/mount";
import type { DemoCommand } from "../../src/overlay/protocol";

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
      const candidate = message as { channel?: string; command?: DemoCommand };
      if (candidate.channel === "onshape-assist" && candidate.command) {
        overlay?.dispatch(candidate.command);
      }
    });
  }
});
