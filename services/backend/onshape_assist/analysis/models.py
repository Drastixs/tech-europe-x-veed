"""Pydantic models for the video analysis input and output contract.

These mirror ``prds/video-analytis-and-narration.md``. Fields are intentionally
permissive (sensible defaults, optional where a model may omit them) so that a
slightly imperfect model response still validates and round-trips, while the
overall shape stays faithful to the PRD contract.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ActionType = Literal[
    "move",
    "click",
    "double_click",
    "drag",
    "keypress",
    "type",
    "scroll",
    "wait",
    "selection",
]
MouseButton = Literal["left", "right", "middle"]
PositionSource = Literal["observed", "inferred"]


# --- Input ---------------------------------------------------------------


class AnalysisScope(BaseModel):
    """Optional sub-range of the video to analyze, in milliseconds."""

    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_time_range(self) -> AnalysisScope:
        if self.end_ms <= self.start_ms:
            raise ValueError("analysis_scope.end_ms must be later than analysis_scope.start_ms")
        return self


class AnalysisRequest(BaseModel):
    """Input contract for a video analysis request."""

    video_url: str
    application: str = "Onshape"
    analysis_scope: AnalysisScope | None = None
    coordinate_system: Literal["normalized_0_to_1000"] = "normalized_0_to_1000"
    output_language: str = "en"


# --- Output --------------------------------------------------------------


class VideoMeta(BaseModel):
    url: str = ""
    application: str = "Onshape"
    analyzed_start_ms: int = 0
    analyzed_end_ms: int = 0
    source_width: int = 0
    source_height: int = 0

    @field_validator("url", "application", mode="before")
    @classmethod
    def _required_str(cls, value: Any) -> Any:
        return "" if value is None else value


class TranscriptSegment(BaseModel):
    start_ms: int = 0
    end_ms: int = 0
    speaker: str = "instructor"
    text: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("speaker", "text", mode="before")
    @classmethod
    def _required_str(cls, value: Any) -> Any:
        return "" if value is None else value


class FullTranscript(BaseModel):
    verbatim_text: str = ""
    segments: list[TranscriptSegment] = Field(default_factory=list)

    @field_validator("verbatim_text", mode="before")
    @classmethod
    def _required_str(cls, value: Any) -> Any:
        return "" if value is None else value


class CursorPoint(BaseModel):
    x: float = 0
    y: float = 0


class Action(BaseModel):
    sequence: int = 0
    timestamp_ms: int = 0
    action_type: ActionType = "move"
    mouse_button: MouseButton | None = None
    keys: list[str] = Field(default_factory=list)
    typed_text: str | None = None
    cursor_start: CursorPoint | None = None
    cursor_end: CursorPoint | None = None
    position_source: PositionSource = "inferred"
    ui_region: str = ""
    target_label: str | None = None
    target_description: str = ""
    icon_description: str | None = None
    selected_object: str | None = None
    visible_result: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator(
        "mouse_button",
        "typed_text",
        "target_label",
        "icon_description",
        "selected_object",
        mode="before",
    )
    @classmethod
    def _nullish_to_none(cls, value: Any) -> Any:
        """Models sometimes emit the literal string ``"null"`` instead of JSON null."""
        if isinstance(value, str) and value.strip().lower() in {"null", "none", ""}:
            return None
        return value

    @field_validator("action_type", mode="before")
    @classmethod
    def _normalize_action_type(cls, value: Any) -> Any:
        if isinstance(value, str):
            candidate = value.strip().lower().replace("-", "_").replace(" ", "_")
            allowed = {
                "move",
                "click",
                "double_click",
                "drag",
                "keypress",
                "type",
                "scroll",
                "wait",
                "selection",
            }
            return candidate if candidate in allowed else "move"
        return value

    @field_validator("position_source", mode="before")
    @classmethod
    def _normalize_position_source(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().lower() in {"observed", "inferred"}:
            return value.strip().lower()
        return "inferred"

    @field_validator("ui_region", "target_description", "visible_result", mode="before")
    @classmethod
    def _required_str(cls, value: Any) -> Any:
        return "" if value is None else value


class Step(BaseModel):
    step_id: str = ""
    start_ms: int = 0
    end_ms: int = 0
    user_text: str = ""
    goal: str = ""
    actions: list[Action] = Field(default_factory=list)
    narration: str = ""
    expected_end_state: str = ""
    uncertainties: list[str] = Field(default_factory=list)

    @field_validator(
        "step_id", "user_text", "goal", "narration", "expected_end_state", mode="before"
    )
    @classmethod
    def _required_str(cls, value: Any) -> Any:
        return "" if value is None else value

    @field_validator("uncertainties", mode="before")
    @classmethod
    def _coerce_uncertainties(cls, value: Any) -> list[str]:
        """Normalize uncertainties to strings.

        The model sometimes returns objects (e.g. ``{"type": ..., "comment": ...}``)
        instead of plain strings; flatten those to readable text rather than failing
        validation.
        """
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                comment = item.get("comment") or item.get("description") or item.get("note")
                kind = item.get("type") or item.get("kind")
                if comment and kind:
                    result.append(f"[{kind}] {comment}")
                elif comment:
                    result.append(str(comment))
                else:
                    result.append(json.dumps(item, ensure_ascii=False))
            else:
                result.append(str(item))
        return result


class AnalysisResult(BaseModel):
    """Output contract. ``scene_review`` is an additive enrichment field produced
    by the second fal model; it does not alter the core PRD contract."""

    video: VideoMeta
    full_transcript: FullTranscript = Field(default_factory=FullTranscript)
    steps: list[Step] = Field(default_factory=list)
    scene_review: str | None = None
