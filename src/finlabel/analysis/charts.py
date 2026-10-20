"""Offline Plotly chart rendering for deterministic analysis results."""

from collections import defaultdict
from decimal import Decimal


MAX_CHART_POINTS = 2000


def render_chart(result) -> str:
    if len(result.rows) > MAX_CHART_POINTS:
        raise ValueError(
            "Analysis produced more than {} chart points; add a filter or coarser time grain.".format(MAX_CHART_POINTS)
        )
    try:
        import plotly.graph_objects as go
        from plotly.io import to_html
    except ImportError as exc:
        raise RuntimeError("Install finlabel-local[web] to render offline charts.") from exc

    plan = result.plan
    time_column = plan.time_axis.column if plan.time_axis else None
    dimensions = list(plan.dimensions)
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

    figure = go.Figure()
    for series_key, points in sorted(groups.items(), key=lambda item: tuple(str(value) for value in item[0])):
        points.sort(key=lambda point: str(point[0]))
        name = ", ".join("{}={}".format(field, value) for field, value in zip(series_fields, series_key)) or plan.metric.operation
        x_values = [point[0] for point in points]
        y_values = [float(point[1]) if point[1] is not None else None for point in points]
        exact_values = [format(point[1], "f") if isinstance(point[1], Decimal) else str(point[1]) for point in points]
        if plan.chart == "line":
            figure.add_trace(go.Scatter(
                x=x_values, y=y_values, customdata=exact_values, mode="lines+markers", name=name,
                hovertemplate="%{x}<br>%{y}<br>Valor exato: %{customdata}<extra>%{fullData.name}</extra>",
            ))
        else:
            figure.add_trace(go.Bar(
                x=x_values, y=y_values, customdata=exact_values, name=name,
                hovertemplate="%{x}<br>%{y}<br>Valor exato: %{customdata}<extra>%{fullData.name}</extra>",
            ))
    if plan.chart == "stacked_bar":
        figure.update_layout(barmode="stack")
    elif plan.chart == "bar":
        figure.update_layout(barmode="group")
    figure.update_layout(
        title="{}{}".format(plan.metric.operation, " por {}".format(", ".join(dimensions)) if dimensions else ""),
        xaxis_title=x_field or "Agregado",
        yaxis_title=plan.metric.column or "Registros",
        template="plotly_white",
    )
    return to_html(figure, full_html=True, include_plotlyjs=True, config={"displaylogo": False})
