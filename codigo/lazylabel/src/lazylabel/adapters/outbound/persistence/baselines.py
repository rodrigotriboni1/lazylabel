"""Deterministic schema and data-quality monitoring."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from lazylabel.domain.monitoring import QualityFinding, SchemaBaseline
from lazylabel.domain.monitoring import capture_schema as capture_schema_from_columns
from lazylabel.domain.monitoring import compare_schema
from lazylabel.adapters.outbound.sources.base import DataSource


def capture_schema(source: DataSource) -> SchemaBaseline:
    return capture_schema_from_columns(source.columns())


def monitor_source(source: DataSource, baseline: SchemaBaseline) -> Sequence[QualityFinding]:
    return compare_schema(source.columns(), baseline)


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
