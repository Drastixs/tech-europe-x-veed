export type Direction = "left" | "right";

export type RuntimePreferences = {
  detailed_narration: boolean;
};

export type Voice = {
  provider: "fal_elevenlabs";
  voice_id: string;
  speaking_rate: number;
};

export type TutorialAction = {
  sequence: number;
  action_type:
    | "move"
    | "click"
    | "double_click"
    | "drag"
    | "keypress"
    | "type"
    | "scroll"
    | "wait"
    | "selection";
  ui_region: string;
  target_label: string | null;
  target_description: string;
  semantic_action: string;
  expected_visible_result: string;
  preferred_activation: "dom_js" | "cdp" | "vision_only";
  fallback_activation: "cdp" | null;
};

export type NarrationVariant = {
  text: string;
  fal_elevenlabs_audio_url: string;
  duration_ms: number;
};

export type Narration = {
  concise: NarrationVariant;
  detailed: NarrationVariant;
};

export type VoiceCue = {
  cue_id: string;
  phase:
    | "before_step"
    | "before_action"
    | "during_action"
    | "after_action"
    | "after_step"
    | "on_retry"
    | "on_user_interrupt";
  action_sequence: number;
  variant: "concise" | "detailed" | "both";
  text_ref: string;
  start_policy:
    | "play_before_motion"
    | "play_with_motion"
    | "play_after_validation"
    | "play_on_event";
  blocking: boolean;
};

export type DynamicCorrections = {
  retry: string;
  validation_failed: string;
  user_interrupt: string;
};

export type TutorialStep = {
  step_id: string;
  goal: string;
  preconditions: string[];
  actions: TutorialAction[];
  narration: Narration;
  voice_cues: VoiceCue[];
  dynamic_corrections: DynamicCorrections;
  expected_end_state: string;
  uncertainties: string[];
};

export type TutorialPlan = {
  tutorial_id: string;
  application: string;
  output_language: string;
  runtime_preferences: RuntimePreferences;
  voice: Voice;
  steps: TutorialStep[];
};

export type DemoCommand =
  | { type: "show" }
  | { type: "hide" }
  | { type: "move"; x: number; y: number; duration_ms?: number | null }
  | { type: "click" }
  | { type: "navigate"; direction: Direction }
  | { type: "load_tutorial"; plan: TutorialPlan; step?: number | null }
  | { type: "arm_takeover" }
  | { type: "disarm_takeover" };

export type DemoEnvelope = {
  version: 1;
  sequence: number;
  sent_at: string;
  command: DemoCommand;
};

export const isDemoEnvelope = (value: unknown): value is DemoEnvelope => {
  if (!isRecord(value) || value.version !== 1 || !Number.isInteger(value.sequence)) return false;
  if (typeof value.sent_at !== "string" || !isRecord(value.command)) return false;

  const command = value.command;
  switch (command.type) {
    case "show":
    case "hide":
    case "click":
    case "arm_takeover":
    case "disarm_takeover":
      return true;
    case "move":
      return isNonNegativeNumber(command.x) && isNonNegativeNumber(command.y) &&
        (command.duration_ms == null || isNonNegativeNumber(command.duration_ms));
    case "navigate":
      return command.direction === "left" || command.direction === "right";
    case "load_tutorial":
      return isTutorialPlan(command.plan) &&
        (command.step == null || isPositiveInteger(command.step));
    default:
      return false;
  }
};

const isTutorialPlan = (value: unknown): value is TutorialPlan => {
  if (!isRecord(value)) return false;
  return isNonEmptyString(value.tutorial_id) &&
    isNonEmptyString(value.application) &&
    isNonEmptyString(value.output_language) &&
    isRecord(value.runtime_preferences) &&
    typeof value.runtime_preferences.detailed_narration === "boolean" &&
    isVoice(value.voice) &&
    Array.isArray(value.steps) &&
    value.steps.length > 0 &&
    value.steps.every(isTutorialStep);
};

const isVoice = (value: unknown): value is Voice =>
  isRecord(value) &&
  value.provider === "fal_elevenlabs" &&
  isNonEmptyString(value.voice_id) &&
  typeof value.speaking_rate === "number" &&
  value.speaking_rate > 0;

const isTutorialStep = (value: unknown): value is TutorialStep => {
  if (!isRecord(value)) return false;
  return isNonEmptyString(value.step_id) &&
    isNonEmptyString(value.goal) &&
    isStringArray(value.preconditions) &&
    Array.isArray(value.actions) &&
    value.actions.length > 0 &&
    value.actions.every(isTutorialAction) &&
    isNarration(value.narration) &&
    Array.isArray(value.voice_cues) &&
    value.voice_cues.every(isVoiceCue) &&
    isDynamicCorrections(value.dynamic_corrections) &&
    isNonEmptyString(value.expected_end_state) &&
    isStringArray(value.uncertainties);
};

const actionTypes = new Set([
  "move", "click", "double_click", "drag", "keypress", "type", "scroll", "wait", "selection"
]);
const activationTypes = new Set(["dom_js", "cdp", "vision_only"]);

const isTutorialAction = (value: unknown): value is TutorialAction =>
  isRecord(value) &&
  isPositiveInteger(value.sequence) &&
  actionTypes.has(String(value.action_type)) &&
  isNonEmptyString(value.ui_region) &&
  (value.target_label === null || isNonEmptyString(value.target_label)) &&
  isNonEmptyString(value.target_description) &&
  isNonEmptyString(value.semantic_action) &&
  isNonEmptyString(value.expected_visible_result) &&
  activationTypes.has(String(value.preferred_activation)) &&
  (value.fallback_activation === null || value.fallback_activation === "cdp");

const isNarration = (value: unknown): value is Narration =>
  isRecord(value) && isNarrationVariant(value.concise) && isNarrationVariant(value.detailed);

const isNarrationVariant = (value: unknown): value is NarrationVariant =>
  isRecord(value) &&
  isNonEmptyString(value.text) &&
  isNonEmptyString(value.fal_elevenlabs_audio_url) &&
  isNonNegativeNumber(value.duration_ms);

const voiceCuePhases = new Set([
  "before_step", "before_action", "during_action", "after_action", "after_step", "on_retry",
  "on_user_interrupt"
]);
const voiceCueVariants = new Set(["concise", "detailed", "both"]);
const startPolicies = new Set([
  "play_before_motion", "play_with_motion", "play_after_validation", "play_on_event"
]);

const isVoiceCue = (value: unknown): value is VoiceCue =>
  isRecord(value) &&
  isNonEmptyString(value.cue_id) &&
  voiceCuePhases.has(String(value.phase)) &&
  isPositiveInteger(value.action_sequence) &&
  voiceCueVariants.has(String(value.variant)) &&
  isNonEmptyString(value.text_ref) &&
  startPolicies.has(String(value.start_policy)) &&
  typeof value.blocking === "boolean";

const isDynamicCorrections = (value: unknown): value is DynamicCorrections =>
  isRecord(value) &&
  isNonEmptyString(value.retry) &&
  isNonEmptyString(value.validation_failed) &&
  isNonEmptyString(value.user_interrupt);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object";
const isNonEmptyString = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0;
const isStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every((item) => typeof item === "string");
const isNonNegativeNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value) && value >= 0;
const isPositiveInteger = (value: unknown): value is number =>
  Number.isInteger(value) && Number(value) >= 1;
