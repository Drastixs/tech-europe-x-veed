from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .holo import HoloClient, LocalizationContext


class ComputerUseError(Exception):
    """A recoverable extension transport or action-execution failure."""


class Viewport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    device_pixel_ratio: float = Field(gt=0)


class PixelPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)


class DemonstrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    normalized_target: PixelPoint
    viewport_target: PixelPoint
    executed: bool
    success: bool
    reason: str | None
    element_description: str | None


class ActionContext(Protocol):
    action_type: str
    target_label: str | None
    target_description: str
    ui_region: str
    semantic_action: str
    parameters: Any

    def model_dump(self) -> dict[str, Any]: ...


PublishCommand = Callable[[dict[str, Any]], Awaitable[None]]
RequestExtension = Callable[[dict[str, Any], str, float], Awaitable[dict[str, Any]]]


class ExtensionEventBroker:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def prepare(self, correlation_id: str) -> asyncio.Future[dict[str, Any]]:
        if correlation_id in self._pending:
            raise ComputerUseError(f"duplicate extension request {correlation_id}")
        future = asyncio.get_running_loop().create_future()
        self._pending[correlation_id] = future
        return future

    def resolve(self, event: dict[str, Any]) -> bool:
        correlation_id = event.get("request_id") or event.get("action_id")
        if not isinstance(correlation_id, str):
            return False
        future = self._pending.get(correlation_id)
        if future is None or future.done():
            return False
        future.set_result(event)
        return True

    def cancel(self, correlation_id: str) -> None:
        future = self._pending.pop(correlation_id, None)
        if future is not None and not future.done():
            future.cancel()

    async def wait(
        self,
        correlation_id: str,
        future: asyncio.Future[dict[str, Any]],
        timeout_seconds: float,
    ) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(future, timeout_seconds)
        except TimeoutError as exc:
            raise ComputerUseError("The browser extension did not respond in time") from exc
        finally:
            self._pending.pop(correlation_id, None)


class DemoRunner:
    def __init__(
        self,
        *,
        holo: HoloClient,
        publish_command: PublishCommand,
        request_extension: RequestExtension,
        timeout_seconds: float = 15,
    ) -> None:
        self.holo = holo
        self.publish_command = publish_command
        self.request_extension = request_extension
        self.timeout_seconds = timeout_seconds

    async def demonstrate(
        self, action: ActionContext, *, step_goal: str | None, execute: bool
    ) -> DemonstrationResult:
        request_id = f"observation_{uuid4().hex}"
        observation = await self.request_extension(
            {"type": "capture_observation", "request_id": request_id},
            request_id,
            self.timeout_seconds,
        )
        if observation.get("type") != "observation.captured":
            raise ComputerUseError(str(observation.get("reason") or "Screenshot capture failed"))

        screenshot = observation.get("screenshot_data_url")
        if not isinstance(screenshot, str):
            raise ComputerUseError("Screenshot response did not include image data")
        viewport = Viewport.model_validate(observation.get("viewport"))
        normalized = await self.holo.localize(
            screenshot,
            LocalizationContext(
                target_description=action.target_description,
                target_label=action.target_label,
                ui_region=action.ui_region,
                semantic_action=action.semantic_action,
                step_goal=step_goal,
            ),
        )
        target = PixelPoint(
            x=min(viewport.width - 1, round(normalized.x / 1000 * viewport.width)),
            y=min(viewport.height - 1, round(normalized.y / 1000 * viewport.height)),
        )
        await self.publish_command(
            {"type": "move", "x": target.x, "y": target.y, "duration_ms": 420}
        )

        action_id = f"action_{uuid4().hex}"
        if not execute:
            return DemonstrationResult(
                action_id=action_id,
                normalized_target=PixelPoint(x=normalized.x, y=normalized.y),
                viewport_target=target,
                executed=False,
                success=True,
                reason=None,
                element_description=None,
            )

        command: dict[str, Any] = {
            "type": "execute_action",
            "action_id": action_id,
            "action": action.model_dump(),
            "target": target.model_dump(),
            "end_target": None,
        }
        if action.action_type == "drag":
            end_context = LocalizationContext(
                target_description=action.parameters.end_target_description,
                target_label=action.parameters.end_target_label,
                ui_region=action.ui_region,
                semantic_action=action.semantic_action,
                step_goal=step_goal,
            )
            end = await self.holo.localize(screenshot, end_context)
            command["end_target"] = PixelPoint(
                x=min(viewport.width - 1, round(end.x / 1000 * viewport.width)),
                y=min(viewport.height - 1, round(end.y / 1000 * viewport.height)),
            ).model_dump()

        result = await self.request_extension(command, action_id, self.timeout_seconds)
        if result.get("type") != "action.completed":
            return DemonstrationResult(
                action_id=action_id,
                normalized_target=PixelPoint(x=normalized.x, y=normalized.y),
                viewport_target=target,
                executed=True,
                success=False,
                reason=str(result.get("reason") or "Action execution failed"),
                element_description=result.get("element_description"),
            )
        return DemonstrationResult(
            action_id=action_id,
            normalized_target=PixelPoint(x=normalized.x, y=normalized.y),
            viewport_target=target,
            executed=True,
            success=bool(result.get("success")),
            reason=result.get("reason"),
            element_description=result.get("element_description"),
        )
