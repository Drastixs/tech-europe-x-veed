import type {
  Direction,
  NarrationVariant,
  OverlayCommand,
  RuntimeSession,
  TutorialPlan,
  TutorialStep,
  TutorialStepRuntimeStatus
} from "./protocol";
import { canTransitionRuntime } from "./runtime";

export type NarrationMode = "concise" | "detailed";

export type OverlayState = {
  sessionVisible: boolean;
  guidanceVisible: boolean;
  x: number;
  y: number;
  moveDurationMs: number;
  step: number;
  clickRevision: number;
  activeDirection: Direction | null;
  plan: TutorialPlan | null;
  runtimeSession: RuntimeSession | null;
  steps: TutorialStep[];
  narrationMode: NarrationMode;
  takeoverArmed: boolean;
  runtimeStatus: TutorialStepRuntimeStatus | null;
  runtimeMessage: string | null;
  demonstrationRevision: number;
  lastCommand: string;
};

export const initialOverlayState: OverlayState = {
  sessionVisible: true,
  guidanceVisible: true,
  x: 520,
  y: 340,
  moveDurationMs: 420,
  step: 1,
  clickRevision: 0,
  activeDirection: null,
  plan: null,
  runtimeSession: null,
  steps: [],
  narrationMode: "concise",
  takeoverArmed: false,
  runtimeStatus: null,
  runtimeMessage: null,
  demonstrationRevision: 0,
  lastCommand: "ready"
};

export function currentTutorialText(state: OverlayState): string {
  return currentNarration(state)?.text ?? "Waiting for a tutorial step…";
}

export function currentNarration(state: OverlayState): NarrationVariant | null {
  const currentStep = state.steps[state.step - 1];
  return currentStep?.narration[state.narrationMode] ?? null;
}

export type LocalAction =
  | OverlayCommand
  | { type: "takeover" }
  | { type: "clear_direction" }
  | { type: "set_narration_mode"; mode: NarrationMode };

export function reduceOverlayState(state: OverlayState, action: LocalAction): OverlayState {
  switch (action.type) {
    case "show":
      return { ...state, sessionVisible: true, guidanceVisible: true, lastCommand: "show" };
    case "hide":
      return {
        ...state,
        sessionVisible: false,
        guidanceVisible: false,
        activeDirection: null
      };
    case "takeover":
      return {
        ...state,
        guidanceVisible: false,
        activeDirection: null,
        takeoverArmed: false,
        lastCommand: "takeover"
      };
    case "move":
      return {
        ...state,
        sessionVisible: true,
        guidanceVisible: true,
        x: Math.max(8, action.x),
        y: Math.max(8, action.y),
        moveDurationMs: Math.max(0, action.duration_ms ?? 420),
        lastCommand: "move"
      };
    case "click":
      return {
        ...state,
        sessionVisible: true,
        guidanceVisible: true,
        clickRevision: state.clickRevision + 1,
        lastCommand: "click"
      };
    case "navigate": {
      const delta = action.direction === "right" ? 1 : -1;
      return {
        ...state,
        sessionVisible: true,
        guidanceVisible: true,
        step: Math.min(Math.max(1, state.steps.length), Math.max(1, state.step + delta)),
        activeDirection: action.direction,
        lastCommand: `step ${action.direction}`
      };
    }
    case "load_tutorial": {
      if (action.plan.steps.length === 0) return state;
      return {
        ...state,
        plan: action.plan,
        runtimeSession: action.runtime_session ?? null,
        steps: action.plan.steps,
        narrationMode: action.plan.runtime_preferences.detailed_narration ? "detailed" : "concise",
        step: Math.min(action.plan.steps.length, Math.max(1, action.step ?? 1)),
        sessionVisible: true,
        guidanceVisible: true,
        runtimeStatus: null,
        runtimeMessage: null,
        lastCommand: "load tutorial"
      };
    }
    case "tutorial_step_status": {
      if (!canTransitionRuntime(state.runtimeStatus, action.status)) return state;
      const stepIndex = state.steps.findIndex((step) => step.step_id === action.step_id);
      const demonstrating = action.status === "demonstrating";
      const demoVisible = action.status === "demo_visible";
      return {
        ...state,
        step: stepIndex >= 0 ? stepIndex + 1 : state.step,
        runtimeStatus: action.status,
        runtimeMessage: action.message ?? null,
        demonstrationRevision: demonstrating
          ? state.demonstrationRevision + 1
          : state.demonstrationRevision,
        sessionVisible: true,
        guidanceVisible: true,
        takeoverArmed: demoVisible,
        lastCommand: action.status
      };
    }
    case "arm_takeover":
      return { ...state, takeoverArmed: true, lastCommand: "takeover armed" };
    case "disarm_takeover":
      return { ...state, takeoverArmed: false, lastCommand: "takeover disarmed" };
    case "clear_direction":
      return { ...state, activeDirection: null };
    case "set_narration_mode":
      return { ...state, narrationMode: action.mode, lastCommand: `${action.mode} narration` };
  }
}

export type Rectangle = { left: number; right: number; top: number; bottom: number };

export function hitTestNavigation(
  x: number,
  y: number,
  left: Rectangle,
  right: Rectangle
): Direction | null {
  const contains = (rectangle: Rectangle) =>
    x >= rectangle.left && x <= rectangle.right && y >= rectangle.top && y <= rectangle.bottom;
  if (contains(left)) return "left";
  if (contains(right)) return "right";
  return null;
}

type Subscriber = (command: OverlayCommand) => void;
const subscribers = new Set<Subscriber>();

export const commandBus = {
  dispatch(command: OverlayCommand) {
    subscribers.forEach((subscriber) => subscriber(command));
  },
  subscribe(subscriber: Subscriber) {
    subscribers.add(subscriber);
    return () => {
      subscribers.delete(subscriber);
    };
  }
};
