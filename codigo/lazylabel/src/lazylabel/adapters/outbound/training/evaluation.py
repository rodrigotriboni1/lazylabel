"""Local calibration artifact persistence and frozen-file verification."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

from lazylabel.domain.training.task_spec import task_spec_sha256
from lazylabel.domain.training.evaluation import (
    CALIBRATOR_METHOD, SUPPORTED_SCORE_METHOD, CalibrationResult,
    CalibrationArtifact as DomainCalibrationArtifact, labeling_policy_sha256,
    fit_calibrator_from_partition, validate_calibration_request,
    _HASH_RE, _hash, _unique_object, _number, _records, _scores, _fit_logistic,
)


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _frozen_calibration_partition(dataset_manifest, task):
    """Verify the immutable manifest object, calibration rows, and their aligned opaque refs."""
    manifest_path = getattr(dataset_manifest, "manifest_path", None)
    expected_manifest_hash = getattr(dataset_manifest, "manifest_sha256", None)
    if manifest_path is None or not isinstance(expected_manifest_hash, str):
        raise ValueError("Calibration requires the TrustedDatasetManifest returned by dataset preparation.")
    actual_manifest_hash = _sha256_file(manifest_path)
    if actual_manifest_hash != expected_manifest_hash:
        raise ValueError("Trusted dataset manifest changed after preparation.")
    try:
        raw = json.loads(Path(manifest_path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read frozen trusted dataset manifest: {}".format(exc)) from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 1 or raw.get("kind") != "trusted_reference_dataset":
        raise ValueError("Unsupported trusted dataset manifest.")
    if (raw.get("task_id") != task.task_id or raw.get("snapshot_sha256") != dataset_manifest.snapshot_sha256
            or raw.get("task_spec_sha256") != task_spec_sha256(task)
            or raw.get("task_spec_sha256") != dataset_manifest.task_spec_sha256
            or raw.get("source_name") != dataset_manifest.source_name
            or raw.get("provenance_id") != dataset_manifest.provenance_id
            or raw.get("feature_columns") != list(task.input_columns)
            or raw.get("label_column") != dataset_manifest.label_column):
        raise ValueError("Trusted dataset manifest identity does not match this calibration task.")
    partitions = raw.get("partitions")
    calibration = partitions.get("calibration") if isinstance(partitions, dict) else None
    if not isinstance(calibration, dict):
        raise ValueError("Frozen dataset has no calibration partition.")
    entries = calibration.get("records")
    if not isinstance(entries, list) or len(entries) != calibration.get("count") or not entries:
        raise ValueError("Calibration manifest must contain aligned opaque record references.")
    refs = []
    content = []
    labels = {}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"record_ref", "input_digest"}:
            raise ValueError("Malformed calibration record reference in frozen manifest.")
        ref, digest = entry["record_ref"], entry["input_digest"]
        if (not isinstance(ref, str) or not _HASH_RE.fullmatch(ref) or ref in refs
                or not isinstance(digest, str) or not _HASH_RE.fullmatch(digest)):
            raise ValueError("Calibration manifest contains invalid or duplicate record metadata.")
        refs.append(ref)
        content.append({"input_digest": digest})
    partition_hash = _hash(content)
    if partition_hash != calibration.get("sha256"):
        raise ValueError("Calibration partition hash does not match its reference rows.")
    dataset_path = Path(manifest_path).parent / calibration.get("path", "")
    if not dataset_path.is_file():
        raise ValueError("Frozen calibration dataset file is missing.")
    dataset_hash = _sha256_file(dataset_path)
    if dataset_hash != calibration.get("dataset_sha256"):
        raise ValueError("Frozen calibration dataset changed after preparation.")
    try:
        with dataset_path.open("r", encoding="utf-8") as handle:
                lines = [json.loads(line, object_pairs_hook=_unique_object) for line in handle if line.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read frozen calibration rows: {}".format(exc)) from exc
    if len(lines) != len(entries):
        raise ValueError("Calibration row count no longer matches its aligned record references.")
    for line, entry in zip(lines, entries):
        if not isinstance(line, dict) or set(line) != {"prompt", "completion"}:
            raise ValueError("Calibration JSONL must preserve the training backend prompt/completion schema.")
        try:
            completion = json.loads(line["completion"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Calibration completion is malformed.") from exc
        if (not isinstance(line["prompt"], str) or not isinstance(completion, dict)
                or set(completion) != {"label"} or completion["label"] not in task.labels):
            raise ValueError("Calibration JSONL contains a malformed or unknown trusted label.")
        labels[entry["record_ref"]] = completion["label"]
    return {"manifest_sha256": actual_manifest_hash, "task_spec_sha256": task_spec_sha256(task),
            "partition_sha256": partition_hash,
            "dataset_sha256": dataset_hash, "labels": labels, "refs": tuple(refs)}


class CalibrationArtifact(DomainCalibrationArtifact):
    """Compatibility value with local artifact load/save operations."""

    def save(self, path):
        destination = Path(path).expanduser().resolve()
        if destination.exists():
            raise FileExistsError("Refusing to overwrite calibration artifact: {}".format(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".lazylabel-calibration-", dir=str(destination.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.to_dict(), handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise
        return destination

    @classmethod
    def load(cls, path):
        raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        return cls.from_dict(raw)


def fit_calibrator(calibration_predictions, trusted_labels, *, method, dataset_manifest,
                   task=None, policy=None, model_ref=None, calibration_ref=None) -> CalibrationArtifact:
    """Verify frozen files before fitting with the pure calibration rules."""
    validate_calibration_request(trusted_labels, method=method, task=task, policy=policy,
                                 model_ref=model_ref, calibration_ref=calibration_ref)
    frozen = _frozen_calibration_partition(dataset_manifest, task)
    fitted = fit_calibrator_from_partition(calibration_predictions, trusted_labels, method=method,
        frozen_partition=frozen, task=task, policy=policy, model_ref=model_ref, calibration_ref=calibration_ref)
    return CalibrationArtifact.from_dict(fitted.to_dict())
