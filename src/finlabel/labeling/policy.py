"""Task-scoped configuration for autonomous labeling; not calibration evidence."""

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from finlabel.labeling.task import LabelTask, PathLike


@dataclass(frozen=True)
class LabelingPolicy:
    policy_id: str
    task_id: str
    allowed_labels: Sequence[str]
    rules_version: str
    calibration_ref: Optional[str]
    min_calibrated_confidence: float
    max_staleness_seconds: int

    def __post_init__(self):
        for name in ("policy_id", "task_id", "rules_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("{} must be a non-empty string.".format(name))
        if not isinstance(self.allowed_labels, (tuple, list)) or not self.allowed_labels:
            raise ValueError("allowed_labels must be a non-empty list of labels.")
        if any(not isinstance(label, str) or not label.strip() for label in self.allowed_labels):
            raise ValueError("allowed_labels must contain non-empty strings.")
        if len(set(self.allowed_labels)) != len(self.allowed_labels):
            raise ValueError("allowed_labels must be unique.")
        object.__setattr__(self, "allowed_labels", tuple(self.allowed_labels))
        if self.calibration_ref is not None and (
            not isinstance(self.calibration_ref, str) or not self.calibration_ref.strip()
        ):
            raise ValueError("calibration_ref must be a non-empty string or null.")
        confidence = self.min_calibrated_confidence
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("min_calibrated_confidence must be finite and between 0 and 1.")
        seconds = self.max_staleness_seconds
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
            raise ValueError("max_staleness_seconds must be a positive integer.")

    @property
    def has_calibration_configuration(self) -> bool:
        """A reference is configured; runtime must still validate its evidence."""
        return self.calibration_ref is not None


def load_policy(path: PathLike, *, task: LabelTask) -> LabelingPolicy:
    source = Path(path).expanduser()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not load labeling policy {}: {}".format(source, exc)) from exc
    if not isinstance(raw, dict):
        raise ValueError("Labeling policy document must be a JSON object.")
    fields = {"policy_id", "task_id", "allowed_labels", "rules_version", "calibration_ref",
              "min_calibrated_confidence", "max_staleness_seconds"}
    unknown = set(raw) - fields
    if unknown:
        raise ValueError("Unknown labeling policy field(s): {}".format(", ".join(sorted(unknown))))
    try:
        policy = LabelingPolicy(**raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid labeling policy: {}".format(exc)) from exc
    if policy.task_id != task.task_id:
        raise ValueError("Labeling policy task_id {!r} does not match task {!r}.".format(
            policy.task_id, task.task_id))
    if set(policy.allowed_labels) != set(task.labels):
        raise ValueError("Labeling policy allowed_labels must match task labels exactly.")
    return policy
