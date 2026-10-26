"""Offline Plotly chart rendering for deterministic analysis results."""

from decimal import Decimal

from finlabel.domain.analysis.charts import MAX_CHART_POINTS, chart_specification


def render_chart(result) -> str:
    specification = chart_specification(result)
    try:
        import plotly.graph_objects as go
        from plotly.io import to_html
    except ImportError as exc:
        raise RuntimeError("Install finlabel-local[web] to render offline charts.") from exc

    figure = go.Figure()
    for series in specification.series:
        name = series.name
        x_values = list(series.x_values)
        y_values = [float(value) if value is not None else None for value in series.y_values]
        exact_values = [format(value, "f") if isinstance(value, Decimal) else str(value) for value in series.y_values]
        if specification.kind == "line":
            figure.add_trace(go.Scatter(
                x=x_values, y=y_values, customdata=exact_values, mode="lines+markers", name=name,
                hovertemplate="%{x}<br>%{y}<br>Valor exato: %{customdata}<extra>%{fullData.name}</extra>",
            ))
        else:
            figure.add_trace(go.Bar(
                x=x_values, y=y_values, customdata=exact_values, name=name,
                hovertemplate="%{x}<br>%{y}<br>Valor exato: %{customdata}<extra>%{fullData.name}</extra>",
            ))
    if specification.kind == "stacked_bar":
        figure.update_layout(barmode="stack")
    elif specification.kind == "bar":
        figure.update_layout(barmode="group")
    figure.update_layout(
        title=specification.title,
        xaxis_title=specification.xaxis_title,
        yaxis_title=specification.yaxis_title,
        template="plotly_white",
    )
    return to_html(figure, full_html=True, include_plotlyjs=True, config={"displaylogo": False})
