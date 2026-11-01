"""Validated analysis plans and deterministic local calculations."""

from finlabel.adapters.outbound.sources.analysis import run_analysis
from finlabel.adapters.outbound.models.analysis_planner import (
    AnalysisClarificationError,
    HighlightRef,
    plan_analysis,
    plan_highlights,
    render_highlight,
)
from finlabel.domain.analysis.schema import (
    AnalysisPlan,
    AnalysisResult,
    FilterSpec,
    MetricSpec,
    TimeAxis,
    plan_from_dict,
    plan_to_dict,
    validate_analysis_plan,
)
from finlabel.adapters.outbound.persistence.analysis_runs import AnalysisRun, analyze_source, result_to_dict

__all__ = [
    "AnalysisPlan",
    "AnalysisResult",
    "AnalysisRun",
    "AnalysisClarificationError",
    "FilterSpec",
    "HighlightRef",
    "MetricSpec",
    "TimeAxis",
    "plan_from_dict",
    "plan_analysis",
    "plan_highlights",
    "plan_to_dict",
    "analyze_source",
    "result_to_dict",
    "render_highlight",
    "run_analysis",
    "validate_analysis_plan",
]

