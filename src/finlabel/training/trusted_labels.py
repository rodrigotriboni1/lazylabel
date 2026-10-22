"""Load explicitly registered, read-only reference labels for training."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from finlabel.project import open_source


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
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError("Unknown trusted-label field(s): {}".format(", ".join(sorted(unknown))))
        return cls(**dict(raw))

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


def _opaque_ref(source_name: str, record_id: str) -> str:
    material = (source_name + "\0" + record_id).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _registered_spec(project, task_id: str) -> TrustedLabelSourceSpec:
    matches = []
    for key, raw in project.supervision_sources.items():
        spec = TrustedLabelSourceSpec.from_dict(raw)
        if key != supervision_key(spec.task_id, spec.source_name):
            raise ValueError("Trusted-label source registry key does not match its task and source.")
        if spec.task_id == task_id:
            matches.append(spec)
    if len(matches) != 1:
        if not matches:
            raise ValueError("No explicitly registered trusted-label source for task {!r}.".format(task_id))
        raise ValueError("Task {!r} has multiple trusted sources; select one before dataset preparation.".format(task_id))
    return matches[0]


def load_trusted_labels(project, task) -> TrustedLabelBatch:
    """Read trusted labels and selected features without modifying or logging rows."""
    spec = _registered_spec(project, task.task_id)
    if spec.source_name not in project.sources:
        raise ValueError("Trusted-label source is not a configured project source.")
    if spec.task_id != task.task_id:
        raise ValueError("Trusted-label source task does not match the requested task.")
    if spec.label_column in task.input_columns:
        raise ValueError("Trusted label column must not appear in task.input_columns.")
    if set(spec.label_mapping.values()) - set(task.labels):
        raise ValueError("Trusted label mapping contains labels outside the configured task taxonomy.")

    source = open_source(project, spec.source_name)
    workspace = Path(project.workspace_dir).expanduser().resolve()
    try:
        source.path.resolve().relative_to(workspace)
    except ValueError:
        pass
    else:
        raise ValueError("Project artifacts cannot be registered as trusted supervision sources.")
    capabilities = source.capabilities()
    if not capabilities.read_only or not capabilities.stable_record_ids or not capabilities.selected_columns:
        raise ValueError("Trusted-label source must support read-only access, stable IDs, and selected columns.")
    available = {column.name for column in source.columns()}
    requested = tuple(task.input_columns) + (spec.label_column,)
    missing = sorted(set(requested) - available)
    if missing:
        raise ValueError("Trusted-label source is missing required columns: {}".format(", ".join(missing)))

    records = []
    seen_ids = set()
    snapshot = hashlib.sha256()
    for source_record in source.iter_records(requested):
        record_id = source_record.record_id
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError("Trusted-label source contains a missing stable record ID.")
        if record_id in seen_ids:
            raise ValueError("Trusted-label source contains duplicate stable record IDs.")
        seen_ids.add(record_id)
        raw_label = source_record.values.get(spec.label_column)
        if raw_label is None or not str(raw_label).strip():
            raise ValueError("Trusted-label source contains a missing label at opaque record {}.".format(_opaque_ref(spec.source_name, record_id)[:12]))
        raw_label = str(raw_label)
        if raw_label not in spec.label_mapping:
            raise ValueError("Trusted-label source contains an unmapped label at opaque record {}.".format(_opaque_ref(spec.source_name, record_id)[:12]))
        label = spec.label_mapping[raw_label]
        if label not in task.labels:
            raise ValueError("Trusted-label mapping resolves outside the task label set.")
        features = {column: source_record.values[column] for column in task.input_columns}
        input_digest = _canonical_digest(features)
        record_ref = _opaque_ref(spec.source_name, record_id)
        snapshot.update(record_ref.encode("ascii"))
        snapshot.update(b"\0")
        snapshot.update(source_record.input_digest.encode("ascii"))
        snapshot.update(b"\n")
        records.append(TrustedLabelRecord(record_ref, features, label, input_digest))

    if not records:
        raise ValueError("Trusted-label source contains no records.")
    return TrustedLabelBatch(
        spec.source_name, spec.task_id, spec.provenance_id, spec.trust_kind,
        tuple(task.input_columns), spec.label_column, tuple(records), snapshot.hexdigest(),
    )


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
