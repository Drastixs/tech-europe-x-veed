from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .config import load_backend_env


class HoloError(Exception):
    """A recoverable Holo request or response failure."""


class HoloConfigurationError(HoloError):
    """The Holo client cannot start with the current environment."""


class LocalizedPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: int = Field(ge=0, le=1000)
    y: int = Field(ge=0, le=1000)


@dataclass(frozen=True, slots=True)
class LocalizationContext:
    target_description: str
    target_label: str | None = None
    ui_region: str | None = None
    semantic_action: str | None = None
    step_goal: str | None = None

    def prompt(self, schema: dict) -> str:
        details = [f"Target description: {self.target_description}"]
        if self.target_label:
            details.append(f"Visible label: {self.target_label}")
        if self.ui_region:
            details.append(f"Expected UI region: {self.ui_region}")
        if self.semantic_action:
            details.append(f"Action: {self.semantic_action}")
        if self.step_goal:
            details.append(f"Step goal: {self.step_goal}")
        return (
            "Localize the requested element in this GUI screenshot and return a safe click "
            "position. Coordinates must be integers normalized to [0, 1000].\n"
            f"Output valid JSON matching this schema: {json.dumps(schema, separators=(',', ':'))}\n"
            + "\n".join(details)
        )


class HoloClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        load_backend_env()
        self.api_key = api_key if api_key is not None else os.getenv("HAI_API_KEY")
        self.model = model or os.getenv("HAI_MODEL", "holo3-1-35b-a3b")
        self.base_url = (
            base_url or os.getenv("HAI_API_BASE", "https://api.hcompany.ai/v1")
        ).rstrip("/")
        self.timeout_seconds = timeout_seconds or float(os.getenv("HAI_TIMEOUT_SECONDS", "30"))
        self.client = client

    async def localize(
        self, screenshot_data_url: str, context: LocalizationContext
    ) -> LocalizedPoint:
        if not self.api_key:
            raise HoloConfigurationError("HAI_API_KEY is not configured")
        if not screenshot_data_url.startswith("data:image/"):
            raise HoloError("Holo localization requires an image data URL")

        schema = LocalizedPoint.model_json_schema()
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": screenshot_data_url}},
                        {"type": "text", "text": context.prompt(schema)},
                    ],
                }
            ],
            "structured_outputs": {"json": schema},
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": 0.0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            if self.client is not None:
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions", json=payload, headers=headers
                    )
        except httpx.TimeoutException as exc:
            raise HoloError("Holo localization timed out") from exc
        except httpx.HTTPError as exc:
            raise HoloError("Holo localization request failed") from exc

        if response.is_error:
            request_id = response.headers.get("x-request-id")
            suffix = f" (request {request_id})" if request_id else ""
            raise HoloError(f"Holo returned {response.status_code}{suffix}")

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            return LocalizedPoint.model_validate_json(content)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            raise HoloError("Holo returned an invalid localization response") from exc
