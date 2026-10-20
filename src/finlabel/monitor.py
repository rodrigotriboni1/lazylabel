"""Deterministic schema and data-quality monitoring."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

from finlabel.sources.base import DataSource


@dataclass(frozen=True)
class SchemaBaseline:
    columns: Mapping[str, str]
    required_columns: Sequence[str]
    max_missing_ratio: Mapping[str, float]
    allow_extra_columns: bool


@dataclass(frozen=True)
class QualityFinding:
    code: str
    severity: str
    column: Optional[str]
    expected: Optional[str]
    observed: Optional[str]
    message: str


def capture_schema(source: DataSource) -> SchemaBaseline:
    """Return an editable candidate; no missingness threshold is inferred."""
    columns = {column.name: column.inferred_type for column in source.columns()}
    return SchemaBaseline(columns, tuple(columns), {}, False)


def monitor_source(source: DataSource, baseline: SchemaBaseline) -> Sequence[QualityFinding]:
    observed = {column.name: column for column in source.columns()}
    findings = []
    for name in baseline.required_columns:
        if name not in observed:
            findings.append(QualityFinding(
                "missing_required_column", "error", name, baseline.columns.get(name), None,
                "Required column {!r} is missing.".format(name),
            ))
    if not baseline.allow_extra_columns:
        for name in sorted(set(observed) - set(baseline.columns)):
            findings.append(QualityFinding(
                "unexpected_column", "warning", name, None, observed[name].inferred_type,
                "Column {!r} is not present in the confirmed schema.".format(name),
            ))
    for name, expected in baseline.columns.items():
        column = observed.get(name)
        if column is None:
            continue
        if expected != column.inferred_type:
            findings.append(QualityFinding(
                "type_mismatch", "warning", name, expected, column.inferred_type,
                "Column {!r} has a different inferred type.".format(name),
            ))
    for name, maximum in baseline.max_missing_ratio.items():
        if maximum < 0 or maximum > 1:
            raise ValueError("Missing-value threshold for {!r} must be between 0 and 1.".format(name))
        column = observed.get(name)
        if column is None:
            continue
        total = column.missing_count + column.non_missing_count
        ratio = column.missing_count / total if total else 0.0
        if ratio > maximum:
            findings.append(QualityFinding(
                "missing_ratio_exceeded", "error", name, str(maximum), str(ratio),
                "Column {!r} missing ratio exceeds the configured limit.".format(name),
            ))
    return findings


def save_schema_baseline(baseline: SchemaBaseline, path) -> None:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(baseline)
    payload["required_columns"] = list(baseline.required_columns)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_schema_baseline(path) -> SchemaBaseline:
    source = Path(path).expanduser()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
        return SchemaBaseline(
            columns=raw["columns"],
            required_columns=tuple(raw["required_columns"]),
            max_missing_ratio=raw.get("max_missing_ratio", {}),
            allow_extra_columns=bool(raw.get("allow_extra_columns", False)),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("Invalid schema baseline {}: {}".format(source, exc)) from exc
