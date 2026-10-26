"""Pure calibration values, contract hashes and deterministic fitting."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from finlabel.domain.training.task_spec import task_spec_sha256


SUPPORTED_SCORE_METHOD = "label_json_mean_log_likelihood_v2"
CALIBRATOR_METHOD = "platt_top_score_v1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _hash(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def labeling_policy_sha256(policy) -> str:
    """Digest every policy field that can affect autonomous labeling or confidence."""
    rules = []
    for rule in policy.rules:
        normalized = dict(rule)
        if "values" in normalized:
            normalized["values"] = list(normalized["values"])
        rules.append(normalized)
    return _hash({"policy_id": policy.policy_id, "task_id": policy.task_id,
        "allowed_labels": list(policy.allowed_labels), "rules_version": policy.rules_version,
        "rules": rules, "calibration_ref": policy.calibration_ref,
        "min_calibrated_confidence": policy.min_calibrated_confidence,
        "max_staleness_seconds": policy.max_staleness_seconds})


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
        expected_hashes = {"task_spec_sha256", "labeling_policy_sha256", "calibration_manifest_sha256", "calibration_partition_sha256",
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
                or policy.calibration_ref != self.calibration_ref
                or labeling_policy_sha256(policy) != self.source_hashes["labeling_policy_sha256"]):
            raise ValueError("Calibration artifact identity does not match this labeling run.")
        evidence, _ = _scores(prediction, task, self.confidence_method)
        top = max(evidence[label] for label in task.labels)
        p = self.parameters
        z = max(-40.0, min(40.0, p["slope"] * top + p["intercept"]))
        confidence = 1.0 / (1.0 + math.exp(-z))
        return CalibrationResult(self.task_id, self.policy_id, self.model_ref,
                                 self.confidence_method, self.calibration_ref, confidence)

    def to_dict(self):
        payload = {"schema_version": 2, "task_id": self.task_id,
                "task_spec_sha256": self.task_spec_sha256, "policy_id": self.policy_id,
                "model_ref": self.model_ref, "confidence_method": self.confidence_method,
                "calibration_ref": self.calibration_ref, "calibrator_method": self.calibrator_method,
                "parameters": dict(self.parameters), "source_hashes": dict(self.source_hashes),
                "metrics": dict(self.metrics), "labels": list(self.labels)}
        payload["artifact_sha256"] = _hash(payload)
        return payload

    @classmethod
    def from_dict(cls, raw):
        if not isinstance(raw, dict):
            raise ValueError("Unsupported or malformed calibration artifact.")
        allowed = {"schema_version", "task_id", "task_spec_sha256", "policy_id", "model_ref", "confidence_method",
                   "calibration_ref", "calibrator_method", "parameters", "source_hashes", "metrics", "labels",
                   "artifact_sha256"}
        if set(raw) != allowed or raw.get("schema_version") != 2:
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


def validate_calibration_request(trusted_labels, *, method, task, policy, model_ref, calibration_ref):
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


def fit_calibrator_from_partition(calibration_predictions, trusted_labels, *, method, frozen_partition,
                                  task=None, policy=None, model_ref=None, calibration_ref=None) -> CalibrationArtifact:
    """Fit confidence from a verified frozen partition supplied as values."""
    validate_calibration_request(trusted_labels, method=method, task=task, policy=policy,
                                 model_ref=model_ref, calibration_ref=calibration_ref)
    frozen = frozen_partition
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
                    "labeling_policy_sha256": labeling_policy_sha256(policy),
                    "calibration_manifest_sha256": frozen["manifest_sha256"],
                    "calibration_partition_sha256": frozen["partition_sha256"],
                    "calibration_dataset_sha256": frozen["dataset_sha256"],
                    "calibration_scores_sha256": scores_hash, "trusted_labels_sha256": labels_hash},
        {"brier_score": brier, "row_count": len(rows), "correct_count": int(sum(ys))},
        tuple(task.labels),
    )
