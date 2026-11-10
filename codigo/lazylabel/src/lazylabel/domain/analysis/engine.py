"""Deterministic grouped calculations over streaming local sources."""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, Mapping, Optional, Sequence

from lazylabel.domain.analysis.schema import AnalysisPlan, AnalysisResult, validate_analysis_plan

from lazylabel.domain.projects import ColumnProfile


NUMERIC_TYPES = {"decimal", "number", "numeric", "float", "integer", "int"}
DATE_TYPES = {"date", "datetime", "timestamp", "date-time"}


def _type_for(name, explicit, inferred):
    kind = explicit.get(name)
    if kind is None:
        if inferred.get(name) in {"integer", "number"}:
            raise ValueError("Numeric column {!r} needs an explicit type mapping.".format(name))
        return "string"
    normalized = str(kind).lower()
    if normalized not in NUMERIC_TYPES | DATE_TYPES | {"string", "text", "boolean", "bool"}:
        raise ValueError("Unsupported explicit type mapping for {!r}: {}".format(name, kind))
    return normalized


def _convert(value, kind):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if kind in NUMERIC_TYPES:
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("not a valid decimal") from exc
        if not result.is_finite():
            raise ValueError("not a finite decimal")
        return result
    if kind in DATE_TYPES:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return value
        text = str(value).strip()
        if kind == "date":
            return date.fromisoformat(text)
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return date.fromisoformat(text)
    if kind in {"boolean", "bool"}:
        normalized = str(value).strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        raise ValueError("not a recognized boolean")
    return str(value)


