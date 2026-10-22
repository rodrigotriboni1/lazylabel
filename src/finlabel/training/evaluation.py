"""Calibration artifacts bound to trusted labels and one exact inference identity."""

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from finlabel.training.task_spec import task_spec_sha256


SUPPORTED_SCORE_METHOD = "label_json_mean_log_likelihood_v2"
CALIBRATOR_METHOD = "platt_top_score_v1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _hash(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains a duplicate key.")
        result[key] = value
    return result


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _records(predictions, labels):
    if isinstance(labels, Mapping):
        label_by_ref = dict(labels)
    else:
        label_by_ref = {}
        for row in labels:
            ref = row.get("record_ref") if isinstance(row, Mapping) else None
            label = row.get("label") if isinstance(row, Mapping) else None
            if not ref or ref in label_by_ref:
                raise ValueError("Trusted calibration labels require unique record_ref values.")
            label_by_ref[ref] = label
    if any(not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{64}", ref) for ref in label_by_ref):
        raise ValueError("Trusted calibration labels require opaque SHA-256 record references.")
    if not isinstance(predictions, (list, tuple)):
        raise ValueError("Calibration predictions must be a sequence of held-out records.")
    normalized = []
    seen = set()
    for item in predictions:
        if not isinstance(item, Mapping) or not isinstance(item.get("record_ref"), str):
            raise ValueError("Calibration predictions require record_ref provenance.")
        ref = item["record_ref"]
        prediction = item.get("prediction")
        if not re.fullmatch(r"[0-9a-f]{64}", ref) or ref in seen or prediction is None:
            raise ValueError("Calibration predictions contain a duplicate ID or missing prediction.")
        seen.add(ref)
        if ref not in label_by_ref:
            raise ValueError("Calibration prediction has no trusted reference label.")
        normalized.append((ref, prediction, label_by_ref[ref]))
    if seen != set(label_by_ref):
        raise ValueError("Trusted calibration labels and predictions must have identical record IDs.")
    if not normalized:
        raise ValueError("Calibration partition is empty.")
    return normalized


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


def _scores(prediction, task, method):
    evidence = getattr(prediction, "confidence_evidence", None)
    if getattr(prediction, "confidence_method", None) != method or not isinstance(evidence, Mapping):
        raise ValueError("Calibration score method/evidence does not match the requested backend method.")
    if list(evidence.keys()) != list(task.labels):
        raise ValueError("Calibration class scores must use the exact task label set and order.")
    if any(not _number(score) for score in evidence.values()):
        raise ValueError("Calibration scores must be finite numeric values.")
    predicted = getattr(prediction, "label", None)
    winner = max(task.labels, key=lambda label: evidence[label])
    if not predicted or predicted not in task.labels or predicted != winner:
        raise ValueError("Generated label conflicts with the raw-score winner; calibration fails closed.")
    return evidence, predicted


def _fit_logistic(xs, ys):
    # Deterministic two-parameter Newton fit with a small L2 penalty.
    if len(set(ys)) != 2:
        raise ValueError("Calibration needs both correct and incorrect held-out predictions.")
    mean = sum(xs) / len(xs)
    scale = math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
    if scale < 1e-12:
        raise ValueError("Calibration scores have no usable variation.")
    values = [( (x - mean) / scale, y) for x, y in zip(xs, ys)]
    a, b = 0.0, math.log(sum(ys) / (len(ys) - sum(ys)))
    for _ in range(100):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, y in values:
            z = max(-40.0, min(40.0, a * x + b))
            p = 1.0 / (1.0 + math.exp(-z))
            w = max(1e-9, p * (1.0 - p))
            error = p - y
            g0 += error * x
            g1 += error
            h00 += w * x * x
            h01 += w * x
            h11 += w
        g0 += 1e-6 * a
        g1 += 1e-6 * b
        h00 += 1e-6
        h11 += 1e-6
        determinant = h00 * h11 - h01 * h01
        if determinant <= 1e-18:
            raise ValueError("Calibration fit is numerically singular.")
        da = (h11 * g0 - h01 * g1) / determinant
        db = (-h01 * g0 + h00 * g1) / determinant
        a -= da
        b -= db
        if max(abs(da), abs(db)) < 1e-8:
            break
    return {"slope": a / scale, "intercept": b - a * mean / scale, "mean": mean, "scale": scale}


@dataclass(frozen=True)
class CalibrationResult:
    task_id: str
    policy_id: str
    model_ref: str
    confidence_method: str
    calibration_ref: str
    confidence: float


@dataclass(frozen=True)
class CalibrationArtifact:
    task_id: str
    task_spec_sha256: str
    policy_id: str
    model_ref: str
    confidence_method: str
    calibration_ref: str
    calibrator_method: str
    parameters: Mapping[str, float]
    source_hashes: Mapping[str, str]
    metrics: Mapping[str, object]
    labels: tuple

    def __post_init__(self):
        for name in ("task_id", "policy_id", "model_ref", "calibration_ref", "task_spec_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Calibration artifact {} must be a non-empty string.".format(name))
        if not _HASH_RE.fullmatch(self.task_spec_sha256):
            raise ValueError("Calibration artifact task_spec_sha256 must be a SHA-256 digest.")
        if self.confidence_method != SUPPORTED_SCORE_METHOD or self.calibrator_method != CALIBRATOR_METHOD:
            raise ValueError("Calibration artifact method is unsupported.")
        if not isinstance(self.labels, (list, tuple)) or not self.labels or any(
                not isinstance(label, str) or not label.strip() for label in self.labels):
            raise ValueError("Calibration artifact labels must be a non-empty ordered taxonomy.")
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("Calibration artifact labels must be unique.")
        object.__setattr__(self, "labels", tuple(self.labels))
        expected_parameters = {"slope", "intercept", "mean", "scale"}
        if not isinstance(self.parameters, Mapping) or set(self.parameters) != expected_parameters:
            raise ValueError("Calibration artifact parameters are incomplete or unknown.")
        if any(not _number(value) for value in self.parameters.values()) or self.parameters["scale"] <= 0:
            raise ValueError("Calibration artifact parameters must be finite and scale must be positive.")
        expected_hashes = {"task_spec_sha256", "calibration_manifest_sha256", "calibration_partition_sha256",
                           "calibration_dataset_sha256", "calibration_scores_sha256",
                           "trusted_labels_sha256"}
        if not isinstance(self.source_hashes, Mapping) or set(self.source_hashes) != expected_hashes:
            raise ValueError("Calibration artifact source hashes are incomplete or unknown.")
        if any(not isinstance(value, str) or not _HASH_RE.fullmatch(value)
               for value in self.source_hashes.values()):
            raise ValueError("Calibration artifact contains a malformed source hash.")
        if self.source_hashes["task_spec_sha256"] != self.task_spec_sha256:
            raise ValueError("Calibration artifact task specification identity is inconsistent.")
        if not isinstance(self.metrics, Mapping) or set(self.metrics) != {"brier_score", "row_count", "correct_count"}:
            raise ValueError("Calibration artifact metrics are incomplete or unknown.")
        brier = self.metrics["brier_score"]
        count = self.metrics["row_count"]
        correct = self.metrics["correct_count"]
        if not _number(brier) or not 0 <= brier <= 1:
            raise ValueError("Calibration Brier score must be finite and between 0 and 1.")
        if isinstance(count, bool) or not isinstance(count, int) or count < max(6, len(self.labels) * 3):
            raise ValueError("Calibration row_count is invalid or below minimum coverage.")
        if isinstance(correct, bool) or not isinstance(correct, int) or not 0 < correct < count:
            raise ValueError("Calibration correct_count must show at least one correct and one incorrect case.")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
        object.__setattr__(self, "source_hashes", MappingProxyType(dict(self.source_hashes)))
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    def calibrate(self, prediction, *, task, policy, model_ref):
        if (task.task_id != self.task_id or tuple(task.labels) != self.labels
                or task_spec_sha256(task) != self.task_spec_sha256
                or policy.task_id != self.task_id or tuple(policy.allowed_labels) != self.labels
                or policy.policy_id != self.policy_id or model_ref != self.model_ref
                or policy.calibration_ref != self.calibration_ref):
            raise ValueError("Calibration artifact identity does not match this labeling run.")
        evidence, _ = _scores(prediction, task, self.confidence_method)
        top = max(evidence[label] for label in task.labels)
        p = self.parameters
        z = max(-40.0, min(40.0, p["slope"] * top + p["intercept"]))
        confidence = 1.0 / (1.0 + math.exp(-z))
        return CalibrationResult(self.task_id, self.policy_id, self.model_ref,
                                 self.confidence_method, self.calibration_ref, confidence)

    def to_dict(self):
        payload = {"schema_version": 1, "task_id": self.task_id,
                "task_spec_sha256": self.task_spec_sha256, "policy_id": self.policy_id,
                "model_ref": self.model_ref, "confidence_method": self.confidence_method,
                "calibration_ref": self.calibration_ref, "calibrator_method": self.calibrator_method,
                "parameters": dict(self.parameters), "source_hashes": dict(self.source_hashes),
                "metrics": dict(self.metrics), "labels": list(self.labels)}
        payload["artifact_sha256"] = _hash(payload)
        return payload

    def save(self, path):
        destination = Path(path).expanduser().resolve()
        if destination.exists():
            raise FileExistsError("Refusing to overwrite calibration artifact: {}".format(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".finlabel-calibration-", dir=str(destination.parent))
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
        if not isinstance(raw, dict):
            raise ValueError("Unsupported or malformed calibration artifact.")
        allowed = {"schema_version", "task_id", "task_spec_sha256", "policy_id", "model_ref", "confidence_method",
                   "calibration_ref", "calibrator_method", "parameters", "source_hashes", "metrics", "labels",
                   "artifact_sha256"}
        if set(raw) != allowed or raw.get("schema_version") != 1:
            raise ValueError("Unsupported or malformed calibration artifact.")
        expected_hash = raw["artifact_sha256"]
        payload = dict(raw)
        del payload["artifact_sha256"]
        if not isinstance(expected_hash, str) or not _HASH_RE.fullmatch(expected_hash) or _hash(payload) != expected_hash:
            raise ValueError("Calibration artifact integrity hash does not match its contents.")
        if not isinstance(raw["labels"], list):
            raise ValueError("Calibration artifact labels must be stored as an ordered JSON array.")
        return cls(raw["task_id"], raw["task_spec_sha256"], raw["policy_id"], raw["model_ref"], raw["confidence_method"],
                   raw["calibration_ref"], raw["calibrator_method"], raw["parameters"],
                   raw["source_hashes"], raw["metrics"], tuple(raw["labels"]))


def fit_calibrator(calibration_predictions, trusted_labels, *, method, dataset_manifest,
                   task=None, policy=None, model_ref=None, calibration_ref=None) -> CalibrationArtifact:
    """Fit Platt confidence for correctness from held-out calibration scores and trusted targets.

    Predictions and labels must cover exactly the manifest's frozen calibration partition.
    `calibration_predictions` is [{record_ref, prediction: Prediction}, ...]; trusted_labels is
    a mapping of the same opaque refs to labels. Identity keywords are mandatory.
    """
    if method != SUPPORTED_SCORE_METHOD:
        raise ValueError("Unsupported raw score method; expected {}.".format(SUPPORTED_SCORE_METHOD))
    if task is None or policy is None or not model_ref or not isinstance(calibration_ref, str) or not calibration_ref.strip():
        raise ValueError("Calibration requires exact task, policy, model_ref, and calibration_ref identities.")
    if policy.task_id != task.task_id or tuple(policy.allowed_labels) != tuple(task.labels):
        raise ValueError("Calibration policy must match the task and its ordered label taxonomy.")
    if policy.calibration_ref != calibration_ref:
        raise ValueError("Calibration reference must match the task policy configuration.")
    if not isinstance(trusted_labels, Mapping):
        raise ValueError("Trusted calibration labels must be a record_ref-to-label mapping.")
    frozen = _frozen_calibration_partition(dataset_manifest, task)
    rows = _records(calibration_predictions, trusted_labels)
    prediction_refs = tuple(row[0] for row in rows)
    if set(prediction_refs) != set(frozen["refs"]) or len(prediction_refs) != len(frozen["refs"]):
        raise ValueError("Calibration predictions must cover exactly the frozen calibration partition.")
    if dict(trusted_labels) != frozen["labels"]:
        raise ValueError("Calibration labels differ from the frozen trusted calibration partition.")
    xs, ys = [], []
    observed = set()
    content = []
    for record_ref, prediction, trusted_label in rows:
        if trusted_label not in task.labels:
            raise ValueError("Trusted calibration label is outside the task taxonomy.")
        evidence, predicted = _scores(prediction, task, method)
        observed.add(trusted_label)
        top_score = max(evidence[label] for label in task.labels)
        xs.append(float(top_score))
        ys.append(float(predicted == trusted_label))
        content.append({"record_ref": record_ref, "scores": dict(evidence), "predicted": predicted,
                        "trusted_label": trusted_label})
    if observed != set(task.labels):
        raise ValueError("Calibration partition must cover every trusted task label.")
    if len(rows) < max(6, len(task.labels) * 3):
        raise ValueError("Calibration partition has insufficient class coverage.")
    parameters = _fit_logistic(xs, ys)
    probabilities = [1.0 / (1.0 + math.exp(-max(-40.0, min(40.0,
                     parameters["slope"] * x + parameters["intercept"])))) for x in xs]
    brier = sum((p - y) ** 2 for p, y in zip(probabilities, ys)) / len(ys)
    scores_hash = _hash(content)
    labels_hash = _hash(sorted((ref, label) for ref, label in
                               ((row[0], row[2]) for row in rows)))
    return CalibrationArtifact(
        task.task_id, task_spec_sha256(task), policy.policy_id, model_ref, method, calibration_ref, CALIBRATOR_METHOD,
        parameters, {"task_spec_sha256": frozen["task_spec_sha256"],
                    "calibration_manifest_sha256": frozen["manifest_sha256"],
                    "calibration_partition_sha256": frozen["partition_sha256"],
                    "calibration_dataset_sha256": frozen["dataset_sha256"],
                    "calibration_scores_sha256": scores_hash, "trusted_labels_sha256": labels_hash},
        {"brier_score": brier, "row_count": len(rows), "correct_count": int(sum(ys))},
        tuple(task.labels),
    )
