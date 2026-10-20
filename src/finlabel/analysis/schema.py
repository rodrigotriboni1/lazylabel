"""Versioned, allowlisted analytics plan types and validation."""

from dataclasses import asdict, dataclass, field
from typing import Mapping, Optional, Sequence

from finlabel.profile import ColumnProfile


METRICS = {"count_rows", "sum", "average", "distinct_count", "share_of_total"}
FILTERS = {"eq", "neq", "in", "gt", "gte", "lt", "lte", "between"}
CHARTS = {"line", "bar", "stacked_bar"}
TIME_GRAINS = {"day", "week", "month", "quarter", "year"}


@dataclass(frozen=True)
class MetricSpec:
    operation: str
    column: Optional[str] = None
    denominator_scope: Optional[Sequence[str]] = None


@dataclass(frozen=True)
class TimeAxis:
    column: str
    grain: str


@dataclass(frozen=True)
class FilterSpec:
    column: str
    operation: str
    value: object


@dataclass(frozen=True)
class AnalysisPlan:
    version: int
    metric: MetricSpec
    dimensions: Sequence[str] = field(default_factory=tuple)
    time_axis: Optional[TimeAxis] = None
    filters: Sequence[FilterSpec] = field(default_factory=tuple)
    chart: str = "bar"


@dataclass(frozen=True)
class AnalysisResult:
    plan: AnalysisPlan
    rows: Sequence[Mapping[str, object]]
    valid_row_count: int
    invalid_value_counts: Mapping[str, int]
    selected_fields: Sequence[str]
    formula_metadata: Mapping[str, object]


def validate_analysis_plan(plan: AnalysisPlan, schema: Sequence[ColumnProfile]) -> AnalysisPlan:
    if plan.version != 1:
        raise ValueError("Unsupported analysis plan version: {}".format(plan.version))
    if plan.metric.operation not in METRICS:
        raise ValueError("Unsupported metric operation: {}".format(plan.metric.operation))
    if plan.chart not in CHARTS:
        raise ValueError("Unsupported chart kind: {}".format(plan.chart))
    names = {column.name for column in schema}
    referenced = list(plan.dimensions)
    if plan.metric.column:
        referenced.append(plan.metric.column)
    if plan.time_axis:
        referenced.append(plan.time_axis.column)
        if plan.time_axis.grain not in TIME_GRAINS:
            raise ValueError("Unsupported time grain: {}".format(plan.time_axis.grain))
    for filter_spec in plan.filters:
        referenced.append(filter_spec.column)
        if filter_spec.operation not in FILTERS:
            raise ValueError("Unsupported filter operation: {}".format(filter_spec.operation))
        if filter_spec.operation == "between" and (not isinstance(filter_spec.value, (list, tuple)) or len(filter_spec.value) != 2):
            raise ValueError("The between filter requires exactly two values.")
        if filter_spec.operation == "in" and not isinstance(filter_spec.value, (list, tuple, set)):
            raise ValueError("The in filter requires a list of values.")
    missing = sorted(set(referenced) - names)
    if missing:
        raise ValueError("Unknown analysis column(s): {}".format(", ".join(missing)))
    if len(set(plan.dimensions)) != len(plan.dimensions):
        raise ValueError("Analysis dimensions must be unique.")
    if plan.metric.operation == "count_rows":
        if plan.metric.column is not None:
            raise ValueError("count_rows does not accept a column.")
    elif not plan.metric.column:
        raise ValueError("Metric {} requires a column.".format(plan.metric.operation))
    if plan.metric.operation == "share_of_total":
        if plan.metric.denominator_scope is None:
            raise ValueError("share_of_total requires an explicit denominator scope (use [] for the full group).")
        if not set(plan.metric.denominator_scope).issubset(set(plan.dimensions)):
            raise ValueError("Share denominator scope must be a subset of the plan dimensions.")
        if not set(plan.dimensions) - set(plan.metric.denominator_scope):
            raise ValueError("Share denominator scope must exclude at least one grouping dimension.")
    elif plan.metric.denominator_scope not in (None, (), []):
        raise ValueError("A denominator scope is only valid for share_of_total.")
    return plan


def plan_to_dict(plan: AnalysisPlan) -> dict:
    return asdict(plan)


def plan_from_dict(raw: Mapping[str, object]) -> AnalysisPlan:
    try:
        metric_raw = raw["metric"]
        time_raw = raw.get("time_axis")
        filters_raw = raw.get("filters", [])
        if not isinstance(metric_raw, dict) or not isinstance(filters_raw, list):
            raise TypeError("metric must be an object and filters must be a list")
        metric = MetricSpec(
            operation=metric_raw["operation"],
            column=metric_raw.get("column"),
            denominator_scope=metric_raw.get("denominator_scope"),
        )
        time_axis = TimeAxis(**time_raw) if time_raw is not None else None
        filters = tuple(FilterSpec(**item) for item in filters_raw)
        plan = AnalysisPlan(
            version=raw["version"], metric=metric,
            dimensions=tuple(raw.get("dimensions", [])), time_axis=time_axis,
            filters=filters, chart=raw.get("chart", "bar"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Malformed analysis plan: {}".format(exc)) from exc
    if not isinstance(plan.version, int) or not isinstance(plan.chart, str):
        raise ValueError("Malformed analysis plan version or chart.")
    return plan

