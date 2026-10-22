"""Calibration artifacts bound to trusted labels and one exact inference identity."""

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


SUPPORTED_SCORE_METHOD = "label_json_mean_log_likelihood_v2"
CALIBRATOR_METHOD = "platt_top_score_v1"


def _hash(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


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
    policy_id: str
    model_ref: str
    confidence_method: str
    calibration_ref: str
    calibrator_method: str
    parameters: Mapping[str, float]
    source_hashes: Mapping[str, str]
    metrics: Mapping[str, float]
    labels: tuple

    def calibrate(self, prediction, *, task, policy, model_ref):
        if (task.task_id != self.task_id or policy.policy_id != self.policy_id or model_ref != self.model_ref
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
        return {"schema_version": 1, "task_id": self.task_id, "policy_id": self.policy_id,
                "model_ref": self.model_ref, "confidence_method": self.confidence_method,
                "calibration_ref": self.calibration_ref, "calibrator_method": self.calibrator_method,
                "parameters": dict(self.parameters), "source_hashes": dict(self.source_hashes),
                "metrics": dict(self.metrics), "labels": list(self.labels)}

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
        raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        allowed = {"schema_version", "task_id", "policy_id", "model_ref", "confidence_method",
                   "calibration_ref", "calibrator_method", "parameters", "source_hashes", "metrics", "labels"}
        if set(raw) != allowed or raw.get("schema_version") != 1:
            raise ValueError("Unsupported or malformed calibration artifact.")
        return cls(raw["task_id"], raw["policy_id"], raw["model_ref"], raw["confidence_method"],
                   raw["calibration_ref"], raw["calibrator_method"], raw["parameters"],
                   raw["source_hashes"], raw["metrics"], tuple(raw["labels"]))


def fit_calibrator(calibration_predictions, trusted_labels, *, method,
                   task=None, policy=None, model_ref=None, calibration_ref=None) -> CalibrationArtifact:
    """Fit Platt confidence for correctness from held-out calibration scores and trusted targets.

    `calibration_predictions` is [{record_ref, prediction: Prediction}, ...]; trusted_labels is
    a mapping of the exact same record_ref values to labels (or equivalent records). Identity
    keywords are mandatory for an artifact usable by the autonomous labeling service.
    """
    if method != SUPPORTED_SCORE_METHOD:
        raise ValueError("Unsupported raw score method; expected {}.".format(SUPPORTED_SCORE_METHOD))
    if task is None or policy is None or not model_ref or not isinstance(calibration_ref, str) or not calibration_ref.strip():
        raise ValueError("Calibration requires exact task, policy, model_ref, and calibration_ref identities.")
    if policy.task_id != task.task_id or set(policy.allowed_labels) != set(task.labels):
        raise ValueError("Calibration policy must match the task and its exact label taxonomy.")
    if policy.calibration_ref != calibration_ref:
        raise ValueError("Calibration reference must match the task policy configuration.")
    rows = _records(calibration_predictions, trusted_labels)
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
        task.task_id, policy.policy_id, model_ref, method, calibration_ref, CALIBRATOR_METHOD,
        parameters, {"calibration_scores_sha256": scores_hash, "trusted_labels_sha256": labels_hash},
        {"brier_score": brier, "row_count": float(len(rows)), "correct_count": float(sum(ys))},
        tuple(task.labels),
    )
