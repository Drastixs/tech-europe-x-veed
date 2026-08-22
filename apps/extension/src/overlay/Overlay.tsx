import { useEffect, useMemo, useReducer, useRef, type CSSProperties } from "react";
import {
  commandBus,
  directionForKey,
  hitTestNavigation,
  initialOverlayState,
  reduceOverlayState,
  type Rectangle
} from "./controller";
import type { DemoCommand } from "./protocol";
import "./overlay.css";

const steps = [
  "Orient the part studio.",
  "Pick the target sketch plane.",
  "Trace the feature boundary.",
  "Confirm the dimension.",
  "Preview the operation.",
  "Apply, then inspect the result."
];

export function Overlay() {
  const [state, dispatch] = useReducer(reduceOverlayState, initialOverlayState);
  const leftRef = useRef<HTMLButtonElement>(null);
  const rightRef = useRef<HTMLButtonElement>(null);

  useEffect(() => commandBus.subscribe(dispatch), []);

  useEffect(() => {
    const onUserPointer = (event: Event) => {
      if (!event.isTrusted) return;
      dispatch({ type: "takeover" });
    };
    document.addEventListener("pointermove", onUserPointer, { capture: true, passive: true });
    document.addEventListener("pointerdown", onUserPointer, { capture: true, passive: true });
    document.addEventListener("mousemove", onUserPointer, { capture: true, passive: true });
    document.addEventListener("mousedown", onUserPointer, { capture: true, passive: true });
    return () => {
      document.removeEventListener("pointermove", onUserPointer, { capture: true });
      document.removeEventListener("pointerdown", onUserPointer, { capture: true });
      document.removeEventListener("mousemove", onUserPointer, { capture: true });
      document.removeEventListener("mousedown", onUserPointer, { capture: true });
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const direction = directionForKey(event.key);
      if (!direction) return;
      event.preventDefault();
      dispatch({ type: "navigate", direction });
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, []);

  useEffect(() => {
    if (!state.activeDirection) return;
    const timeout = window.setTimeout(() => dispatch({ type: "clear_direction" }), 170);
    return () => window.clearTimeout(timeout);
  }, [state.activeDirection]);

  useEffect(() => {
    if (state.clickRevision === 0) return;
    const left = rectOf(leftRef.current);
    const right = rectOf(rightRef.current);
    if (!left || !right) return;
    const direction = hitTestNavigation(state.x, state.y, left, right);
    if (direction) dispatch({ type: "navigate", direction });
  }, [state.clickRevision, state.x, state.y]);

  const cursorStyle = useMemo(
    () => ({
      transform: `translate3d(${state.x}px, ${state.y}px, 0)`,
      transitionDuration: `${state.moveDurationMs}ms`
    }),
    [state.moveDurationMs, state.x, state.y]
  );

  const calloutStyle = useMemo(
    () =>
      ({
        "--oa-guide-x": `${Math.min(state.x + 24, window.innerWidth - 340)}px`,
        "--oa-guide-y": `${Math.min(state.y + 22, window.innerHeight - 128)}px`
      }) as CSSProperties,
    [state.x, state.y]
  );

  if (!state.sessionVisible) return null;

  return (
    <div className="oa-root" aria-label="Onshape Assist overlay">
      <div
        className={`oa-cursor ${state.guidanceVisible ? "is-visible" : "is-hidden"}`}
        style={cursorStyle}
        aria-hidden="true"
      >
        <span className="oa-cursor-core" />
        <span className="oa-cursor-ring" />
      </div>

      <div
        className={`oa-callout ${state.guidanceVisible ? "is-visible" : "is-hidden"}`}
        style={calloutStyle}
      >
        <span>{steps[state.step - 1]}</span>
      </div>

      <nav className="oa-nav" aria-label="Tutorial steps">
        <button
          ref={leftRef}
          className={state.activeDirection === "left" ? "is-active" : ""}
          type="button"
          onClick={() => dispatch({ type: "navigate", direction: "left" })}
          aria-label="Previous step, left arrow"
        >
          ←
          <kbd>←</kbd>
        </button>
        <span className="oa-step">{state.step}/6</span>
        <button
          ref={rightRef}
          className={state.activeDirection === "right" ? "is-active" : ""}
          type="button"
          onClick={() => dispatch({ type: "navigate", direction: "right" })}
          aria-label="Next step, right arrow"
        >
          →
          <kbd>→</kbd>
        </button>
      </nav>
    </div>
  );
}

function rectOf(element: HTMLElement | null): Rectangle | null {
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
}

export function dispatchOverlayCommand(command: DemoCommand) {
  commandBus.dispatch(command);
}
