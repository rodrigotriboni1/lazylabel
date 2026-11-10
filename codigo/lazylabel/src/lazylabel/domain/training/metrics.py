"""Evaluation mathematics and deterministic evidence validation."""

import hashlib
import json
import re
from typing import Mapping

_SHA = re.compile(r"^[0-9a-f]{64}$")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), default=str).encode()).hexdigest()


def _finite(value):
    import math
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value))


def _metrics_equal(left, right):
    if not isinstance(left, Mapping) or set(left) != set(right):
        return False
    return all(_finite(left.get(key)) and abs(left[key] - value) <= 1e-12
               for key, value in right.items())


def _derive_holdout_metrics(rows, labels, threshold):
    """Recompute gates from privacy-minimized per-row target/prediction evidence."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("holdout_rows_missing")
    allowed_reasons = {None, "below_threshold", "rule_conflict", "invalid_input", "unknown_label",
                       "invalid_output", "backend_error", "calibration_error", "stale_source"}
    abstain = "__lazylabel_abstain__"
    while abstain in labels:
        abstain += "_"
    confusion = {label: {guess: 0 for guess in (*labels, abstain)} for label in labels}
    correct, confidences, canonical_rows = [], [], []
    seen = set()
    applied_count = 0
    for row in rows:
        expected_fields = {"record_ref", "input_digest", "target", "prediction", "scores", "confidence", "applied", "reason_code"}
        if not isinstance(row, Mapping) or set(row) != expected_fields:
            raise ValueError("malformed_holdout_row")
        ref, input_digest, target, predicted = (row["record_ref"], row["input_digest"],
                                                row["target"], row["prediction"])
        confidence, reason = row["confidence"], row["reason_code"]
        if (not isinstance(ref, str) or not _SHA.fullmatch(ref) or ref in seen
                or not isinstance(input_digest, str) or not _SHA.fullmatch(input_digest) or target not in labels
                or predicted is not None and predicted not in labels or reason not in allowed_reasons):
            raise ValueError("invalid_holdout_row_identity_or_label")
        seen.add(ref)
        if predicted is None:
            if (row["scores"] is not None or confidence is not None or row["applied"] is not False
                    or reason not in {"rule_conflict", "invalid_input", "unknown_label", "invalid_output",
                                      "backend_error", "calibration_error"}):
                raise ValueError("abstention_has_prediction_evidence")
            guess = abstain
            correct.append(0.0)
            applied = False
        else:
            if reason not in {None, "below_threshold", "stale_source"}:
                raise ValueError("prediction_reason_code_invalid")
            scores = row["scores"]
            if (not isinstance(scores, Mapping) or set(scores) != set(labels)
                    or any(not _finite(value) for value in scores.values())
                    or not _finite(confidence) or not 0 <= confidence <= 1):
                raise ValueError("prediction_score_evidence_invalid")
            expected_applied = reason is None and confidence >= threshold
            if row["applied"] is not expected_applied:
                raise ValueError("applied_flag_mismatches_threshold")
            if reason == "below_threshold" and confidence >= threshold:
                raise ValueError("threshold_reason_mismatch")
            if reason is None and confidence < threshold:
                raise ValueError("threshold_reason_mismatch")
            guess = predicted
            correct.append(float(predicted == target))
            confidences.append((confidence, float(predicted == target)))
            applied = expected_applied
        confusion[target][guess] += 1
        applied_count += int(applied)
        canonical_rows.append({"record_ref": ref, "input_digest": input_digest,
            "target": target, "prediction": predicted,
            "scores": ({label: row["scores"][label] for label in labels}
                       if row["scores"] is not None else None),
            "confidence": confidence, "applied": applied, "reason_code": reason})
    total = len(rows)
    per_label, f1s = {}, []
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[truth][label] for truth in labels if truth != label)
        fn = sum(confusion[label][guess] for guess in (*labels, abstain) if guess != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
        f1s.append(f1)
    accuracy = sum(correct) / total
    brier = sum((confidence - outcome) ** 2 for confidence, outcome in confidences) / len(confidences) if confidences else 1.0
    ece = 0.0
    if confidences:
        for index in range(10):
            bucket = [(confidence, outcome) for confidence, outcome in confidences
                      if index / 10 <= confidence < ((index + 1) / 10 if index < 9 else 1.0000001)]
            if bucket:
                ece += len(bucket) / len(confidences) * abs(
                    sum(outcome for _, outcome in bucket) / len(bucket)
                    - sum(confidence for confidence, _ in bucket) / len(bucket))
    metrics = {"accuracy": accuracy, "macro_f1": sum(f1s) / len(f1s), "brier_score": brier,
               "calibration_error": ece if confidences else 1.0, "coverage": applied_count / total}
    record_digest = _digest(canonical_rows)
    return {"metrics": metrics, "per_label": per_label,
            "per_label_f1": {label: values["f1"] for label, values in per_label.items()},
            "confusion": confusion, "records_sha256": record_digest}


def _metrics(scored, calibrator, task, policy, model_ref):
    abstain = "__lazylabel_abstain__"
    while abstain in task.labels:
        abstain += "_"
    confusion = {label: {other: 0 for other in (*task.labels, abstain)} for label in task.labels}
    confidences, correct = [], []
    for row in scored:
        pred, target = row["prediction"], row["target"]
        if pred is None:
            confusion[target][abstain] += 1
            row["applied"] = False
            row["confidence"] = None
            continue
        try:
            confidence = calibrator.calibrate(pred, task=task, policy=policy, model_ref=model_ref).confidence
        except Exception:
            row["prediction"] = None
            row["reason_code"] = "calibration_error"
            row["applied"] = False
            row["confidence"] = None
            confusion[target][abstain] += 1
            continue
        confusion[target][pred.label] += 1
        confidences.append(confidence)
        is_correct = float(pred.label == target)
        correct.append(is_correct)
        if row["reason_code"] is None and confidence >= policy.min_calibrated_confidence:
            row["applied"] = True
            row["reason_code"] = None
        elif row["reason_code"] is None:
            row["reason_code"] = "below_threshold"
        row["confidence"] = confidence
    total = len(scored)
    per_label, f1s = {}, []
    for label in task.labels:
        tp = confusion[label][label]
        fp = sum(confusion[truth][label] for truth in task.labels if truth != label)
        fn = sum(confusion[label][guess] for guess in (*task.labels, abstain) if guess != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
        f1s.append(f1)
    accuracy = sum(correct) / total
    brier = sum((p - y) ** 2 for p, y in zip(confidences, correct)) / len(correct) if correct else 1.0
    ece = 0.0
    for index in range(10):
        bucket = [(p, y) for p, y in zip(confidences, correct)
                  if index / 10 <= p < ((index + 1) / 10 if index < 9 else 1.0000001)]
        if bucket:
            ece += len(bucket) / len(confidences) * abs(sum(y for _, y in bucket) / len(bucket) -
                                               sum(p for p, _ in bucket) / len(bucket))
    coverage = sum(bool(row["applied"]) for row in scored) / total
    return ({"accuracy": accuracy, "macro_f1": sum(f1s) / len(f1s), "brier_score": brier,
             "calibration_error": ece if correct else 1.0, "coverage": coverage}, per_label, confusion)
