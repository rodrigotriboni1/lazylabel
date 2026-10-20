"""Immutable JSONL records for label suggestion runs."""

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4


_RUN_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class LabelSuggestion:
    suggestion_id: str
    run_id: str
    source_name: str
    record_id: str
    input_digest: str
    task_id: str
    label: str
    rationale: Optional[str]
    model_ref: str
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LabelRun:
    run_id: str
    source_name: str
    task_id: str
    model_ref: str
    suggestion_path: Path
    row_count: int
    invalid_count: int


def parse_suggestion(raw: str, *, valid_labels) -> tuple:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Model output is not valid JSON.") from exc
    if not isinstance(payload, dict) or set(payload) - {"label", "rationale"}:
        raise ValueError("Model output must contain only label and optional rationale fields.")
    label = payload.get("label")
    if not isinstance(label, str) or label not in valid_labels:
        raise ValueError("Model output contains a label outside the configured task labels.")
    rationale = payload.get("rationale")
    if rationale is not None and (not isinstance(rationale, str) or len(rationale) > 1000):
        raise ValueError("Model rationale must be a string of at most 1000 characters.")
    return label, rationale
