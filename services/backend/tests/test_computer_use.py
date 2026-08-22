from __future__ import annotations

import asyncio
from typing import Any

import pytest

from onshape_assist.app import ClickAction, DragAction, TutorialStep
from onshape_assist.computer_use import (
    ComputerUseError,
    DemoRunner,
    ExtensionEventBroker,
)
from onshape_assist.holo import LocalizedPoint


class FakeHolo:
    def __init__(self, points: list[LocalizedPoint] | None = None) -> None:
        self.points = points or [LocalizedPoint(x=500, y=250)]
        self.contexts = []
        self.screenshots = []

    async def localize(self, screenshot_data_url, context):
        assert screenshot_data_url.startswith("data:image/png")
        self.screenshots.append(screenshot_data_url)
        self.contexts.append(context)
        return self.points.pop(0)


def click_action() -> ClickAction:
    return ClickAction(
        sequence=1,
        action_type="click",
        parameters={"button": "primary"},
        ui_region="feature tree",
        target_label="Sketch 1",
        target_description="Sketch 1 in the feature tree.",
        icon_description="A blue sketch glyph beside the Sketch 1 label.",
        semantic_action="Select Sketch 1.",
        expected_visible_result="Sketch 1 is highlighted.",
        preferred_activation="dom_js",
        fallback_activation="cdp",
    )


def observation() -> dict[str, Any]:
    return {
        "type": "observation.captured",
        "request_id": "dynamic",
        "screenshot_data_url": "data:image/png;base64,c2NyZWVu",
        "viewport": {"width": 1440, "height": 900, "device_pixel_ratio": 2},
        "url": "https://cad.onshape.com/documents/demo/w/one/e/two",
    }


def tutorial_step(actions: list[ClickAction]) -> TutorialStep:
    return TutorialStep(
        step_id="open-revolve",
        goal="Open Revolve",
        preconditions=["Sketch 1 is visible."],
        actions=actions,
        narration={
            "concise": {
                "text": "Open Revolve.",
                "fal_elevenlabs_audio_url": "fal://concise",
                "duration_ms": 1000,
            },
            "detailed": {
                "text": "Select the sketch, then open Revolve.",
                "fal_elevenlabs_audio_url": "fal://detailed",
                "duration_ms": 2000,
            },
        },
        voice_cues=[
            {
                "cue_id": "intro",
                "phase": "before_step",
                "action_sequence": 1,
                "variant": "both",
                "text_ref": "narration.concise.text",
                "start_policy": "play_before_motion",
                "blocking": True,
            }
        ],
        dynamic_corrections={
            "retry": "Try again.",
            "validation_failed": "Pause.",
            "user_interrupt": "Stopping.",
        },
        expected_end_state="Revolve is open.",
        uncertainties=[],
    )


def test_demo_runner_localizes_moves_and_executes_one_action():
    published = []
    requested = []

    async def publish(command):
        published.append(command)

    async def request(command, correlation_id, _timeout):
        requested.append(command)
        if command["type"] == "capture_observation":
            return {**observation(), "request_id": correlation_id}
        return {
            "type": "action.completed",
            "action_id": correlation_id,
            "success": True,
            "reason": None,
            "element_description": "Sketch 1",
        }

    runner = DemoRunner(
        holo=FakeHolo(),
        publish_command=publish,
        request_extension=request,
    )
    result = asyncio.run(
        runner.demonstrate(click_action(), step_goal="Open Revolve", execute=True)
    )

    assert result.success is True
    assert result.normalized_target.model_dump() == {"x": 500, "y": 250}
    assert result.viewport_target.model_dump() == {"x": 720, "y": 225}
    assert published == [{"type": "move", "x": 720, "y": 225, "duration_ms": 420}]
    assert [item["type"] for item in requested] == ["capture_observation", "execute_action"]
    assert requested[1]["action"]["parameters"] == {"button": "primary"}


