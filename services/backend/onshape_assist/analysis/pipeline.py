"""Orchestrates the two-model video analysis pipeline.

Given an :class:`AnalysisRequest`, it runs the primary structured pass and the
enrichment pass (concurrently when possible), parses the primary JSON into the
PRD output contract, and attaches the enrichment result as ``scene_review``.
"""

from __future__ import annotations

import asyncio
import json
import re
import tempfile

from pydantic import ValidationError

from onshape_assist.analysis import fal, prompts
from onshape_assist.analysis.fal import FalError, Runner
from onshape_assist.analysis.models import AnalysisRequest, AnalysisResult

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class AnalysisError(RuntimeError):
    """Raised when the pipeline cannot produce a valid result."""


def extract_json(text: str) -> dict:
    """Extract a JSON object from a model response.

    Tolerates markdown code fences and leading/trailing prose by falling back to
    the first balanced ``{...}`` block.
    """
    stripped = _FENCE_RE.sub("", text.strip())
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    if start == -1:
        raise AnalysisError("no JSON object found in model output")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError as exc:
                    raise AnalysisError(f"failed to parse JSON block: {exc}") from exc
    raise AnalysisError("unbalanced JSON object in model output")


def _dump_debug(payload: dict) -> str:
    """Persist a raw payload that failed validation, so it can be inspected without
    paying for another API call. Returns the file path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="analysis-raw-", delete=False, encoding="utf-8"
    ) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        return handle.name


def _fill_video_meta(result: AnalysisResult, request: AnalysisRequest) -> None:
    """Backfill video metadata from the request when the model omits it."""
    video = result.video
    if not video.url:
        video.url = request.video_url
    if not video.application:
        video.application = request.application
    if request.analysis_scope is not None:
        if not video.analyzed_start_ms:
            video.analyzed_start_ms = request.analysis_scope.start_ms
        if not video.analyzed_end_ms:
            video.analyzed_end_ms = request.analysis_scope.end_ms


def enforce_constraints(result: AnalysisResult, request: AnalysisRequest) -> AnalysisResult:
    """Deterministically enforce the contract in code rather than trusting the model.

    Inspired by the MarkupLadder guardrail pattern: the prompt *requests* good
    behaviour, this *guarantees* it. Specifically:

    - drop actions whose timestamp falls outside the requested analysis window,
    - drop transcript segments that fall entirely outside the window,
    - sort actions chronologically within each step and re-number ``sequence``,
    - sort steps chronologically, and drop steps that had actions but lost them
      all to the window filter (keeps intentionally action-free narration steps),
    - clamp step start/end to the window.

    Mutates and returns ``result``.
    """
    scope = request.analysis_scope
    lo = scope.start_ms if scope else None
    hi = scope.end_ms if scope else None

    def in_window(ts: int) -> bool:
        if lo is None or hi is None:
            return True
        return lo <= ts <= hi

    kept_steps = []
    for step in result.steps:
        had_actions = len(step.actions) > 0
        actions = [a for a in step.actions if in_window(a.timestamp_ms)]
        actions.sort(key=lambda a: a.timestamp_ms)
        for i, action in enumerate(actions, start=1):
            action.sequence = i
        step.actions = actions
        if lo is not None and hi is not None:
            step.start_ms = min(max(step.start_ms, lo), hi) if step.start_ms else lo
            step.end_ms = min(max(step.end_ms, lo), hi) if step.end_ms else hi
        # Drop steps that used to have actions but lost them all to the filter;
        # keep steps that were intentionally action-free (pure narration).
        if had_actions and not actions:
            continue
        kept_steps.append(step)

    kept_steps.sort(key=lambda s: s.start_ms)
    result.steps = kept_steps

    # Clip the transcript segments to the window (drop fully-outside ones).
    if lo is not None and hi is not None:
        result.full_transcript.segments = [
            seg
            for seg in result.full_transcript.segments
            if seg.end_ms >= lo and seg.start_ms <= hi
        ]

    return result


async def analyze_video_async(
    request: AnalysisRequest,
    *,
    gemini_model: str = fal.DEFAULT_GEMINI_MODEL,
    with_enrichment: bool = True,
    runner: Runner | None = None,
) -> AnalysisResult:
    """Run the full analysis pipeline for a request."""
    system_prompt = prompts.system_prompt(request)
    primary_prompt = prompts.primary_user_prompt(request)

    primary_task = asyncio.create_task(
        fal.run_primary(
            video_url=request.video_url,
            system_prompt=system_prompt,
            user_prompt=primary_prompt,
            gemini_model=gemini_model,
            runner=runner,
        )
    )

    enrichment_task = None
    if with_enrichment and fal.supports_enrichment(request.video_url):
        enrichment_task = asyncio.create_task(
            fal.run_enrichment(
                video_url=request.video_url,
                prompt=prompts.enrichment_prompt(request),
                runner=runner,
            )
        )

    try:
        primary_output = await primary_task
    except FalError as exc:
        if enrichment_task is not None:
            enrichment_task.cancel()
        raise AnalysisError(f"primary analysis failed: {exc}") from exc

    payload = extract_json(primary_output)
    try:
        result = AnalysisResult.model_validate(payload)
    except ValidationError as exc:
        debug_path = _dump_debug(payload)
        raise AnalysisError(
            f"model output did not match the contract (raw payload saved to {debug_path} "
            f"for offline debugging): {exc}"
        ) from exc

    _fill_video_meta(result, request)
    enforce_constraints(result, request)

    if enrichment_task is not None:
        try:
            result.scene_review = await enrichment_task
        except FalError as exc:
            # Enrichment is best-effort: degrade gracefully and note it.
            note = f"Enrichment (scene review) pass unavailable: {exc}"
            if result.steps:
                result.steps[0].uncertainties.append(note)

    return result


def analyze_video(
    request: AnalysisRequest,
    *,
    gemini_model: str = fal.DEFAULT_GEMINI_MODEL,
    with_enrichment: bool = True,
    runner: Runner | None = None,
) -> AnalysisResult:
    """Synchronous wrapper around :func:`analyze_video_async`."""
    return asyncio.run(
        analyze_video_async(
            request,
            gemini_model=gemini_model,
            with_enrichment=with_enrichment,
            runner=runner,
        )
    )
