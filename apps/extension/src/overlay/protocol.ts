export type Direction = "left" | "right";

export type DemoCommand =
  | { type: "show" }
  | { type: "hide" }
  | { type: "move"; x: number; y: number; duration_ms?: number }
  | { type: "click" }
  | { type: "navigate"; direction: Direction };

export type DemoEnvelope = {
  version: 1;
  sequence: number;
  sent_at: string;
  command: DemoCommand;
};

export const isDemoEnvelope = (value: unknown): value is DemoEnvelope => {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<DemoEnvelope>;
  return (
    candidate.version === 1 &&
    Number.isInteger(candidate.sequence) &&
    !!candidate.command &&
    typeof candidate.command === "object" &&
    "type" in candidate.command
  );
};