def test_demo_runner_executes_a_step_sequentially_with_fresh_screenshots():
    requested = []
    screenshot_number = 0
    second_action = click_action().model_copy(
        update={
            "sequence": 2,
            "target_label": "Revolve",
            "target_description": "Revolve in the toolbar.",
            "icon_description": "A profile rotating around a vertical axis.",
            "semantic_action": "Open Revolve.",
        }
    )
    holo = FakeHolo([LocalizedPoint(x=100, y=200), LocalizedPoint(x=750, y=500)])

    async def request(command, correlation_id, _timeout):
        nonlocal screenshot_number
        requested.append((command, correlation_id))
        if command["type"] == "capture_observation":
            screenshot_number += 1
            return {
                **observation(),
                "request_id": correlation_id,
                "screenshot_data_url": (
                    f"data:image/png;base64,screenshot-{screenshot_number}"
                ),
            }
        return {
            "type": "action.completed",
            "action_id": correlation_id,
            "success": True,
            "reason": None,
            "element_description": command["action"]["target_label"],
        }

    runner = DemoRunner(
        holo=holo,
        publish_command=lambda _: asyncio.sleep(0),
        request_extension=request,
    )
    result = asyncio.run(
        runner.demonstrate_step(tutorial_step([click_action(), second_action]), execute=True)
    )

    assert result.success is True
    assert result.completed_actions == 2
    assert result.failed_action_sequence is None
    assert [item[0]["type"] for item in requested] == [
        "capture_observation",
        "execute_action",
        "capture_observation",
        "execute_action",
    ]
    assert requested[1][0]["action"]["sequence"] == 1
    assert requested[3][0]["action"]["sequence"] == 2
    assert requested[0][1] != requested[2][1]
    assert holo.screenshots == [
        "data:image/png;base64,screenshot-1",
        "data:image/png;base64,screenshot-2",
    ]
    assert holo.contexts[0].icon_description == (
        "A blue sketch glyph beside the Sketch 1 label."
    )
    assert holo.contexts[1].icon_description == (
        "A profile rotating around a vertical axis."
    )
    assert result.results[1].viewport_target.model_dump() == {"x": 1080, "y": 450}


def test_demo_runner_stops_a_step_after_an_action_failure():
    requested = []
    executed_actions = 0
    actions = [
        click_action(),
        click_action().model_copy(update={"sequence": 2}),
        click_action().model_copy(update={"sequence": 3}),
    ]

    async def request(command, correlation_id, _timeout):
        nonlocal executed_actions
        requested.append(command)
        if command["type"] == "capture_observation":
            return {**observation(), "request_id": correlation_id}
        executed_actions += 1
        if executed_actions == 1:
            return {
                "type": "action.completed",
                "action_id": correlation_id,
                "success": True,
                "reason": None,
                "element_description": "Sketch 1",
            }
        return {
            "type": "action.failed",
            "action_id": correlation_id,
            "success": False,
            "reason": "Target did not match",
            "element_description": None,
        }

    runner = DemoRunner(
        holo=FakeHolo([LocalizedPoint(x=500, y=250), LocalizedPoint(x=600, y=300)]),
        publish_command=lambda _: asyncio.sleep(0),
        request_extension=request,
    )
    result = asyncio.run(runner.demonstrate_step(tutorial_step(actions), execute=True))

    assert result.success is False
    assert result.completed_actions == 1
    assert result.reason == "Target did not match"
    assert result.failed_action_sequence == 2
    assert len(result.results) == 2
    assert [item["type"] for item in requested] == [
        "capture_observation",
        "execute_action",
        "capture_observation",
        "execute_action",
    ]


