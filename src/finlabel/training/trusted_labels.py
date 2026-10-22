"""Load explicitly registered, read-only reference labels for training."""

import hashlib
import hmac
import json
import re
import secrets
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


def _opaque_ref(key: bytes, source_name: str, record_id: str) -> str:
    material = (source_name + "\0" + record_id).encode("utf-8")
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def _registered_spec(project, task_id: str):
    matches = []
    for key, raw in project.supervision_sources.items():
        spec = TrustedLabelSourceSpec.from_dict(raw)
        snapshot_sha256 = raw.get("snapshot_sha256")
        row_count = raw.get("row_count")
        if (snapshot_sha256 is None) != (row_count is None):
            raise ValueError("Trusted-label snapshot digest and row count must be stored together.")
        if snapshot_sha256 is not None and (
            not isinstance(snapshot_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256)
            or not isinstance(row_count, int)
            or isinstance(row_count, bool)
            or row_count < 1
        ):
            raise ValueError("Trusted-label snapshot metadata is malformed.")
        if key != supervision_key(spec.task_id, spec.source_name):
            raise ValueError("Trusted-label source registry key does not match its task and source.")
        if spec.task_id == task_id:
            matches.append((spec, snapshot_sha256, row_count))
    if len(matches) != 1:
        if not matches:
            raise ValueError("No explicitly registered trusted-label source for task {!r}.".format(task_id))
        raise ValueError("Task {!r} has multiple trusted sources; select one before dataset preparation.".format(task_id))
    return matches[0]


def load_trusted_labels(project, task) -> TrustedLabelBatch:
    """Read trusted labels and selected features without modifying or logging rows."""
    spec, expected_snapshot, expected_count = _registered_spec(project, task.task_id)
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
    artifact_root = workspace if workspace.name == ".finlabel" else workspace / ".finlabel"
    try:
        source.path.resolve().relative_to(artifact_root)
    except ValueError:
        pass
    else:
        raise ValueError("Project artifacts cannot be registered as trusted supervision sources.")
    capabilities = source.capabilities()
    if not capabilities.read_only or not capabilities.stable_record_ids or not capabilities.selected_columns:
        raise ValueError("Trusted-label source must support read-only access, stable IDs, and selected columns.")
    identifiable = " ".join((spec.source_name, source.path.name, spec.label_column, spec.task_id))
    if source.spec.table:
        identifiable += " " + source.spec.table
    if re.search(r"(?:\bmodel\b|model[ _-]?output|prediction|suggestion|outcome|review[ _-]?log)", identifiable, re.IGNORECASE):
        raise ValueError("Sources identifiable as model outputs, suggestions, outcomes, or review logs cannot be trusted labels.")
    available = {column.name for column in source.columns()}
    requested = tuple(task.input_columns) + (spec.label_column,)
    missing = sorted(set(requested) - available)
    if missing:
        raise ValueError("Trusted-label source is missing required columns: {}".format(", ".join(missing)))

    records = []
    seen_ids = set()
    snapshot = hashlib.sha256()
    snapshot.update(json.dumps({
        "source_name": spec.source_name,
        "task_id": spec.task_id,
        "label_column": spec.label_column,
        "label_mapping": dict(spec.label_mapping),
        "provenance_id": spec.provenance_id,
        "trust_kind": spec.trust_kind,
        "feature_columns": list(task.input_columns),
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    pending_records = []
    for source_record in source.iter_records(requested):
        record_id = source_record.record_id
        if not isinstance(record_id, str) or not record_id.strip():
            raise ValueError("Trusted-label source contains a missing stable record ID.")
        if record_id in seen_ids:
            raise ValueError("Trusted-label source contains duplicate stable record IDs.")
        seen_ids.add(record_id)
        raw_label = source_record.values.get(spec.label_column)
        if raw_label is None or not str(raw_label).strip():
            raise ValueError("Trusted-label source contains a missing label.")
        raw_label = str(raw_label)
        if raw_label not in spec.label_mapping:
            raise ValueError("Trusted-label source contains an unmapped label.")
        label = spec.label_mapping[raw_label]
        if label not in task.labels:
            raise ValueError("Trusted-label mapping resolves outside the task label set.")
        features = {column: source_record.values[column] for column in task.input_columns}
        input_digest = _canonical_digest(features)
        snapshot.update(source_record.input_digest.encode("ascii"))
        snapshot.update(b"\n")
        pending_records.append((record_id, features, label, input_digest))

    if not pending_records:
        raise ValueError("Trusted-label source contains no records.")
    snapshot_sha256 = snapshot.hexdigest()
    if expected_snapshot is not None and (
        expected_snapshot != snapshot_sha256 or expected_count != len(pending_records)
    ):
        raise ValueError("Trusted-label source changed since registration; refresh its trusted snapshot before training.")
    # Artifact refs stay private per load; the independent split key is deterministic,
    # internal, and never serialized, so repeated snapshot/seed splits remain stable.
    opaque_key = secrets.token_bytes(32)
    records = []
    for ordinal, (record_id, features, label, input_digest) in enumerate(pending_records):
        split_material = "{}\0{}\0{}\0{}".format(snapshot_sha256, ordinal, input_digest, spec.source_name)
        split_key = hashlib.sha256(split_material.encode("utf-8")).hexdigest()
        records.append(TrustedLabelRecord(_opaque_ref(opaque_key, spec.source_name, record_id),
                                          features, label, input_digest, split_key))
    return TrustedLabelBatch(
        spec.source_name, spec.task_id, spec.provenance_id, spec.trust_kind,
        tuple(task.input_columns), spec.label_column, tuple(records), snapshot_sha256,
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
