"""Thin async wrappers around the two fal partner models used by the analyzer.

The pipeline deliberately mixes two fal models:

* ``openrouter/router/video`` (Gemini) — primary structured pass. Accepts YouTube
  links directly and follows the forensic system prompt to emit the JSON contract.
* ``fal-ai/video-understanding`` — enrichment/verification pass. Produces an
  independent plain-language description of the UI and actions used to cross-check
  and enrich the primary result.

Both are called via ``fal_client``; a ``runner`` callable can be injected to make
the pipeline testable without network access.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import fal_client

# Model identifiers.
ROUTER_VIDEO_MODEL = "openrouter/router/video"
VIDEO_UNDERSTANDING_MODEL = "fal-ai/video-understanding"

# Default underlying LLM for the OpenRouter video router. Gemini has native video
# understanding and (on AI Studio) accepts YouTube links directly.
DEFAULT_GEMINI_MODEL = "google/gemini-3.1-pro-preview"

# A runner takes a fal model id and its arguments and returns the result payload.
Runner = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class FalError(RuntimeError):
    """Raised when a fal model call fails or returns an unusable payload."""


async def _default_runner(model_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        return await fal_client.subscribe_async(model_id, arguments=arguments)
    except Exception as exc:
        raise FalError(f"fal call to {model_id!r} failed: {exc}") from exc


def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


async def run_primary(
    *,
    video_url: str,
    system_prompt: str,
    user_prompt: str,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    temperature: float = 0.0,
    max_tokens: int | None = None,
    runner: Runner | None = None,
) -> str:
    """Run the primary structured pass and return the raw text output."""
    run = runner or _default_runner
    arguments: dict[str, Any] = {
        "video_urls": [video_url],
        "prompt": user_prompt,
        "system_prompt": system_prompt,
        "model": gemini_model,
        "temperature": temperature,
        # Reasoning is mandatory for this endpoint; the JSON contract is recovered
        # from the response by the pipeline's tolerant JSON extractor.
        "reasoning": True,
    }
    if max_tokens is not None:
        arguments["max_tokens"] = max_tokens
    result = await run(ROUTER_VIDEO_MODEL, arguments)
    return _extract_output(result, ROUTER_VIDEO_MODEL)


async def run_enrichment(
    *,
    video_url: str,
    prompt: str,
    runner: Runner | None = None,
) -> str:
    """Run the enrichment/verification pass and return the raw text output.

    ``fal-ai/video-understanding`` expects a direct media URL. YouTube links are
    not supported here, so callers should skip this pass for YouTube-only inputs.
    """
    run = runner or _default_runner
    if _is_youtube(video_url):
        raise FalError(
            "video-understanding does not accept YouTube links; "
            "provide a direct media URL for the enrichment pass."
        )
    arguments: dict[str, Any] = {
        "video_url": video_url,
        "prompt": prompt,
        "detailed_analysis": True,
    }
    result = await run(VIDEO_UNDERSTANDING_MODEL, arguments)
    return _extract_output(result, VIDEO_UNDERSTANDING_MODEL)


def supports_enrichment(video_url: str) -> bool:
    """Whether the enrichment pass can run for the given URL."""
    return not _is_youtube(video_url)


def _extract_output(result: dict[str, Any], model_id: str) -> str:
    output = result.get("output") if isinstance(result, dict) else None
    if not isinstance(output, str) or not output.strip():
        raise FalError(f"{model_id!r} returned no usable 'output' field: {result!r}")
    return output
