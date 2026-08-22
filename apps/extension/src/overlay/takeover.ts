const EDITING_KEYS = new Set(["Enter", "Escape", "Backspace", "Delete"]);
const EDITABLE_NAVIGATION_KEYS = new Set(["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]);

function isEditableTarget(target: EventTarget | null): boolean {
  if (typeof HTMLElement === "undefined" || !(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  );
}

export function isRelevantTakeoverKey(event: KeyboardEvent): boolean {
  if (event.ctrlKey || event.metaKey || event.altKey) return false;
  if (event.key.length === 1 || EDITING_KEYS.has(event.key)) return true;
  return isEditableTarget(event.target) && EDITABLE_NAVIGATION_KEYS.has(event.key);
}

export function isOverlayEvent(event: Event): boolean {
  return event.composedPath().some(
    (target) => target instanceof HTMLElement && target.id === "onshape-assist-root"
  );
}
