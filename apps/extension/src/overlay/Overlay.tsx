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
  shouldPlayStepNarration,
  type PlaybackStatus
} from "./narration";
import type { OverlayCommand } from "./protocol";
import { isLearnerTakeoverEvent } from "./takeover";
import "./overlay.css";

export function Overlay() {
  const [state, dispatch] = useReducer(reduceOverlayState, initialOverlayState);
  const [playbackStatus, setPlaybackStatus] = useState<PlaybackStatus>("idle");
  const [redoStatus, setRedoStatus] = useState<"idle" | "requesting" | "failed">("idle");
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
  const narrationIsActive = playbackStatus === "loading" || playbackStatus === "playing";
  const navigationBlocked = Boolean(voiceCue?.blocking && narrationIsActive);

  useEffect(() => {
    const player = playerRef.current;
    if (!player) return;

    if (
      state.sessionVisible &&
      state.guidanceVisible &&
      currentStep &&
      narration &&
      shouldPlayStepNarration(state.runtimeStatus, currentStep, state.narrationMode)
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
    state.runtimeStatus,
    state.demonstrationRevision,
    currentStep,
    narration
  ]);

  useEffect(() => {
    const takeOver = (event: Event) => {
      if (!takeoverArmedRef.current || !isLearnerTakeoverEvent(event)) return;

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
    return () => {
      window.removeEventListener("pointerdown", takeOver, { capture: true });
      window.removeEventListener("touchstart", takeOver, { capture: true });
    };
  }, []);

  useEffect(() => {
    if (!state.activeDirection) return;
    const timeout = window.setTimeout(() => dispatch({ type: "clear_direction" }), 170);
    return () => window.clearTimeout(timeout);
  }, [state.activeDirection]);

  useEffect(() => {
    if (state.clickRevision === 0) return;
    if (navigationBlocked) return;
    const left = rectOf(leftRef.current);
    const right = rectOf(rightRef.current);
    if (!left || !right) return;
    const direction = hitTestNavigation(state.x, state.y, left, right);
    if (direction) dispatch({ type: "navigate", direction });
  }, [navigationBlocked, state.clickRevision, state.x, state.y]);

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

  const runtimeText = runtimeStatusText(state.runtimeStatus, state.runtimeMessage);

  const requestStepRedo = async () => {
    if (!currentStep || !state.plan || redoStatus === "requesting") return;

    setRedoStatus("requesting");
    try {
      await browser.runtime.sendMessage({
        channel: "onshape-assist",
        event: createStepRedoRequestedEvent(
          state.plan.tutorial_id,
          currentStep.step_id,
          state.step
        )
      });
      setRedoStatus("idle");
    } catch {
      setRedoStatus("failed");
    }
  };

  const requestRuntimeEvent = (type: "tutorial.runtime.pause.requested" | "tutorial.runtime.resume.requested" | "user.takeover") => {
    if (typeof browser === "undefined") return;
    void browser.runtime.sendMessage({ channel: "onshape-assist", event: { type } });
  };

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
        role="status"
        aria-live="polite"
      >
        <span>{runtimeText ?? currentTutorialText(state)}</span>
      </div>

      <aside className="oa-panel" aria-label="Tutorial controls">
        <p className="oa-panel-eyebrow">Onshape Assist</p>
        <h2>{currentStep?.goal ?? "Waiting for a tutorial"}</h2>
        <p className="oa-panel-progress">Step {state.steps.length ? `${state.step} of ${state.steps.length}` : "0 of 0"}</p>
        <p className="oa-panel-state" role="status">{runtimeText ?? "Ready"}</p>
        <div className="oa-panel-controls">
          {state.runtimeStatus === "paused" ? (
            <button type="button" onClick={() => requestRuntimeEvent("tutorial.runtime.resume.requested")}>Resume</button>
          ) : (
            <button type="button" onClick={() => requestRuntimeEvent("tutorial.runtime.pause.requested")}>Pause</button>
          )}
          <button
            type="button"
            onClick={() => requestRuntimeEvent("user.takeover")}
            disabled={state.runtimeStatus !== "demo_visible"}
          >
            Try it myself
          </button>
        </div>
      </aside>

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
          className="oa-redo"
          type="button"
          onClick={() => void requestStepRedo()}
          disabled={
            !currentStep || navigationBlocked || redoStatus === "requesting" ||
            state.runtimeStatus === "demonstrating" || state.runtimeStatus === "restoring"
          }
          aria-label={currentStep ? `Redo step ${state.step}: ${currentStep.goal}` : "Redo current step"}
          title={redoStatus === "failed" ? "Could not request the redo. Try again." : "Redo current step with the agent"}
        >
          <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            <path d="M13.25 5.25V2.5m0 2.75H10.5M13 5a5.5 5.5 0 1 0 .25 5.65" />
          </svg>
          <span>{redoStatus === "requesting" ? "Redoing…" : "Redo"}</span>
        </button>
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
          {redoStatus === "failed"
            ? "Could not request the step redo. Try again."
            : playbackStatus === "failed"
              ? "Narration audio unavailable. Follow the on-screen text."
              : ""}
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

export function dispatchOverlayCommand(command: OverlayCommand) {
  commandBus.dispatch(command);
}

export function createStepRedoRequestedEvent(
  tutorialId: string,
  stepId: string,
  stepNumber: number,
  timestampMs = Date.now()
) {
  return {
    type: "tutorial.step.redo.requested" as const,
    tutorial_id: tutorialId,
    step_id: stepId,
    step_number: stepNumber,
    timestamp_ms: timestampMs
  };
}

function runtimeStatusText(
  status: typeof initialOverlayState.runtimeStatus,
  message: string | null
): string | null {
  if (status === "demonstrating") return "Showing the next step…";
  if (status === "demo_visible") return "Click when you’re ready to try.";
  if (status === "restoring") return "Resetting the demo state…";
  if (status === "waiting") return "Waiting for the next step…";
  if (status === "learner_attempt") return "Your turn.";
  if (status === "validating") return "Checking your result…";
  if (status === "complete") return "Step complete.";
  if (status === "paused") return message || "Paused. You can retry when ready.";
  if (status === "failed") return message || "I couldn’t complete that step. Try redo.";
  return null;
}
