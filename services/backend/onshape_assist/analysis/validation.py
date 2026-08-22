"""Strict acceptance validation for forensic video-analysis payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import AnalysisRequest

_POINTER_ACTIONS = {"move", "click", "double_click", "drag", "scroll", "selection"}
_ACTION_TYPES = _POINTER_ACTIONS | {"keypress", "type", "wait"}
_VIDEO_FIELDS = (
    "url",
    "application",
    "analyzed_start_ms",
    "analyzed_end_ms",
    "source_width",
    "source_height",
)
_ACTION_FIELDS = (
    "sequence",
    "timestamp_ms",
    "action_type",
    "position_source",
    "ui_region",
    "target_description",
    "visible_result",
    "confidence",
)


@dataclass(frozen=True, slots=True)
class ContractViolation:
    path: str
    message: str

    def model_dump(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


class AnalysisContractError(ValueError):
    """Raised when model output is syntactically valid but unusable as evidence."""

    def __init__(self, violations: list[ContractViolation]) -> None:
        self.violations = violations
        super().__init__("analysis output failed strict contract validation")

    def model_dump(self) -> dict[str, object]:
        return {
            "version": "analysis-error/v1",
            "code": "contract_validation_failed",
            "violations": [violation.model_dump() for violation in self.violations],
        }


def validate_payload(payload: dict[str, Any], request: AnalysisRequest) -> None:
    """Reject incomplete or silently repaired model output before it reaches Pydantic.

    The transport models retain permissive defaults for local manipulation and legacy
    fixtures. The external model boundary is intentionally fail-loud: each required
    value must be present in the raw response and meet the replay contract.
    """
    violations: list[ContractViolation] = []
    _validate_video(payload, request, violations)
    window = _analysis_window(payload, request)
    _validate_transcript(payload, window, violations)
    _validate_steps(payload, window, violations)
    if violations:
        raise AnalysisContractError(violations)


def _analysis_window(payload: dict[str, Any], request: AnalysisRequest) -> tuple[int, int] | None:
    if request.analysis_scope is not None:
        return request.analysis_scope.start_ms, request.analysis_scope.end_ms
    video = payload.get("video")
    if not isinstance(video, dict):
        return None
    start, end = video.get("analyzed_start_ms"), video.get("analyzed_end_ms")
    return (start, end) if _is_int(start) and _is_int(end) and start < end else None


def _validate_video(
    payload: dict[str, Any], request: AnalysisRequest, violations: list[ContractViolation]
) -> None:
    video = payload.get("video")
    if not isinstance(video, dict):
        violations.append(ContractViolation("video", "must be an object"))
        return
    for field in _VIDEO_FIELDS:
        if field not in video:
            violations.append(ContractViolation(f"video.{field}", "is required"))
    if not isinstance(video.get("url"), str) or not video.get("url", "").strip():
        violations.append(ContractViolation("video.url", "must be a non-empty string"))
    if not isinstance(video.get("application"), str) or not video.get("application", "").strip():
        violations.append(ContractViolation("video.application", "must be a non-empty string"))
    if video.get("url") != request.video_url:
        violations.append(ContractViolation("video.url", "must match the requested video_url"))
    if video.get("application") != request.application:
        violations.append(
            ContractViolation("video.application", "must match the requested application")
        )
    start, end = video.get("analyzed_start_ms"), video.get("analyzed_end_ms")
    if not _is_int(start) or not _is_int(end) or start < 0 or end <= start:
        violations.append(
            ContractViolation("video", "must contain a non-empty analyzed time range")
        )
    if request.analysis_scope and (
        start != request.analysis_scope.start_ms or end != request.analysis_scope.end_ms
    ):
        violations.append(ContractViolation("video", "must match the requested analysis_scope"))
    for field in ("source_width", "source_height"):
        if not _is_int(video.get(field)) or video[field] <= 0:
            violations.append(ContractViolation(f"video.{field}", "must be a positive integer"))


def _validate_transcript(
    payload: dict[str, Any], window: tuple[int, int] | None, violations: list[ContractViolation]
) -> None:
    transcript = payload.get("full_transcript")
    if not isinstance(transcript, dict):
        violations.append(ContractViolation("full_transcript", "must be an object"))
        return
    if (
        not isinstance(transcript.get("verbatim_text"), str)
        or not transcript.get("verbatim_text", "").strip()
    ):
        violations.append(ContractViolation("full_transcript.verbatim_text", "must be non-empty"))
    segments = transcript.get("segments")
    if not isinstance(segments, list) or not segments:
        violations.append(
            ContractViolation("full_transcript.segments", "must contain timestamped segments")
        )
        return
    previous_end: int | None = None
    for index, segment in enumerate(segments):
        path = f"full_transcript.segments[{index}]"
        if not isinstance(segment, dict):
            violations.append(ContractViolation(path, "must be an object"))
            continue
        start, end = segment.get("start_ms"), segment.get("end_ms")
        if not _is_int(start) or not _is_int(end) or end <= start:
            violations.append(ContractViolation(path, "must have an increasing time range"))
            continue
        if previous_end is not None and start != previous_end:
            violations.append(ContractViolation(path, "must continuously follow the prior segment"))
        previous_end = end
        for field in ("speaker", "text"):
            if not isinstance(segment.get(field), str) or not segment.get(field, "").strip():
                violations.append(ContractViolation(f"{path}.{field}", "must be non-empty"))
        if not _is_confidence(segment.get("confidence")):
            violations.append(ContractViolation(f"{path}.confidence", "must be between 0 and 1"))
    if (
        window
        and isinstance(segments[0], dict)
        and isinstance(segments[-1], dict)
        and (segments[0].get("start_ms") != window[0] or segments[-1].get("end_ms") != window[1])
    ):
        violations.append(
            ContractViolation("full_transcript.segments", "must cover the complete analyzed range")
        )


def _validate_steps(
    payload: dict[str, Any], window: tuple[int, int] | None, violations: list[ContractViolation]
) -> None:
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        violations.append(ContractViolation("steps", "must contain at least one step"))
        return
    previous_timestamp = -1
    seen_step_ids: set[str] = set()
    for step_index, step in enumerate(steps):
        path = f"steps[{step_index}]"
        if not isinstance(step, dict):
            violations.append(ContractViolation(path, "must be an object"))
            continue
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id.strip() or step_id in seen_step_ids:
            violations.append(ContractViolation(f"{path}.step_id", "must be non-empty and unique"))
        else:
            seen_step_ids.add(step_id)
        start, end = step.get("start_ms"), step.get("end_ms")
        if not _is_int(start) or not _is_int(end) or end < start:
            violations.append(ContractViolation(path, "must have an ordered time range"))
        elif window and (start < window[0] or end > window[1]):
            violations.append(ContractViolation(path, "must be within the analyzed range"))
        for field in ("user_text", "goal", "narration", "expected_end_state"):
            if not isinstance(step.get(field), str) or not step.get(field, "").strip():
                violations.append(ContractViolation(f"{path}.{field}", "must be non-empty"))
        actions = step.get("actions")
        if not isinstance(actions, list) or not actions:
            violations.append(ContractViolation(f"{path}.actions", "must contain atomic actions"))
            continue
        for action_index, action in enumerate(actions):
            action_path = f"{path}.actions[{action_index}]"
            if not isinstance(action, dict):
                violations.append(ContractViolation(action_path, "must be an object"))
                continue
            for field in _ACTION_FIELDS:
                if field not in action:
                    violations.append(ContractViolation(f"{action_path}.{field}", "is required"))
            timestamp = action.get("timestamp_ms")
            if not _is_int(timestamp) or timestamp < previous_timestamp:
                violations.append(
                    ContractViolation(f"{action_path}.timestamp_ms", "must be chronological")
                )
            else:
                previous_timestamp = timestamp
            if (
                _is_int(start)
                and _is_int(end)
                and _is_int(timestamp)
                and not start <= timestamp <= end
            ):
                violations.append(
                    ContractViolation(
                        f"{action_path}.timestamp_ms", "must be within its step range"
                    )
                )
            if not _is_confidence(action.get("confidence")):
                violations.append(
                    ContractViolation(f"{action_path}.confidence", "must be between 0 and 1")
                )
            if action.get("action_type") not in _ACTION_TYPES:
                violations.append(
                    ContractViolation(
                        f"{action_path}.action_type", "must be a supported atomic action"
                    )
                )
            if action.get("position_source") not in {"observed", "inferred"}:
                violations.append(
                    ContractViolation(
                        f"{action_path}.position_source", "must be observed or inferred"
                    )
                )
            for field in ("ui_region", "target_description", "visible_result"):
                if not isinstance(action.get(field), str) or not action.get(field, "").strip():
                    violations.append(
                        ContractViolation(f"{action_path}.{field}", "must be non-empty")
                    )
            if action.get("action_type") in _POINTER_ACTIONS:
                _validate_cursor(action, action_path, violations)


def _validate_cursor(
    action: dict[str, Any], path: str, violations: list[ContractViolation]
) -> None:
    for field in ("cursor_start", "cursor_end"):
        point = action.get(field)
        if not isinstance(point, dict):
            violations.append(
                ContractViolation(f"{path}.{field}", "is required for pointer actions")
            )
            continue
        for axis in ("x", "y"):
            value = point.get(axis)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0 <= value <= 1000
            ):
                violations.append(
                    ContractViolation(f"{path}.{field}.{axis}", "must be between 0 and 1000")
                )


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_confidence(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1
