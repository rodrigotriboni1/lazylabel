"""Immutable JSONL records for label suggestion runs."""

import json
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from lazylabel.domain.labeling.prediction import Prediction, PredictionError
from lazylabel.domain.labeling.suggestions import LabelSuggestion, parse_suggestion


_RUN_ID = re.compile(r"^[0-9a-f]{32}$")


def verify_suggestions_file(path: Path, expected_sha256: str) -> None:
    """Fail closed if the immutable suggestion artifact differs from its run metadata."""
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Suggestion run has no valid integrity hash.")
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise ValueError("Suggestion file is missing or unreadable.") from exc
    if digest.hexdigest() != expected_sha256:
        raise ValueError("Suggestion file changed after the run was created.")


@dataclass(frozen=True)
class LabelRun:
    run_id: str
    source_name: str
    task_id: str
    model_ref: str
    suggestion_path: Path
    row_count: int
    invalid_count: int


def parse_prediction(raw: str, *, valid_labels, confidence_evidence=None,
                     confidence_method=None) -> Prediction:
    """Parse a model response without trusting any model-reported confidence."""
    label, rationale = parse_suggestion(raw, valid_labels=valid_labels)
    if confidence_evidence is not None and set(confidence_evidence) != set(valid_labels):
        raise ValueError("Raw label scores must cover the complete task taxonomy.")
    return Prediction(
        label=label, rationale=rationale, confidence_evidence=confidence_evidence,
        calibrated_confidence=None, calibration_ref=None, confidence_method=confidence_method,
        raw_output_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )
