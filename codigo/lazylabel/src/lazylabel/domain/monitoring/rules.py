"""Compare confirmed schema constraints with supplied column profiles."""

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from lazylabel.domain.projects import ColumnProfile


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


def capture_schema(columns: Sequence[ColumnProfile]) -> SchemaBaseline:
    """Return an editable candidate without inferring a missingness threshold."""
    inferred = {column.name: column.inferred_type for column in columns}
    return SchemaBaseline(inferred, tuple(inferred), {}, False)


def compare_schema(columns: Sequence[ColumnProfile], baseline: SchemaBaseline) -> Sequence[QualityFinding]:
    observed = {column.name: column for column in columns}
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
