"""Parse structured suggestions without trusting model text."""

import json
from dataclasses import asdict, dataclass
from typing import Optional

from finlabel.domain.labeling.prediction import PredictionError


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

def parse_suggestion(raw: str, *, valid_labels) -> tuple:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PredictionError("Model output is not valid JSON.") from exc
    if not isinstance(payload, dict) or set(payload) - {"label", "rationale"}:
        raise PredictionError("Model output must contain only label and optional rationale fields.")
    label = payload.get("label")
    if not isinstance(label, str):
        raise PredictionError("Model output requires a string label.")
    if label not in valid_labels:
        raise PredictionError("Model output contains a label outside the configured task labels.",
                              reason_code="unknown_label")
    rationale = payload.get("rationale")
    if rationale is not None and (not isinstance(rationale, str) or len(rationale) > 1000):
        raise PredictionError("Model rationale must be a string of at most 1000 characters.")
    return label, rationale
