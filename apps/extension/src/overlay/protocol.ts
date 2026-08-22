export type Direction = "left" | "right";

export type RuntimePreferences = {
  detailed_narration: boolean;
};

export type Voice = {
  provider: "fal_elevenlabs";
  voice_id: string;
  speaking_rate: number;
};

type TutorialActionBase = {
  sequence: number;
  ui_region: string;
  target_label: string | null;
  target_description: string;
  icon_description: string | null;
  semantic_action: string;
  expected_visible_result: string;
  preferred_activation: "dom_js" | "cdp" | "vision_only";
  fallback_activation: "cdp" | null;
};

export type TutorialAction = TutorialActionBase & (
  | { action_type: "move"; parameters: { duration_ms: number } }
  | {
      action_type: "click";
      parameters: { button: "primary" | "secondary" | "middle" };
    }
  | {
      action_type: "double_click";
      parameters: {
        button: "primary" | "secondary" | "middle";
        interval_ms: number;
      };
    }
  | {
      action_type: "drag";
      parameters: {
        end_target_label: string | null;
        end_target_description: string;
        duration_ms: number;
      };
    }
  | {
      action_type: "keypress";
      parameters: {
        key: string;
        modifiers: Array<"alt" | "control" | "meta" | "shift">;
        repeat: number;
      };
    }
  | {
      action_type: "type";
      parameters: { text: string; clear_existing: boolean; submit: boolean };
    }
  | {
      action_type: "scroll";
      parameters: { delta_x: number; delta_y: number; duration_ms: number };
    }
  | {
      action_type: "wait";
      parameters: { duration_ms: number | null; condition: string | null };
    }
  | {
      action_type: "selection";
      parameters: {
        items: string[];
        mode: "replace" | "add" | "toggle";
        confirm: boolean;
      };
    }
);

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

export type OverlayCommand =
  | { type: "show" }
  | { type: "hide" }
  | { type: "move"; x: number; y: number; duration_ms?: number | null }
  | { type: "click" }
  | { type: "navigate"; direction: Direction }
  | { type: "load_tutorial"; plan: TutorialPlan; step?: number | null }
  | { type: "arm_takeover" }
  | { type: "disarm_takeover" };

export type PixelPoint = { x: number; y: number };

export type CaptureObservationCommand = {
  type: "capture_observation";
  request_id: string;
};

export type ExecuteActionCommand = {
  type: "execute_action";
  action_id: string;
  action: TutorialAction;
  target: PixelPoint;
  end_target: PixelPoint | null;
};

export type ComputerUseCommand = CaptureObservationCommand | ExecuteActionCommand;
export type DemoCommand = OverlayCommand | ComputerUseCommand;

export type ViewportObservation = {
  width: number;
  height: number;
  device_pixel_ratio: number;
};

export type ObservationCapturedEvent = {
  type: "observation.captured";
  request_id: string;
  screenshot_data_url: string;
  viewport: ViewportObservation;
  url: string;
};

export type ObservationFailedEvent = {
  type: "observation.failed";
  request_id: string;
  reason: string;
};

export type ActionCompletedEvent = {
  type: "action.completed" | "action.failed";
  action_id: string;
  success: boolean;
  reason: string | null;
  element_description: string | null;
};

export type ComputerUseEvent =
  | ObservationCapturedEvent
  | ObservationFailedEvent
  | ActionCompletedEvent;

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
    case "capture_observation":
      return isNonEmptyString(command.request_id);
    case "execute_action":
      return isNonEmptyString(command.action_id) &&
        isTutorialAction(command.action) &&
        isPixelPoint(command.target) &&
        (command.end_target === null || isPixelPoint(command.end_target));
    default:
      return false;
  }
};

export const isOverlayCommand = (command: DemoCommand): command is OverlayCommand =>
  command.type !== "capture_observation" && command.type !== "execute_action";

export const isCaptureObservationCommand = (
  command: DemoCommand
): command is CaptureObservationCommand => command.type === "capture_observation";

export const isExecuteActionCommand = (
  command: DemoCommand
): command is ExecuteActionCommand => command.type === "execute_action";

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

