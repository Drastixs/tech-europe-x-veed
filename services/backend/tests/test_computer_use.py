from __future__ import annotations

import asyncio
from typing import Any

import pytest

from onshape_assist.app import ClickAction, DragAction
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

    async def localize(self, screenshot_data_url, context):
        assert screenshot_data_url.startswith("data:image/png")
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
