import type { TutorialStep } from "../overlay/protocol";

export const completedUndoCount = (step: TutorialStep, completedActions: number) =>
  step.actions.slice(0, completedActions).filter((action) => {
    if (action.action_type === "type") return action.parameters.submit;
    if (action.action_type !== "click" && action.action_type !== "selection") return false;

    const intent = action.semantic_action.trim().toLocaleLowerCase();
    return intent.startsWith("create ") ||
      intent.startsWith("commit ") ||
      /^set (?:the )?.*radius\b/.test(intent) ||
      /^set (?:the )?.*endpoint\b/.test(intent);
  }).length;
