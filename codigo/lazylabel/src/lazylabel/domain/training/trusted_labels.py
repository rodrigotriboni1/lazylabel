"""Trusted-label values and deterministic provenance metadata."""

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence


_TRUST_KINDS = frozenset({"provided_ground_truth", "validated_rule"})
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_BLOCKED_PROVENANCE = re.compile(
    r"(?:model[ _-]?(?:output|prediction)|inference|suggestion|outcome|review[ _-]?log)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TrustedLabelSourceSpec:
    source_name: str
    task_id: str
    label_column: str
    label_mapping: Mapping[str, str]
    provenance_id: str
    trust_kind: str

    def __post_init__(self):
        for field_name in ("source_name", "task_id", "label_column", "provenance_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("{} must be a non-empty string.".format(field_name))
        if not isinstance(self.source_name, str) or not _NAME.fullmatch(self.source_name):
            raise ValueError("source_name must use 1-64 safe identifier characters.")
        if not isinstance(self.task_id, str) or not _NAME.fullmatch(self.task_id):
            raise ValueError("task_id must use 1-64 safe identifier characters.")
        if not isinstance(self.trust_kind, str) or self.trust_kind not in _TRUST_KINDS:
            raise ValueError("trust_kind must be provided_ground_truth or validated_rule.")
        if _BLOCKED_PROVENANCE.search(self.provenance_id):
            raise ValueError("Model predictions, outcomes, suggestions, and review logs cannot be trusted provenance.")
        if not isinstance(self.label_mapping, Mapping) or not self.label_mapping:
            raise ValueError("label_mapping must explicitly map source values to task labels.")
        normalized = {}
        for source_label, task_label in self.label_mapping.items():
            if not isinstance(source_label, str) or not source_label.strip():
                raise ValueError("Source labels in label_mapping must be non-empty strings.")
            if not isinstance(task_label, str) or not task_label.strip():
                raise ValueError("Mapped task labels must be non-empty strings.")
            normalized[source_label] = task_label
        object.__setattr__(self, "label_mapping", MappingProxyType(normalized))

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "TrustedLabelSourceSpec":
        if not isinstance(raw, Mapping):
            raise ValueError("Trusted-label source configuration must be an object.")
        allowed = {"source_name", "task_id", "label_column", "label_mapping", "provenance_id", "trust_kind"}
        allowed.update({"snapshot_sha256", "row_count"})
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError("Unknown trusted-label field(s): {}".format(", ".join(sorted(unknown))))
        return cls(**{key: value for key, value in raw.items() if key in {
            "source_name", "task_id", "label_column", "label_mapping", "provenance_id", "trust_kind"
        }})

    def to_dict(self) -> dict:
        return {
            "source_name": self.source_name,
            "task_id": self.task_id,
            "label_column": self.label_column,
            "label_mapping": dict(self.label_mapping),
            "provenance_id": self.provenance_id,
            "trust_kind": self.trust_kind,
        }


@dataclass(frozen=True)
class TrustedLabelRecord:
    record_ref: str
    features: Mapping[str, object]
    label: str
    input_digest: str
    split_key: str = ""

    def __post_init__(self):
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


@dataclass(frozen=True)
class TrustedLabelBatch:
    source_name: str
    task_id: str
    provenance_id: str
    trust_kind: str
    feature_columns: Sequence[str]
    label_column: str
    records: Sequence[TrustedLabelRecord]
    snapshot_sha256: str

    def __post_init__(self):
        object.__setattr__(self, "feature_columns", tuple(self.feature_columns))
        object.__setattr__(self, "records", tuple(self.records))

    @property
    def row_count(self) -> int:
        return len(self.records)


def supervision_key(task_id: str, source_name: str) -> str:
    return "{}::{}".format(task_id, source_name)


def _canonical_digest(values: Mapping[str, object]) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def snapshot_manifest(batch: TrustedLabelBatch) -> dict:
    """Return privacy-safe registration metadata; no feature or label values."""
    return {
        "schema_version": 1,
        "source_name": batch.source_name,
        "task_id": batch.task_id,
        "provenance_id": batch.provenance_id,
        "trust_kind": batch.trust_kind,
        "feature_columns": list(batch.feature_columns),
        "label_column": batch.label_column,
        "row_count": batch.row_count,
        "snapshot_sha256": batch.snapshot_sha256,
    }
