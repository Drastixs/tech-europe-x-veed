"""Video analysis and tutorial extraction.

Converts an Onshape tutorial video into a timestamped, machine-readable record of
speech and visible interaction using fal partner models. See
``prds/video-analytis-and-narration.md`` for the specification.
"""

from onshape_assist.analysis.models import (
    AnalysisRequest,
    AnalysisResult,
    AnalysisScope,
)
from onshape_assist.analysis.pipeline import analyze_video, analyze_video_async

__all__ = [
    "AnalysisRequest",
    "AnalysisResult",
    "AnalysisScope",
    "analyze_video",
    "analyze_video_async",
]
