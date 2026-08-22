import type { DemoCommand, Direction, TutorialStep } from "./protocol";

export type OverlayState = {
  sessionVisible: boolean;
  guidanceVisible: boolean;
  x: number;
  y: number;
  moveDurationMs: number;
  step: number;
  clickRevision: number;
  activeDirection: Direction | null;
  steps: TutorialStep[];
  takeoverArmed: boolean;
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
  steps: [{ step_id: "waiting", text: "Waiting for a tutorial step…" }],
  takeoverArmed: false,
  lastCommand: "ready"
};

export type LocalAction = DemoCommand | { type: "takeover" } | { type: "clear_direction" };

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
        step: Math.min(state.steps.length, Math.max(1, state.step + delta)),
        activeDirection: action.direction,
        lastCommand: `step ${action.direction}`
      };
    }
    case "load_tutorial": {
      if (action.steps.length === 0) return state;
      return {
        ...state,
        steps: action.steps,
        step: Math.min(action.steps.length, Math.max(1, action.step ?? 1)),
        sessionVisible: true,
        guidanceVisible: true,
        lastCommand: "load tutorial"
      };
    }
    case "arm_takeover":
      return { ...state, takeoverArmed: true, lastCommand: "takeover armed" };
    case "disarm_takeover":
      return { ...state, takeoverArmed: false, lastCommand: "takeover disarmed" };
    case "clear_direction":
      return { ...state, activeDirection: null };
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

type Subscriber = (command: DemoCommand) => void;
const subscribers = new Set<Subscriber>();

export const commandBus = {
  dispatch(command: DemoCommand) {
    subscribers.forEach((subscriber) => subscriber(command));
  },
  subscribe(subscriber: Subscriber) {
    subscribers.add(subscriber);
    return () => {
      subscribers.delete(subscriber);
    };
  }
};
