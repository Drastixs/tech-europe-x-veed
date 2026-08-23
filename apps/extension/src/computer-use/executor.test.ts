import { describe, expect, it, vi } from "vitest";
import type { ExecuteActionCommand, TutorialAction } from "../overlay/protocol";
import {
  actionEnvironmentForOverlay,
  executeOnshapeAction,
  type ActionEnvironment,
  type PageElement
} from "./executor";

const element = (label: string): PageElement => ({
  textContent: label,
  parentElement: null,
  getAttribute: () => null
});

const clickAction = (overrides: Partial<TutorialAction> = {}): TutorialAction => ({
  sequence: 1,
  action_type: "click",
  parameters: { button: "primary" },
  ui_region: "feature tree",
  target_label: "Sketch 1",
  target_description: "Sketch 1 in the feature tree.",
  icon_description: "A blue sketch glyph beside the Sketch 1 label.",
  semantic_action: "Select Sketch 1.",
  expected_visible_result: "Sketch 1 is highlighted.",
  preferred_activation: "dom_js",
  fallback_activation: "cdp",
  ...overrides
} as TutorialAction);

const command = (action: TutorialAction = clickAction()): ExecuteActionCommand => ({
  type: "execute_action",
  action_id: "action_1",
  action,
  target: { x: 80, y: 300 },
  end_target: null
});

const environment = (target: PageElement | null = element("Sketch 1")): ActionEnvironment => ({
  elementFromPoint: vi.fn().mockReturnValue(target),
  isOverlayElement: vi.fn().mockReturnValue(false),
  click: vi.fn(),
  doubleClick: vi.fn().mockResolvedValue(undefined),
  typeText: vi.fn(),
  keypress: vi.fn(),
  scroll: vi.fn(),
  drag: vi.fn().mockResolvedValue(undefined),
  conditionVisible: vi.fn().mockReturnValue(true),
  expectedResultVisible: vi.fn().mockReturnValue(true),
  delay: vi.fn().mockResolvedValue(undefined)
});

describe("executeOnshapeAction", () => {
  it("clicks a localized element only when its label matches", async () => {
    const page = environment();

    const result = await executeOnshapeAction(command(), page);

    expect(result.type).toBe("action.completed");
    expect(result.success).toBe(true);
    expect(page.click).toHaveBeenCalledWith(expect.objectContaining({ textContent: "Sketch 1" }), "primary");
  });

  it("refuses a localized element with the wrong identity", async () => {
    const page = environment(element("Extrude"));

    const result = await executeOnshapeAction(command(), page);

    expect(result.type).toBe("action.failed");
    expect(result.outcome).toBe("retryable");
    expect(page.click).not.toHaveBeenCalled();
  });

  it("uses a retryable CDP fallback when the visible result is not observed", async () => {
    const page = environment();
    vi.mocked(page.expectedResultVisible).mockReturnValue(false);

    const result = await executeOnshapeAction(command(), page);

    expect(result).toMatchObject({
      type: "action.failed",
      outcome: "retryable",
      fallback_activation: "cdp",
      observed_visible_result: false
    });
  });

  it("refuses to interact with the assistant overlay", async () => {
    const page = environment();
    vi.mocked(page.isOverlayElement).mockReturnValue(true);

    const result = await executeOnshapeAction(command(), page);

    expect(result.success).toBe(false);
    expect(page.click).not.toHaveBeenCalled();
  });

  it("recognizes an overlay descendant across the Shadow DOM boundary", () => {
    const overlay = { contains: vi.fn().mockReturnValue(true) } as unknown as HTMLElement;
    const actionEnvironment = actionEnvironmentForOverlay(() => overlay);

    expect(actionEnvironment.isOverlayElement(element("Redo"))).toBe(true);
    expect(overlay.contains).toHaveBeenCalled();
  });

  it("passes typed text parameters to an editable target", async () => {
    const page = environment(element("Angle"));
    const action = clickAction({
      action_type: "type",
      target_label: "Angle",
      parameters: { text: "360", clear_existing: true, submit: true }
    } as Partial<TutorialAction>);

    const result = await executeOnshapeAction(command(action), page);

    expect(result.success).toBe(true);
    expect(page.typeText).toHaveBeenCalledWith(expect.anything(), "360", true, true);
  });

  it("executes zero-target scroll and wait primitives", async () => {
    const page = environment(null);
    const scroll = clickAction({
      action_type: "scroll",
      parameters: { delta_x: 0, delta_y: 500, duration_ms: 200 }
    } as Partial<TutorialAction>);
    const wait = clickAction({
      action_type: "wait",
      parameters: { duration_ms: 100, condition: "Revolve" }
    } as Partial<TutorialAction>);

    expect((await executeOnshapeAction(command(scroll), page)).success).toBe(true);
    expect((await executeOnshapeAction(command(wait), page)).success).toBe(true);
    expect(page.scroll).toHaveBeenCalledWith(0, 500);
    expect(page.conditionVisible).toHaveBeenCalledWith("Revolve");
  });

  it("requires a localized destination for drag", async () => {
    const page = environment();
    const drag = clickAction({
      action_type: "drag",
      parameters: {
        end_target_label: "Axis",
        end_target_description: "Vertical axis",
        duration_ms: 600
      }
    } as Partial<TutorialAction>);

    const result = await executeOnshapeAction(command(drag), page);

    expect(result.type).toBe("action.failed");
    expect(page.drag).not.toHaveBeenCalled();
  });
});