const activationTypes = new Set(["dom_js", "cdp", "vision_only"]);

const isTutorialAction = (value: unknown): value is TutorialAction => {
  if (!isRecord(value) ||
    !isPositiveInteger(value.sequence) ||
    !isNonEmptyString(value.ui_region) ||
    (value.target_label !== null && !isNonEmptyString(value.target_label)) ||
    !isNonEmptyString(value.target_description) ||
    (value.icon_description !== null && !isNonEmptyString(value.icon_description)) ||
    !isNonEmptyString(value.semantic_action) ||
    !isNonEmptyString(value.expected_visible_result) ||
    !activationTypes.has(String(value.preferred_activation)) ||
    (value.fallback_activation !== null && value.fallback_activation !== "cdp")) return false;

  return isActionParameters(value.action_type, value.parameters);
};

const isActionParameters = (actionType: unknown, value: unknown): boolean => {
  if (!isRecord(value)) return false;
  switch (actionType) {
    case "move":
      return hasOnlyKeys(value, ["duration_ms"]) && isIntegerBetween(value.duration_ms, 0, 10_000);
    case "click":
      return hasOnlyKeys(value, ["button"]) && isPointerButton(value.button);
    case "double_click":
      return hasOnlyKeys(value, ["button", "interval_ms"]) &&
        isPointerButton(value.button) && isIntegerBetween(value.interval_ms, 0, 1_000);
    case "drag":
      return hasOnlyKeys(value, ["end_target_label", "end_target_description", "duration_ms"]) &&
        (value.end_target_label === null || isNonEmptyString(value.end_target_label)) &&
        isNonEmptyString(value.end_target_description) &&
        isIntegerBetween(value.duration_ms, 0, 10_000);
    case "keypress":
      return hasOnlyKeys(value, ["key", "modifiers", "repeat"]) &&
        isNonEmptyString(value.key) &&
        Array.isArray(value.modifiers) &&
        value.modifiers.every((modifier) =>
          modifier === "alt" || modifier === "control" || modifier === "meta" || modifier === "shift"
        ) &&
        isIntegerBetween(value.repeat, 1, 100);
    case "type":
      return hasOnlyKeys(value, ["text", "clear_existing", "submit"]) &&
        isNonEmptyString(value.text) &&
        typeof value.clear_existing === "boolean" &&
        typeof value.submit === "boolean";
    case "scroll":
      return hasOnlyKeys(value, ["delta_x", "delta_y", "duration_ms"]) &&
        Number.isInteger(value.delta_x) && Number.isInteger(value.delta_y) &&
        (value.delta_x !== 0 || value.delta_y !== 0) &&
        isIntegerBetween(value.duration_ms, 0, 10_000);
    case "wait":
      return hasOnlyKeys(value, ["duration_ms", "condition"]) &&
        (value.duration_ms === null || isIntegerBetween(value.duration_ms, 0, 60_000)) &&
        (value.condition === null || isNonEmptyString(value.condition)) &&
        (value.duration_ms !== null || value.condition !== null);
    case "selection":
      return hasOnlyKeys(value, ["items", "mode", "confirm"]) &&
        isNonEmptyStringArray(value.items) &&
        (value.mode === "replace" || value.mode === "add" || value.mode === "toggle") &&
        typeof value.confirm === "boolean";
    default:
      return false;
  }
};

const isPointerButton = (value: unknown) =>
  value === "primary" || value === "secondary" || value === "middle";
const hasOnlyKeys = (value: Record<string, unknown>, keys: string[]) =>
  Object.keys(value).length === keys.length && keys.every((key) => key in value);
const isIntegerBetween = (value: unknown, minimum: number, maximum: number) =>
  Number.isInteger(value) && Number(value) >= minimum && Number(value) <= maximum;
const isNonEmptyStringArray = (value: unknown): value is string[] =>
  Array.isArray(value) && value.length > 0 && value.every(isNonEmptyString);
const isPixelPoint = (value: unknown): value is PixelPoint =>
  isRecord(value) && isNonNegativeNumber(value.x) && isNonNegativeNumber(value.y);

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
