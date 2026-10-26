"""Pure chart metadata; rendering and numeric display conversion live outside."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Sequence

from finlabel.domain.analysis.schema import AnalysisResult


MAX_CHART_POINTS = 2000


@dataclass(frozen=True)
class ChartSeries:
    name: str
    x_values: Sequence[object]
    y_values: Sequence[object]


@dataclass(frozen=True)
class ChartSpecification:
    kind: str
    title: str
    xaxis_title: str
    yaxis_title: str
    series: Sequence[ChartSeries]


def chart_specification(result: AnalysisResult) -> ChartSpecification:
    if len(result.rows) > MAX_CHART_POINTS:
        raise ValueError(
            "Analysis produced more than {} chart points; add a filter or coarser time grain.".format(MAX_CHART_POINTS)
        )
    plan = result.plan
    dimensions = list(plan.dimensions)
    x_field: Optional[str]
    time_column = plan.time_axis.column if plan.time_axis else None
    if time_column:
        x_field = time_column
        series_fields = dimensions
    elif dimensions:
        x_field = dimensions[0]
        series_fields = dimensions[1:]
    else:
        x_field = None
        series_fields = []
    groups = defaultdict(list)
    for row in result.rows:
        series_key = tuple(row.get(name) for name in series_fields)
        x_value = row.get(x_field) if x_field else "Total"
        groups[series_key].append((x_value, row.get("value")))
    series = []
    for series_key, points in sorted(groups.items(), key=lambda item: tuple(str(value) for value in item[0])):
        points.sort(key=lambda point: str(point[0]))
        name = ", ".join("{}={}".format(field, value) for field, value in zip(series_fields, series_key)) or plan.metric.operation
        series.append(ChartSeries(name, tuple(point[0] for point in points), tuple(point[1] for point in points)))
    return ChartSpecification(
        kind=plan.chart,
        title="{}{}".format(plan.metric.operation, " por {}".format(", ".join(dimensions)) if dimensions else ""),
        xaxis_title=x_field or "Agregado",
        yaxis_title=plan.metric.column or "Registros",
        series=tuple(series),
    )
