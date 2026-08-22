from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from .config import load_backend_env

SYSTEM_INSTRUCTIONS = """You turn timestamped video-analysis JSON into an executable Onshape
tutorial plan. Preserve action order, visible UI targets, expected results, preconditions, and
uncertainties. Group atomic actions into goal-oriented steps without inventing actions.

Write two spoken narration variants for every step. Concise narration states intent and result;
detailed narration previews each visible action in order. Never mention coordinates, DOM, CDP,
JavaScript, model confidence, hidden reasoning, or implementation mechanisms in narration.

The response must match the supplied JSON schema. Audio is enriched after planning: set every
fal_elevenlabs_audio_url to a unique pending://tts/<step-id>/<variant> URI and duration_ms to 0.
Use one-based action sequences and reference an existing action sequence in every voice cue.
"""


@dataclass(slots=True)
class PlannerError(Exception):
    message: str
    status_code: int = 502

    def __str__(self) -> str:
        return self.message


class OpenAIPlanner:
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
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5-mini")
        self.base_url = (
            base_url or os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
        ).rstrip("/")
        configured_timeout = os.getenv("OPENAI_TIMEOUT_SECONDS", "60")
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else float(configured_timeout)
        )
        self.client = client

    async def generate(
        self, *, input_payload: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.api_key:
            raise PlannerError("OPENAI_API_KEY is not configured", status_code=503)

        request = {
            "model": self.model,
            "instructions": SYSTEM_INSTRUCTIONS,
            "input": json.dumps(input_payload, separators=(",", ":"), ensure_ascii=False),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "tutorial_plan",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            if self.client is not None:
                response = await self.client.post(
                    f"{self.base_url}/responses",
                    json=request,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/responses", json=request, headers=headers
                    )
        except httpx.TimeoutException as exc:
            raise PlannerError("OpenAI planning request timed out", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise PlannerError("OpenAI planning request failed") from exc

        if response.is_error:
            request_id = response.headers.get("x-request-id")
            suffix = f" (request {request_id})" if request_id else ""
            raise PlannerError(f"OpenAI planning request returned {response.status_code}{suffix}")

        try:
            body = response.json()
        except ValueError as exc:
            raise PlannerError("OpenAI planning response was not JSON") from exc

        status = body.get("status")
        if status not in (None, "completed"):
            detail = body.get("incomplete_details", {}).get("reason", status)
            raise PlannerError(f"OpenAI planning response did not complete: {detail}")

        refusal = _find_refusal(body)
        if refusal:
            raise PlannerError(f"OpenAI refused to generate the tutorial plan: {refusal}", 422)

        output_text = _find_output_text(body)
        if output_text is None:
            raise PlannerError("OpenAI planning response contained no structured output")
        try:
            parsed = json.loads(output_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PlannerError(
                "OpenAI planning response contained invalid structured JSON"
            ) from exc
        if not isinstance(parsed, dict):
            raise PlannerError("OpenAI planning response must be a JSON object")
        return parsed


def _find_output_text(body: dict[str, Any]) -> str | None:
    top_level = body.get("output_text")
    if isinstance(top_level, str) and top_level:
        return top_level
    for output in body.get("output", []):
        if not isinstance(output, dict):
            continue
        if output.get("type") == "output_text" and isinstance(output.get("text"), str):
            return output["text"]
        for content in output.get("content", []):
            if (
                isinstance(content, dict)
                and content.get("type") in ("output_text", "text")
                and isinstance(content.get("text"), str)
            ):
                return content["text"]
    return None


def _find_refusal(body: dict[str, Any]) -> str | None:
    for output in body.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("type") == "refusal":
                refusal = content.get("refusal")
                return refusal if isinstance(refusal, str) else "request refused"
    return None
