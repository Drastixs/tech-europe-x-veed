from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LearnerObservationAssessment(BaseModel):
    """A visual progress hint that must be verified through the Onshape API."""

    model_config = ConfigDict(extra="forbid")

    state: Literal["progressing", "blocked", "target_relocated", "ready_to_validate"]
    evidence: list[str] = Field(min_length=1, max_length=4)
    suggested_next_action: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class LearnerObservationContext(BaseModel):
    """The bounded visual history passed to the learner-progress observer."""

    model_config = ConfigDict(extra="forbid")

    recent_screenshots: list[str] = Field(default_factory=list, exclude=True, max_length=3)
    recent_timestamps_ms: list[int] = Field(default_factory=list, exclude=True, max_length=3)
    historical_summaries: list[str] = Field(default_factory=list)
    latest_assessment: LearnerObservationAssessment | None = None

    def add_screenshot(self, screenshot_data_url: str, timestamp_ms: int) -> None:
        if len(self.recent_screenshots) == 3:
            self.recent_screenshots.pop(0)
            previous_timestamp = self.recent_timestamps_ms.pop(0)
            self.historical_summaries.append(
                f"Earlier learner observation at {previous_timestamp}ms was retained as history."
            )
        self.recent_screenshots.append(screenshot_data_url)
        self.recent_timestamps_ms.append(timestamp_ms)

    def observation_prompt(self, *, step_goal: str, expected_end_state: str) -> str:
        history = "\n".join(f"- {summary}" for summary in self.historical_summaries[-3:])
        return (
            "Assess the learner's visible progress in Onshape. Do not claim CAD correctness; "
            "Onshape API validation is the final authority. Return only visible evidence and a "
            "safe next action.\n"
            f"Step goal: {step_goal}\nExpected visible end state: {expected_end_state}\n"
            f"Earlier context:\n{history or '- No earlier observations.'}"
        )
