"""Validated analysis plans and deterministic local calculations."""

from finlabel.analysis.engine import run_analysis
from finlabel.analysis.planner import (
    AnalysisClarificationError,
    HighlightRef,
    plan_analysis,
    plan_highlights,
    render_highlight,
)
from finlabel.analysis.schema import (
    AnalysisPlan,
    AnalysisResult,
    FilterSpec,
    MetricSpec,
    TimeAxis,
    plan_from_dict,
    plan_to_dict,
    validate_analysis_plan,
)

__all__ = [
    "AnalysisPlan",
    "AnalysisResult",
    "AnalysisClarificationError",
    "FilterSpec",
    "HighlightRef",
    "MetricSpec",
    "TimeAxis",
    "plan_from_dict",
    "plan_analysis",
    "plan_highlights",
    "plan_to_dict",
    "render_highlight",
    "run_analysis",
    "validate_analysis_plan",
]