def test_demo_runner_preserves_partial_results_when_a_later_capture_fails():
    requested = []
    actions = [click_action(), click_action().model_copy(update={"sequence": 2})]

    async def request(command, correlation_id, _timeout):
        requested.append(command)
        if command["type"] == "capture_observation" and len(requested) == 1:
            return {**observation(), "request_id": correlation_id}
        if command["type"] == "capture_observation":
            return {
                "type": "observation.failed",
                "request_id": correlation_id,
                "reason": "Browser capture failed",
            }
        return {
            "type": "action.completed",
            "action_id": correlation_id,
            "success": True,
            "reason": None,
            "element_description": "Sketch 1",
        }

    runner = DemoRunner(
        holo=FakeHolo(),
        publish_command=lambda _: asyncio.sleep(0),
        request_extension=request,
    )
    result = asyncio.run(runner.demonstrate_step(tutorial_step(actions), execute=True))

    assert result.success is False
    assert result.completed_actions == 1
    assert result.failed_action_sequence == 2
    assert result.reason == "Browser capture failed"
    assert len(result.results) == 1


def test_demo_runner_dry_run_does_not_count_grounded_actions_as_completed():
    actions = [click_action(), click_action().model_copy(update={"sequence": 2})]

    async def request(command, correlation_id, _timeout):
        return {**observation(), "request_id": correlation_id}

    runner = DemoRunner(
        holo=FakeHolo([LocalizedPoint(x=500, y=250), LocalizedPoint(x=600, y=300)]),
        publish_command=lambda _: asyncio.sleep(0),
        request_extension=request,
    )
    result = asyncio.run(runner.demonstrate_step(tutorial_step(actions), execute=False))

    assert result.success is True
    assert result.completed_actions == 0
    assert len(result.results) == 2
    assert all(not action_result.executed for action_result in result.results)


def test_demo_runner_can_ground_without_executing():
    requested = []

    async def request(command, correlation_id, _timeout):
        requested.append(command)
        return {**observation(), "request_id": correlation_id}

    runner = DemoRunner(
        holo=FakeHolo(),
        publish_command=lambda _: asyncio.sleep(0),
        request_extension=request,
    )
    result = asyncio.run(runner.demonstrate(click_action(), step_goal=None, execute=False))

    assert result.executed is False
    assert result.success is True
    assert [item["type"] for item in requested] == ["capture_observation"]


def test_demo_runner_localizes_both_drag_endpoints():
    commands = []
    holo = FakeHolo([LocalizedPoint(x=100, y=200), LocalizedPoint(x=800, y=700)])
    action = DragAction(
        **click_action().model_dump(exclude={"action_type", "parameters"}),
        action_type="drag",
        parameters={
            "end_target_label": "Axis",
            "end_target_description": "The vertical construction line.",
            "duration_ms": 600,
        },
    )

    async def request(command, correlation_id, _timeout):
        commands.append(command)
        if command["type"] == "capture_observation":
            return {**observation(), "request_id": correlation_id}
        return {
            "type": "action.completed",
            "action_id": correlation_id,
            "success": True,
            "reason": None,
            "element_description": "Sketch 1",
        }

    runner = DemoRunner(
        holo=holo,
        publish_command=lambda _: asyncio.sleep(0),
        request_extension=request,
    )
    asyncio.run(runner.demonstrate(action, step_goal=None, execute=True))

    assert commands[1]["target"] == {"x": 144, "y": 180}
    assert commands[1]["end_target"] == {"x": 1152, "y": 630}
    assert len(holo.contexts) == 2


def test_extension_event_broker_correlates_and_times_out():
    async def correlate():
        broker = ExtensionEventBroker()
        future = broker.prepare("obs_1")
        assert broker.resolve({"type": "observation.captured", "request_id": "obs_1"})
        result = await broker.wait("obs_1", future, 0.1)
        assert result["type"] == "observation.captured"
        assert not broker.resolve({"request_id": "unknown"})

        timeout_future = broker.prepare("obs_2")
        with pytest.raises(ComputerUseError, match="did not respond"):
            await broker.wait("obs_2", timeout_future, 0.001)

    asyncio.run(correlate())
