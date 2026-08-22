from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from .config import load_backend_env

SYSTEM_INSTRUCTIONS = """You are the tutorial planner and voice director for an Onshape
in-browser teaching assistant. Convert timestamped video-analysis JSON into an executable plan.

PLANNING
- Group atomic actions into user-meaningful steps with one semantic goal each.
- Preserve every source action exactly once and in chronological order; never invent an action.
- Preserve UI regions, target labels, visible results, warnings, and uncertainty notes.
- Define the visible preconditions and expected end state for every step.
- Number each step's actions contiguously from one.

ACTIVATION
- Prefer dom_js for stable DOM or accessibility targets, with cdp as fallback.
- Prefer cdp for canvas, WebGL, drag, keyboard, inaccessible, or unstable targets.
- Use vision_only only when the evidence supports observation without activation.
- Activation fields guide another system; never mention them in spoken narration.

VOICE
- Write both variants for every step. Concise states the intent or result briefly. Detailed
  previews every visible action in its exact order before the demonstration.
- Narrate only user-visible actions, intent, warnings, and results. Never mention coordinates,
  DOM, CDP, JavaScript, APIs, model confidence, hidden reasoning, or implementation mechanisms.
- Provide short retry, target-relocation, validation-failure, and user-interruption correction lines.

TIMING
- Provide cues for entry narration and relevant correction events. Each cue must reference an
  action sequence that exists in its step. Detailed entry narration normally plays before motion.
- Use blocking only when motion must wait for narration; event corrections use play_on_event.

OUTPUT
- Match the supplied JSON schema exactly and output nothing outside it.
- Audio is generated after planning. Set every fal_elevenlabs_audio_url to a unique
  pending://tts/<step-id>/<variant> URI and every duration_ms to 0.
"""


@dataclass(slots=True)
class PlannerError(Exception):
    message: str
    status_code: int = 502
    code: str = "provider_error"

    def __str__(self) -> str:
        return self.message

    def envelope(self) -> dict[str, str]:
        return error_envelope(self.code, self.message)


def error_envelope(code: str, message: str) -> dict[str, str]:
    return {
        "version": "tutorial-planner-error/v1",
        "code": code,
        "message": message,
    }


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
            raise PlannerError(
                "OPENAI_API_KEY is not configured",
                status_code=503,
                code="configuration_error",
            )

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
            raise PlannerError(
                "OpenAI planning request timed out", status_code=504, code="provider_timeout"
            ) from exc
        except httpx.HTTPError as exc:
            raise PlannerError("OpenAI planning request failed", code="provider_request_failed") from exc

        if response.is_error:
            request_id = response.headers.get("x-request-id")
            suffix = f" (request {request_id})" if request_id else ""
            raise PlannerError(
                f"OpenAI planning request returned {response.status_code}{suffix}",
                code="provider_response_error",
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise PlannerError("OpenAI planning response was not JSON", code="invalid_response") from exc

        status = body.get("status")
        if status not in (None, "completed"):
            detail = body.get("incomplete_details", {}).get("reason", status)
            raise PlannerError(
                f"OpenAI planning response did not complete: {detail}", code="incomplete_response"
            )

        refusal = _find_refusal(body)
        if refusal:
            raise PlannerError(
                f"OpenAI refused to generate the tutorial plan: {refusal}",
                422,
                "model_refusal",
            )

        output_text = _find_output_text(body)
        if output_text is None:
            raise PlannerError(
                "OpenAI planning response contained no structured output", code="missing_structured_output"
            )
        try:
            parsed = json.loads(output_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise PlannerError(
                "OpenAI planning response contained invalid structured JSON",
                code="invalid_structured_output",
            ) from exc
        if not isinstance(parsed, dict):
            raise PlannerError(
                "OpenAI planning response must be a JSON object", code="invalid_structured_output"
            )
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
