"""Pure analysis plans, streaming calculations, and chart specifications."""

from finlabel.domain.analysis.charts import ChartSeries, ChartSpecification, chart_specification
from finlabel.domain.analysis.engine import required_fields, run_analysis
from finlabel.domain.analysis.schema import (
    AnalysisPlan, AnalysisResult, FilterSpec, MetricSpec, TimeAxis,
    plan_from_dict, plan_to_dict, validate_analysis_plan,
)

__all__ = [
    "AnalysisPlan", "AnalysisResult", "FilterSpec", "MetricSpec", "TimeAxis",
    "ChartSeries", "ChartSpecification", "chart_specification",
    "plan_from_dict", "plan_to_dict", "validate_analysis_plan", "required_fields", "run_analysis",
]
