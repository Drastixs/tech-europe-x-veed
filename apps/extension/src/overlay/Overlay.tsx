import { useEffect, useMemo, useReducer, useRef, useState, type CSSProperties } from "react";
import {
  commandBus,
  currentNarration,
  currentTutorialText,
  hitTestNavigation,
  initialOverlayState,
  reduceOverlayState,
  type Rectangle
} from "./controller";
import {
  browserAudioFactory,
  entryVoiceCue,
  NarrationPlayer,
  shouldAutoplayNarration,
  type PlaybackStatus
} from "./narration";
import type { DemoCommand } from "./protocol";
import { isOverlayEvent, isRelevantTakeoverKey } from "./takeover";
import "./overlay.css";

export function Overlay() {
  const [state, dispatch] = useReducer(reduceOverlayState, initialOverlayState);
  const [playbackStatus, setPlaybackStatus] = useState<PlaybackStatus>("idle");
  const playerRef = useRef<NarrationPlayer | null>(null);
  if (!playerRef.current) {
    playerRef.current = new NarrationPlayer(browserAudioFactory, setPlaybackStatus);
  }
  const leftRef = useRef<HTMLButtonElement>(null);
  const rightRef = useRef<HTMLButtonElement>(null);
  const takeoverArmedRef = useRef(state.takeoverArmed);
  takeoverArmedRef.current = state.takeoverArmed;

  useEffect(() => commandBus.subscribe(dispatch), []);

  const currentStep = state.steps[state.step - 1] ?? null;
  const narration = currentNarration(state);
  const voiceCue = currentStep ? entryVoiceCue(currentStep, state.narrationMode) : null;

  useEffect(() => {
    const player = playerRef.current;
    if (!player) return;

    if (
      state.sessionVisible &&
      state.guidanceVisible &&
      currentStep &&
      narration &&
      shouldAutoplayNarration(currentStep, state.narrationMode)
    ) {
      void player.play(narration.fal_elevenlabs_audio_url);
    } else {
      player.stop();
    }

    return () => player.stop();
  }, [
    state.sessionVisible,
    state.guidanceVisible,
    state.plan?.tutorial_id,
    state.step,
    state.narrationMode,
    currentStep,
    narration
  ]);

  useEffect(() => {
    const takeOver = (event: Event) => {
      if (!takeoverArmedRef.current || !event.isTrusted || isOverlayEvent(event)) return;
      if (event instanceof PointerEvent && event.button !== 0) return;
      if (event instanceof KeyboardEvent && !isRelevantTakeoverKey(event)) return;

      event.preventDefault();
      event.stopImmediatePropagation();
      takeoverArmedRef.current = false;
      dispatch({ type: "takeover" });
      if (typeof browser !== "undefined") {
        void browser.runtime.sendMessage({
          channel: "onshape-assist",
          event: {
            type: "user.takeover",
            browser_event: event.type,
            timestamp_ms: Date.now()
          }
        });
      }
    };

    window.addEventListener("pointerdown", takeOver, { capture: true, passive: false });
    window.addEventListener("touchstart", takeOver, { capture: true, passive: false });
    window.addEventListener("keydown", takeOver, { capture: true });
    return () => {
      window.removeEventListener("pointerdown", takeOver, { capture: true });
      window.removeEventListener("touchstart", takeOver, { capture: true });
      window.removeEventListener("keydown", takeOver, { capture: true });
    };
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

  const playNarration = () => {
    if (narration) void playerRef.current?.play(narration.fal_elevenlabs_audio_url);
  };
  const narrationIsActive = playbackStatus === "loading" || playbackStatus === "playing";
  const navigationBlocked = Boolean(voiceCue?.blocking && narrationIsActive);

  if (!state.sessionVisible) return null;

  return (
    <div className="oa-root" aria-label="Onshape Assist overlay">
      <div
        className={`oa-cursor ${state.guidanceVisible ? "is-visible" : "is-hidden"}`}
        style={cursorStyle}
        aria-hidden="true"
      >
        <svg viewBox="0 0 28 36" focusable="false">
          <path d="M2.5 1.8 24.2 20l-9.2 1.5 5.1 10.7-6.1 2.9-5-10.7-6.5 6.7Z" />
        </svg>
      </div>

      <div
        className={`oa-callout ${state.guidanceVisible ? "is-visible" : "is-hidden"}`}
        style={calloutStyle}
      >
        <span>{currentTutorialText(state)}</span>
      </div>

      <nav className="oa-nav" aria-label="Tutorial steps">
        <button
          ref={leftRef}
          className={state.activeDirection === "left" ? "is-active" : ""}
          type="button"
          onClick={() => dispatch({ type: "navigate", direction: "left" })}
          disabled={navigationBlocked}
          aria-label="Previous step, left arrow"
        >
          ←
        </button>
        <span className="oa-step">{state.steps.length === 0 ? "0/0" : `${state.step}/${state.steps.length}`}</span>
        <div className="oa-narration-mode" aria-label="Narration detail">
          <button
            type="button"
            className={state.narrationMode === "concise" ? "is-selected" : ""}
            aria-pressed={state.narrationMode === "concise"}
            onClick={() => dispatch({ type: "set_narration_mode", mode: "concise" })}
          >
            Brief
          </button>
          <button
            type="button"
            className={state.narrationMode === "detailed" ? "is-selected" : ""}
            aria-pressed={state.narrationMode === "detailed"}
            onClick={() => dispatch({ type: "set_narration_mode", mode: "detailed" })}
          >
            Detail
          </button>
        </div>
        <button
          className="oa-audio"
          type="button"
          onClick={narrationIsActive ? () => playerRef.current?.stop() : playNarration}
          disabled={!narration}
          aria-label={narrationIsActive ? "Stop narration" : "Play narration"}
          title={playbackStatus === "failed" ? "Audio unavailable; tutorial text remains available" : undefined}
        >
          {narrationIsActive ? "■" : playbackStatus === "failed" ? "Audio off" : "♪"}
        </button>
        <button
          ref={rightRef}
          className={state.activeDirection === "right" ? "is-active" : ""}
          type="button"
          onClick={() => dispatch({ type: "navigate", direction: "right" })}
          disabled={navigationBlocked}
          aria-label="Next step, right arrow"
        >
          →
        </button>
        <span className="oa-sr-only" aria-live="polite">
          {playbackStatus === "failed" ? "Narration audio unavailable. Follow the on-screen text." : ""}
        </span>
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
