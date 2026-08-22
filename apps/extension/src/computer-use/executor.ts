import type {
  ActionCompletedEvent,
  ExecuteActionCommand,
  PixelPoint
} from "../overlay/protocol";

export type PageElement = {
  textContent: string | null;
  parentElement: PageElement | null;
  getAttribute: (name: string) => string | null;
};

export type ActionEnvironment = {
  elementFromPoint: (point: PixelPoint) => PageElement | null;
  isOverlayElement: (element: PageElement) => boolean;
  click: (element: PageElement, button: "primary" | "secondary" | "middle") => void;
  doubleClick: (
    element: PageElement,
    button: "primary" | "secondary" | "middle",
    intervalMs: number
  ) => Promise<void>;
  typeText: (element: PageElement, text: string, clearExisting: boolean, submit: boolean) => void;
  keypress: (
    element: PageElement,
    key: string,
    modifiers: Array<"alt" | "control" | "meta" | "shift">,
    repeat: number
  ) => void;
  scroll: (deltaX: number, deltaY: number) => void;
  drag: (start: PageElement, startPoint: PixelPoint, endPoint: PixelPoint, durationMs: number) =>
    Promise<void>;
  conditionVisible: (condition: string) => boolean;
  delay: (durationMs: number) => Promise<void>;
};

export async function executeOnshapeAction(
  command: ExecuteActionCommand,
  environment: ActionEnvironment
): Promise<ActionCompletedEvent> {
  const { action } = command;
  try {
    if (action.action_type === "move") {
      await environment.delay(action.parameters.duration_ms);
      return completed(command.action_id, true, null, null);
    }
    if (action.action_type === "scroll") {
      environment.scroll(action.parameters.delta_x, action.parameters.delta_y);
      await environment.delay(action.parameters.duration_ms);
      return completed(command.action_id, true, null, "Onshape viewport");
    }
    if (action.action_type === "wait") {
      if (action.parameters.duration_ms !== null) {
        await environment.delay(action.parameters.duration_ms);
      }
      if (action.parameters.condition && !environment.conditionVisible(action.parameters.condition)) {
        return failed(command.action_id, "Wait condition is not visible", null);
      }
      return completed(command.action_id, true, null, action.parameters.condition);
    }

    const element = findSafeTarget(environment, command.target, action.target_label);
    if (!element) {
      return failed(command.action_id, "Localized point did not match the requested target", null);
    }
    const description = describeElement(element);

    switch (action.action_type) {
      case "click":
        environment.click(element, action.parameters.button);
        break;
      case "double_click":
        await environment.doubleClick(
          element,
          action.parameters.button,
          action.parameters.interval_ms
        );
        break;
      case "drag":
        if (!command.end_target) {
          return failed(command.action_id, "Drag action is missing its destination", description);
        }
        await environment.drag(
          element,
          command.target,
          command.end_target,
          action.parameters.duration_ms
        );
        break;
      case "keypress":
        environment.keypress(
          element,
          action.parameters.key,
          action.parameters.modifiers,
          action.parameters.repeat
        );
        break;
      case "type":
        environment.typeText(
          element,
          action.parameters.text,
          action.parameters.clear_existing,
          action.parameters.submit
        );
        break;
      case "selection":
        environment.click(element, "primary");
        break;
    }
    return completed(command.action_id, true, null, description);
  } catch (error) {
    return failed(
      command.action_id,
      error instanceof Error ? error.message : "Onshape action execution failed",
      null
    );
  }
}

const findSafeTarget = (
  environment: ActionEnvironment,
  point: PixelPoint,
  targetLabel: string | null
): PageElement | null => {
  let candidate = environment.elementFromPoint(point);
  for (let depth = 0; candidate && depth < 6; depth += 1) {
    if (environment.isOverlayElement(candidate)) return null;
    if (!targetLabel || labelMatches(candidate, targetLabel)) return candidate;
    candidate = candidate.parentElement;
  }
  return null;
};

const labelMatches = (element: PageElement, expected: string) => {
  const wanted = normalize(expected);
  return descriptors(element).some((value) => normalize(value).includes(wanted));
};

const descriptors = (element: PageElement) => [
  element.textContent ?? "",
  element.getAttribute("aria-label") ?? "",
  element.getAttribute("title") ?? "",
  element.getAttribute("data-tooltip") ?? ""
].filter(Boolean);

