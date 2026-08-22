export type Direction = "left" | "right";

export type TutorialStep = {
  step_id: string;
  text: string;
};

export type DemoCommand =
  | { type: "show" }
  | { type: "hide" }
  | { type: "move"; x: number; y: number; duration_ms?: number }
  | { type: "click" }
  | { type: "navigate"; direction: Direction }
  | { type: "load_tutorial"; steps: TutorialStep[]; step?: number }
  | { type: "arm_takeover" }
  | { type: "disarm_takeover" };

export type DemoEnvelope = {
  version: 1;
  sequence: number;
  sent_at: string;
  command: DemoCommand;
};

export const isDemoEnvelope = (value: unknown): value is DemoEnvelope => {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<DemoEnvelope>;
  if (!(
    candidate.version === 1 &&
    Number.isInteger(candidate.sequence) &&
    !!candidate.command &&
    typeof candidate.command === "object" &&
    "type" in candidate.command
  )) return false;

  const command = candidate.command as { type?: unknown };
  return typeof command.type === "string" && [
    "show",
    "hide",
    "move",
    "click",
    "navigate",
    "load_tutorial",
    "arm_takeover",
    "disarm_takeover"
  ].includes(command.type);
};