def _date_bucket(value, grain):
    if isinstance(value, datetime):
        current = value.date()
    else:
        current = value
    if grain == "day":
        return current.isoformat()
    if grain == "week":
        iso = current.isocalendar()
        return "{:04d}-W{:02d}".format(iso.year, iso.week)
    if grain == "month":
        return "{:04d}-{:02d}".format(current.year, current.month)
    if grain == "quarter":
        return "{:04d}-Q{}".format(current.year, (current.month - 1) // 3 + 1)
    return str(current.year)


def _sort_value(value):
    if value is None:
        return (0, "")
    if isinstance(value, bool):
        return (2, value)
    if isinstance(value, (Decimal, int, float)):
        return (1, Decimal(str(value)))
    return (3, str(value))


def _matches(value, operation, target):
    if operation == "eq":
        return value == target
    if operation == "neq":
        return value != target
    if operation == "in":
        return value in target
    if value is None or target is None:
        return False
    if operation == "gt":
        return value > target
    if operation == "gte":
        return value >= target
    if operation == "lt":
        return value < target
    if operation == "lte":
        return value <= target
    if operation == "between":
        return target[0] <= value <= target[1]
    return False


def required_fields(plan: AnalysisPlan) -> list[str]:
    """Return the stable column projection needed to evaluate a plan."""
    return list(dict.fromkeys(
        list(plan.dimensions)
        + ([plan.time_axis.column] if plan.time_axis else [])
        + ([plan.metric.column] if plan.metric.column else [])
        + [item.column for item in plan.filters]
    ))


def run_analysis(
    plan: AnalysisPlan,
    profiles: Sequence[ColumnProfile],
    explicit_types: Mapping[str, str],
    records: Iterable[Mapping[str, object]],
) -> AnalysisResult:
    """Calculate aggregates in one pass over supplied records.

    Callers own source access and use ``required_fields`` for projection. Plan
    and type validation precede iteration; records are never materialized.
    """
    validate_analysis_plan(plan, profiles)
    inferred = {column.name: column.inferred_type for column in profiles}
    explicit = dict(explicit_types)
    metric = plan.metric
    metric_kind: Optional[str] = None
    if metric.operation in {"sum", "average", "share_of_total"}:
        metric_kind = _type_for(metric.column, explicit, inferred)
        if metric_kind not in NUMERIC_TYPES:
            raise ValueError("Metric {} requires an explicitly mapped numeric column.".format(metric.operation))
    elif metric.operation == "distinct_count":
        metric_kind = _type_for(metric.column, explicit, inferred)

    field_names = required_fields(plan)
    kinds: Dict[str, str] = {}
    for name in field_names:
        kinds[name] = metric_kind if name == metric.column and metric_kind else _type_for(name, explicit, inferred)
    if plan.time_axis and kinds[plan.time_axis.column] not in DATE_TYPES:
        raise ValueError("Time column {!r} requires an explicit date or datetime mapping.".format(plan.time_axis.column))

    groups = {}
    invalid_counts: Dict[str, int] = {}
    valid_row_count = 0
    structural_fields = set(plan.dimensions)
    structural_fields.update(item.column for item in plan.filters)
    if plan.time_axis:
        structural_fields.add(plan.time_axis.column)
    for record in records:
        parsed = {}
        row_bad = False
        for name in field_names:
            raw = record.get(name)
            try:
                parsed[name] = _convert(raw, kinds[name])
            except (ValueError, TypeError):
                invalid_counts["invalid:{}".format(name)] = invalid_counts.get("invalid:{}".format(name), 0) + 1
                if name in structural_fields or name != metric.column or metric.operation == "distinct_count":
                    row_bad = True
                parsed[name] = None
            else:
                if parsed[name] is None:
                    invalid_counts["missing:{}".format(name)] = invalid_counts.get("missing:{}".format(name), 0) + 1

        filter_match = True
        for item in plan.filters:
            value = parsed[item.column]
            kind = kinds[item.column]
            try:
                if item.operation == "in":
                    target = [_convert(part, kind) for part in item.value]
                elif item.operation == "between":
                    target = tuple(_convert(part, kind) for part in item.value)
                else:
                    target = _convert(item.value, kind)
            except (ValueError, TypeError) as exc:
                raise ValueError("Invalid filter value for column {!r}: {}".format(item.column, exc)) from exc
            if not _matches(value, item.operation, target):
                filter_match = False
                break
        if not filter_match or row_bad:
            continue
        if plan.time_axis and parsed[plan.time_axis.column] is None:
            continue
        valid_row_count += 1
        time_value = _date_bucket(parsed[plan.time_axis.column], plan.time_axis.grain) if plan.time_axis else None
        group_values = tuple(parsed[name] for name in plan.dimensions)
        group_key = group_values + ((time_value,) if plan.time_axis else ())
        state = groups.setdefault(group_key, {"count": 0, "sum": Decimal(0), "metric_count": 0, "distinct": set()})
        state["count"] += 1
        if metric.operation == "count_rows":
            continue
        metric_value = parsed.get(metric.column)
        if metric.operation == "distinct_count":
            if metric_value is not None:
                state["distinct"].add(metric_value)
            continue
        if metric_value is not None:
            state["sum"] += metric_value
            state["metric_count"] += 1

    denominator_totals = {}
    if metric.operation == "share_of_total":
        dimension_indexes = {name: index for index, name in enumerate(plan.dimensions)}
        denominator_indexes = [dimension_indexes[name] for name in metric.denominator_scope]
        for group_key, state in groups.items():
            denom_key = tuple(group_key[index] for index in denominator_indexes)
            if plan.time_axis:
                denom_key += (group_key[-1],)
            denominator_totals[denom_key] = denominator_totals.get(denom_key, Decimal(0)) + state["sum"]

    result_rows = []
    output_names = list(plan.dimensions) + ([plan.time_axis.column] if plan.time_axis else [])
    for group_key in sorted(groups, key=lambda key: tuple(_sort_value(value) for value in key)):
        state = groups[group_key]
        values = group_key[:len(plan.dimensions)]
        row = dict(zip(plan.dimensions, values))
        if plan.time_axis:
            row[plan.time_axis.column] = group_key[-1]
        if metric.operation == "count_rows":
            result_value = state["count"]
        elif metric.operation == "distinct_count":
            result_value = len(state["distinct"])
        elif metric.operation == "average":
            result_value = state["sum"] / state["metric_count"] if state["metric_count"] else None
        elif metric.operation == "share_of_total":
            dimension_indexes = {name: index for index, name in enumerate(plan.dimensions)}
            denom_key = tuple(group_key[dimension_indexes[name]] for name in metric.denominator_scope)
            if plan.time_axis:
                denom_key += (group_key[-1],)
            denominator = denominator_totals.get(denom_key, Decimal(0))
            result_value = state["sum"] / denominator if denominator else None
        else:
            result_value = state["sum"] if state["metric_count"] else None
        row["value"] = result_value
        result_rows.append(row)

    formula = {
        "operation": metric.operation,
        "column": metric.column,
        "denominator_scope": list(metric.denominator_scope) if metric.operation == "share_of_total" else None,
        "filters": [asdict_filter(item) for item in plan.filters],
        "time_grain": plan.time_axis.grain if plan.time_axis else None,
        "valid_row_count": valid_row_count,
        "group_fields": output_names,
    }
    return AnalysisResult(
        plan=plan,
        rows=result_rows,
        valid_row_count=valid_row_count,
        invalid_value_counts=dict(sorted(invalid_counts.items())),
        selected_fields=field_names,
        formula_metadata=formula,
    )


def asdict_filter(item):
    return {"column": item.column, "operation": item.operation, "value": item.value}
