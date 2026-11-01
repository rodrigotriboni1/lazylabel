"""Read-only source monitoring orchestration using canonical domain rules."""

import math
from typing import Sequence

from finlabel.application.ports.projects import ProjectLookup
from finlabel.application.ports.sources import SourceReader
from finlabel.application.use_cases.errors import InvalidSourceMetadata, SourceAccessError, SourceNotReadOnly
from finlabel.application.use_cases.projects import (
    _validate_columns,
    _resolve_source,
    _require_read_only,
)
from finlabel.domain.monitoring import (
    QualityFinding,
    SchemaBaseline,
    capture_schema,
    compare_schema,
)

__all__ = [
    "InvalidSourceMetadata",
    "SourceAccessError",
    "SourceNotReadOnly",
    "capture_project_schema",
    "monitor_project_source",
]


def capture_project_schema(
    projects: ProjectLookup,
    sources: SourceReader,
    project_reference: str,
    source_name: str,
) -> SchemaBaseline:
    """Create a schema candidate from a validated, read-only source profile."""
    source = _resolve_source(projects, sources, project_reference, source_name)
    _require_read_only(source)
    try:
        source_columns = source.columns()
    except Exception as exc:
        raise SourceAccessError("Source profile could not be read.") from exc
    columns = _validate_columns(source_columns)
    return capture_schema(columns)


def monitor_project_source(
    projects: ProjectLookup,
    sources: SourceReader,
    project_reference: str,
    source_name: str,
    baseline: SchemaBaseline,
) -> Sequence[QualityFinding]:
    """Compare a fresh read-only source profile with a confirmed baseline."""
    _validate_baseline(baseline)
    source = _resolve_source(projects, sources, project_reference, source_name)
    _require_read_only(source)
    try:
        source_columns = source.columns()
    except Exception as exc:
        raise SourceAccessError("Source profile could not be read.") from exc
    columns = _validate_columns(source_columns)
    try:
        return compare_schema(columns, baseline)
    except InvalidSourceMetadata:
        raise
    except (TypeError, ValueError) as exc:
        raise InvalidSourceMetadata("Source or baseline metadata is malformed.") from exc


def _validate_baseline(baseline: SchemaBaseline) -> None:
    if not isinstance(baseline, SchemaBaseline):
        raise InvalidSourceMetadata("Schema baseline has an invalid type.")
    if not isinstance(baseline.columns, dict) and not hasattr(baseline.columns, "items"):
        raise InvalidSourceMetadata("Schema baseline columns must be a mapping.")
    if any(
        not isinstance(name, str) or not name.strip() or not isinstance(kind, str) or not kind
        for name, kind in baseline.columns.items()
    ):
        raise InvalidSourceMetadata("Schema baseline columns are malformed.")
    if not isinstance(baseline.required_columns, (list, tuple)) or any(
        not isinstance(name, str) or not name.strip() for name in baseline.required_columns
    ):
        raise InvalidSourceMetadata("Schema baseline required columns are malformed.")
    if len(baseline.required_columns) != len(set(baseline.required_columns)):
        raise InvalidSourceMetadata("Schema baseline required columns must be unique.")
    if not hasattr(baseline.max_missing_ratio, "items"):
        raise InvalidSourceMetadata("Schema baseline missing ratios must be a mapping.")
    for name, ratio in baseline.max_missing_ratio.items():
        if not isinstance(name, str) or not name.strip() or isinstance(ratio, bool):
            raise InvalidSourceMetadata("Schema baseline missing ratios are malformed.")
        try:
            valid = math.isfinite(ratio) and 0 <= ratio <= 1
        except TypeError as exc:
            raise InvalidSourceMetadata("Schema baseline missing ratios are malformed.") from exc
        if not valid:
            raise InvalidSourceMetadata("Schema baseline missing ratios must be between zero and one.")
    if not isinstance(baseline.allow_extra_columns, bool):
        raise InvalidSourceMetadata("Schema baseline extra-column setting must be boolean.")