const describeElement = (element: PageElement) => descriptors(element)[0] ?? "Onshape element";
const normalize = (value: string) => value.trim().toLocaleLowerCase().replace(/\s+/g, " ");

const completed = (
  action_id: string,
  success: boolean,
  reason: string | null,
  element_description: string | null
): ActionCompletedEvent => ({
  type: "action.completed",
  action_id,
  success,
  reason,
  element_description
});

const failed = (
  action_id: string,
  reason: string,
  element_description: string | null
): ActionCompletedEvent => ({
  type: "action.failed",
  action_id,
  success: false,
  reason,
  element_description
});

const asHTMLElement = (element: PageElement) => element as HTMLElement;

export const browserActionEnvironment: ActionEnvironment = {
  elementFromPoint: ({ x, y }) => document.elementFromPoint(x, y) as PageElement | null,
  isOverlayElement: (element) => Boolean(asHTMLElement(element).closest?.("#onshape-assist-root")),
  click: (element, button) => {
    const htmlElement = asHTMLElement(element);
    if (button === "primary") {
      htmlElement.click();
      return;
    }
    const numericButton = button === "middle" ? 1 : 2;
    htmlElement.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, button: numericButton }));
    htmlElement.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, button: numericButton }));
    htmlElement.dispatchEvent(new MouseEvent("click", { bubbles: true, button: numericButton }));
  },
  doubleClick: async (element, button, intervalMs) => {
    browserActionEnvironment.click(element, button);
    await browserActionEnvironment.delay(intervalMs);
    browserActionEnvironment.click(element, button);
    asHTMLElement(element).dispatchEvent(new MouseEvent("dblclick", { bubbles: true, button: 0 }));
  },
  typeText: (element, text, clearExisting, submit) => {
    const htmlElement = asHTMLElement(element);
    htmlElement.focus();
    if (htmlElement instanceof HTMLInputElement || htmlElement instanceof HTMLTextAreaElement) {
      const prototype = htmlElement instanceof HTMLInputElement
        ? HTMLInputElement.prototype
        : HTMLTextAreaElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
      setter?.call(htmlElement, clearExisting ? text : `${htmlElement.value}${text}`);
      htmlElement.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
      htmlElement.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (htmlElement.isContentEditable) {
      htmlElement.textContent = clearExisting ? text : `${htmlElement.textContent ?? ""}${text}`;
      htmlElement.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
    } else {
      throw new Error("Localized target is not editable");
    }
    if (submit) browserActionEnvironment.keypress(element, "Enter", [], 1);
  },
  keypress: (element, key, modifiers, repeat) => {
    const htmlElement = asHTMLElement(element);
    htmlElement.focus();
    const init = {
      key,
      bubbles: true,
      altKey: modifiers.includes("alt"),
      ctrlKey: modifiers.includes("control"),
      metaKey: modifiers.includes("meta"),
      shiftKey: modifiers.includes("shift")
    };
    for (let index = 0; index < repeat; index += 1) {
      htmlElement.dispatchEvent(new KeyboardEvent("keydown", init));
      htmlElement.dispatchEvent(new KeyboardEvent("keyup", init));
    }
  },
  scroll: (deltaX, deltaY) => window.scrollBy({ left: deltaX, top: deltaY, behavior: "smooth" }),
  drag: async (element, start, end, durationMs) => {
    const startElement = asHTMLElement(element);
    startElement.dispatchEvent(new PointerEvent("pointerdown", {
      bubbles: true,
      button: 0,
      buttons: 1,
      clientX: start.x,
      clientY: start.y
    }));
    await browserActionEnvironment.delay(durationMs);
    const endElement = document.elementFromPoint(end.x, end.y) ?? startElement;
    endElement.dispatchEvent(new PointerEvent("pointermove", {
      bubbles: true,
      button: 0,
      buttons: 1,
      clientX: end.x,
      clientY: end.y
    }));
    endElement.dispatchEvent(new PointerEvent("pointerup", {
      bubbles: true,
      button: 0,
      buttons: 0,
      clientX: end.x,
      clientY: end.y
    }));
  },
  conditionVisible: (condition) => normalize(document.body.innerText).includes(normalize(condition)),
  delay: (durationMs) => new Promise((resolve) => window.setTimeout(resolve, durationMs))
};
