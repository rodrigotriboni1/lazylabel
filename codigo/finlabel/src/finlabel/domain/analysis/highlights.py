"""Result-grounded highlight references and deterministic rendering."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping, Sequence
from finlabel.domain.analysis.schema import AnalysisResult

@dataclass(frozen=True)
class HighlightRef:
    result_key: Sequence[object]
    observation: str


def render_highlight(result: AnalysisResult, reference: HighlightRef) -> str:
    row, comparison = _resolve_highlight(result, reference)
    metric_name = result.plan.metric.column or "linhas"
    time_column = result.plan.time_axis.column if result.plan.time_axis else None
    if reference.observation in {"overall_increase", "overall_decrease"}:
        start, end = comparison
        direction = "cresceu" if reference.observation == "overall_increase" else "diminuiu"
        context_fields = [name for name in result.formula_metadata.get("group_fields", []) if name != time_column]
        context = _context(dict(zip(context_fields, reference.result_key)))
        return "O valor calculado de {} {} de {} para {} {}.".format(
            metric_name, direction, _format_value(start["value"]), _format_value(end["value"]), context
        )
    labels = {
        "highest": "Maior valor calculado",
        "lowest": "Menor valor calculado",
        "largest_share": "Maior participação calculada",
        "smallest_share": "Menor participação calculada",
        "notable": "Valor calculado",
    }
    context_fields = list(result.formula_metadata.get("group_fields", []))
    context = _context({name: row.get(name) for name in context_fields})
    return "{} de {}: {} {}.".format(labels[reference.observation], metric_name, _format_value(row["value"]), context)


def _resolve_highlight(result: AnalysisResult, reference: HighlightRef):
    fields = list(result.formula_metadata.get("group_fields", []))
    time_column = result.plan.time_axis.column if result.plan.time_axis else None
    point_observations = {"highest", "lowest", "largest_share", "smallest_share", "notable"}
    if reference.observation in point_observations:
        if len(reference.result_key) != len(fields):
            raise ValueError("Highlight result key has the wrong number of fields.")
        matches = [
            row for row in result.rows
            if tuple(_json_value(row.get(name)) for name in fields) == tuple(reference.result_key)
        ]
        if len(matches) != 1:
            raise ValueError("Highlight result key does not identify exactly one calculated row.")
        row = matches[0]
        if row.get("value") is None:
            raise ValueError("Highlight cannot reference a missing calculated value.")
        if reference.observation in {"largest_share", "smallest_share"} and result.plan.metric.operation != "share_of_total":
            raise ValueError("Share highlights require a share_of_total analysis.")
        values = [item["value"] for item in result.rows if item.get("value") is not None]
        expected = max(values) if reference.observation in {"highest", "largest_share"} else min(values)
        if reference.observation != "notable" and row["value"] != expected:
            raise ValueError("Highlight observation does not match the calculated result ordering.")
        return row, None
    if reference.observation not in {"overall_increase", "overall_decrease"} or time_column is None:
        raise ValueError("Trend highlight requires a time axis and a supported observation kind.")
    dimensions = [name for name in fields if name != time_column]
    if len(reference.result_key) != len(dimensions):
        raise ValueError("Trend highlight key must identify dimension values only.")
    matching = [
        row for row in result.rows
        if tuple(_json_value(row.get(name)) for name in dimensions) == tuple(reference.result_key)
        and row.get("value") is not None
    ]
    matching.sort(key=lambda row: str(row.get(time_column)))
    if len(matching) < 2:
        raise ValueError("Trend highlight needs at least two calculated time points.")
    start, end = matching[0], matching[-1]
    increased = end["value"] > start["value"]
    expected = increased if reference.observation == "overall_increase" else not increased
    if not expected or end["value"] == start["value"]:
        raise ValueError("Trend highlight direction does not match calculated endpoints.")
    return None, (start, end)


def _context(values: Mapping[str, object]) -> str:
    if not values:
        return "no recorte configurado"
    return "para {}".format(", ".join("{}={}".format(name, _format_value(value)) for name, value in values.items()))


def _format_value(value):
    return format(value, "f") if isinstance(value, Decimal) else str(value)


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    return value
