"""Training rules operate on values without project, model or filesystem access."""

from dataclasses import replace
import hashlib
import json

import pytest

from lazylabel.domain.labeling.task import LabelTask
from lazylabel.domain.labeling.policy import LabelingPolicy
from lazylabel.domain.labeling.prediction import Prediction
from lazylabel.domain.training.trusted_labels import TrustedLabelBatch, TrustedLabelRecord, TrustedLabelSourceSpec
from lazylabel.domain.training.quality import validate_trusted_batch
from lazylabel.domain.training.split import split_trusted_records
from lazylabel.domain.training.task_spec import task_spec_sha256
from lazylabel.domain.training.evaluation import (
    CalibrationArtifact, SUPPORTED_SCORE_METHOD, fit_calibrator_from_partition,
    labeling_policy_sha256, _fit_logistic,
)
from lazylabel.domain.training.promotion import PromotionPolicy, promotion_reasons, rollback_reasons
from lazylabel.domain.training.metrics import _derive_holdout_metrics


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), default=str).encode()).hexdigest()


def task():
    return LabelTask("risk", "classify", ("amount",), ("low", "high"), "local/model")


def policy():
    return PromotionPolicy("risk", "v1", {"accuracy": 0.5}, 0.5,
                           {"low": 0.1, "high": 0.1}, 0.2, {"accuracy": 0.7}, 2)


def batch():
    records = [TrustedLabelRecord(digest(i), {"amount": i}, "low" if i < 14 else "high",
                                 digest({"amount": i})) for i in range(28)]
    return TrustedLabelBatch("labels", "risk", "advisor-v1", "provided_ground_truth",
                             ("amount",), "class", records, "a" * 64)


def eligible():
    gates = policy()
    candidate = {"task_id": "risk", "candidate_id": "c1", "model_ref": "candidate-ref",
                 "status": "evaluated", "training_gate_sha256": "a" * 64,
                 "incumbent_model_ref": "incumbent-ref", "expected_active_model_ref": "incumbent-ref"}
    result = {"evaluator": "finlabel-local-transformers-peft-v1", "score_method": "label_json_mean_log_likelihood_v2",
              "task_id": "risk", "candidate_id": "c1", "candidate_model_ref": "candidate-ref",
              "incumbent_model_ref": "incumbent-ref", "policy_sha256": gates.policy_sha256,
              "training_gate_sha256": "a" * 64, "same_frozen_holdout": True,
              "holdout_sha256": "b" * 64, "holdout_dataset_sha256": "c" * 64,
              "dataset_manifest_sha256": "d" * 64, "holdout_count": 10,
              "coverage": 0.8, "calibration_error": 0.1,
              "trusted_label_provenance": {"source_name": "labels", "provenance_id": "advisor-v1",
                  "trust_kind": "provided_ground_truth", "snapshot_sha256": "e" * 64},
              "candidate_metrics": {"accuracy": 0.8}, "incumbent_metrics": {"accuracy": 0.7},
              "candidate_per_label": {"low": 0.8, "high": 0.8},
              "incumbent_per_label": {"low": 0.8, "high": 0.8}}
    return candidate, result, gates


def reasons(candidate, result, gates, evidence_reasons=()):
    result = dict(result)
    result["evaluation_sha256"] = digest(result)
    return promotion_reasons(candidate, result, gates, evidence_reasons=evidence_reasons)


def test_trusted_eligibility_and_tamper_detection():
    trusted = batch()
    assert validate_trusted_batch(trusted, task()) == {"low": 14, "high": 14}
    with pytest.raises(ValueError, match="cannot be trusted"):
        TrustedLabelSourceSpec("labels", "risk", "class", {"L": "low"}, "model-output", "provided_ground_truth")
    with pytest.raises(ValueError, match="stale or inconsistent"):
        validate_trusted_batch(replace(trusted, records=(replace(trusted.records[0], input_digest="0" * 64),)), task())
    with pytest.raises(ValueError, match="Insufficient trusted class coverage"):
        validate_trusted_batch(replace(trusted, records=trusted.records[:6]), task())


def test_split_is_stable_disjoint_and_preserves_class_coverage():
    records = batch().records
    first = split_trusted_records(records, task().labels)
    second = split_trusted_records(tuple(reversed(records)), task().labels)
    assert first == second
    groups = [{row.record_ref for row in getattr(first, name)} for name in ("train", "calibration", "holdout")]
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    assert set.union(*groups) == {row.record_ref for row in records}
    for partition in first.manifest["partitions"].values():
        assert min(partition["label_counts"].values()) >= 1


def test_task_and_policy_hashes_bind_contract_fields():
    original = task()
    assert task_spec_sha256(original) == digest({"task_id": "risk", "instructions": "classify",
        "input_columns": ["amount"], "labels": ["low", "high"], "model_id": "local/model", "model_revision": None})
    assert task_spec_sha256(replace(original, instructions="changed")) != task_spec_sha256(original)
    labeling = LabelingPolicy("risk-v1", "risk", ("low", "high"), "rules-v1", "cal-v1", 0.7, 30)
    assert labeling_policy_sha256(replace(labeling, min_calibrated_confidence=0.8)) != labeling_policy_sha256(labeling)
    assert replace(policy(), minimum_coverage=0.9, policy_sha256="").policy_sha256 != policy().policy_sha256


def test_calibration_fit_is_deterministic_and_rejects_insufficient_evidence():
    xs, ys = [-4., -3., -2., -1., -0.5, -0.2], [0., 1., 0., 1., 1., 0.]
    assert _fit_logistic(xs, ys) == _fit_logistic(xs, ys)
    with pytest.raises(ValueError, match="both correct and incorrect"):
        _fit_logistic(xs, [1.] * 6)
    with pytest.raises(ValueError, match="no usable variation"):
        _fit_logistic([1.] * 6, ys)


def calibration_values():
    labeling = LabelingPolicy("risk-v1", "risk", ("low", "high"), "rules-v1", "cal-v1", 0.7, 30)
    predictions, labels = [], {}
    cases = [("low", "low"), ("high", "high"), ("low", "high"),
             ("high", "low"), ("low", "low"), ("high", "low")]
    for index, (predicted, target) in enumerate(cases):
        ref, top = digest(index), -3.0 + index * 0.5
        scores = {label: top if label == predicted else top - 1.0 for label in task().labels}
        prediction = Prediction(predicted, None, scores, None, None, SUPPORTED_SCORE_METHOD, ref)
        predictions.append({"record_ref": ref, "prediction": prediction})
        labels[ref] = target
    frozen = {"task_spec_sha256": task_spec_sha256(task()), "manifest_sha256": "a" * 64,
              "partition_sha256": "b" * 64, "dataset_sha256": "c" * 64,
              "refs": tuple(labels), "labels": labels}
    return predictions, labels, {"method": SUPPORTED_SCORE_METHOD, "frozen_partition": frozen,
        "task": task(), "policy": labeling, "model_ref": "model-v1", "calibration_ref": "cal-v1"}


def test_calibration_fits_values_and_preserves_legacy_artifact_serialization(tmp_path):
    from lazylabel.training.evaluation import CalibrationArtifact as LocalCalibrationArtifact

    predictions, labels, options = calibration_values()
    artifact = fit_calibrator_from_partition(predictions, labels, **options)
    payload = artifact.to_dict()
    assert payload["schema_version"] == 2
    assert payload["labels"] == ["low", "high"]
    assert payload["metrics"]["row_count"] == 6
    assert payload["metrics"]["correct_count"] == 3
    assert 0 <= payload["metrics"]["brier_score"] <= 1
    assert CalibrationArtifact.from_dict(payload) == artifact
    local = LocalCalibrationArtifact.from_dict(payload)
    path = local.save(tmp_path / "calibration.json")
    assert LocalCalibrationArtifact.load(path).to_dict() == payload
    confidence = artifact.calibrate(predictions[0]["prediction"], task=options["task"],
        policy=options["policy"], model_ref=options["model_ref"]).confidence
    assert 0 <= confidence <= 1
    with pytest.raises(ValueError, match="identity does not match"):
        artifact.calibrate(predictions[0]["prediction"], task=options["task"],
            policy=options["policy"], model_ref="other-model")
    with pytest.raises(ValueError, match="integrity hash"):
        CalibrationArtifact.from_dict({**payload, "model_ref": "other-model"})


def test_calibration_rejects_partial_or_changed_frozen_evidence():
    predictions, labels, options = calibration_values()
    with pytest.raises(ValueError, match="identical record IDs"):
        fit_calibrator_from_partition(predictions[:-1], labels, **options)
    with pytest.raises(ValueError, match="differ from the frozen"):
        fit_calibrator_from_partition(predictions, {**labels, predictions[0]["record_ref"]: "high"}, **options)
    reduced = predictions[:-1]
    reduced_labels = {row["record_ref"]: labels[row["record_ref"]] for row in reduced}
    frozen = {**options["frozen_partition"], "labels": reduced_labels, "refs": tuple(reduced_labels)}
    with pytest.raises(ValueError, match="insufficient class coverage"):
        fit_calibrator_from_partition(reduced, reduced_labels, **{**options, "frozen_partition": frozen})


def test_promotion_requires_valid_policy_and_verified_external_evidence():
    candidate, result, gates = eligible()
    assert reasons(candidate, result, gates) == []
    assert reasons(candidate, result, gates, ("holdout_metric_evidence_invalid",)) == ["holdout_metric_evidence_invalid"]
    with pytest.raises(ValueError, match="Promotion policy"):
        reasons(candidate, result, None)
    assert "candidate_not_evaluated" in reasons({**candidate, "status": "failed"}, result, gates)


def test_promotion_rejects_tampered_evaluation_and_mutated_policy():
    candidate, result, gates = eligible()
    result["evaluation_sha256"] = digest(result)
    assert promotion_reasons(candidate, {**result, "coverage": 0.9}, gates, evidence_reasons=()) == [
        "evaluation_integrity_mismatch"]
    gates.required_metrics["accuracy"] = 0.9
    with pytest.raises(ValueError, match="invalid or changed"):
        promotion_reasons(candidate, result, gates, evidence_reasons=())


@pytest.mark.parametrize("updates, expected", [
    ({"same_frozen_holdout": False}, "holdout_provenance_missing"),
    ({"holdout_count": 1}, "holdout_count_below_minimum"),
    ({"candidate_metrics": {}}, "required_metric_failed:accuracy"),
    ({"candidate_metrics": {"accuracy": 0.6}}, "incumbent_comparison_missing_or_regressed:accuracy"),
    ({"coverage": 0.1}, "coverage_gate_failed"),
    ({"calibration_error": 0.9}, "calibration_gate_failed"),
    ({"candidate_per_label": {"low": 0.1, "high": 0.8}}, "per_label_regression_failed:low"),
])
def test_promotion_rejects_failed_or_insufficient_evaluation(updates, expected):
    candidate, result, gates = eligible()
    assert expected in reasons(candidate, {**result, **updates}, gates)


def test_rollback_limits_preserve_direction_and_reject_missing_metrics():
    gates = replace(policy(), rollback_monitor_limits={"accuracy": 0.7, "brier_score": 0.2}, policy_sha256="")
    assert rollback_reasons({"accuracy": 0.8, "brier_score": 0.1}, gates) == []
    assert rollback_reasons({"accuracy": 0.2, "brier_score": 0.3}, gates) == [
        "rollback_limit_violated:accuracy", "rollback_limit_violated:brier_score"]
    with pytest.raises(ValueError, match="health_metric_missing_or_invalid"):
        rollback_reasons({}, gates)


def test_holdout_metrics_include_abstentions_and_enforce_threshold():
    rows = [{"record_ref": "a" * 64, "input_digest": "b" * 64, "target": "low", "prediction": "low",
             "scores": {"low": 0.9, "high": 0.1}, "confidence": 0.8, "applied": True, "reason_code": None},
            {"record_ref": "c" * 64, "input_digest": "d" * 64, "target": "high", "prediction": None,
             "scores": None, "confidence": None, "applied": False, "reason_code": "backend_error"}]
    derived = _derive_holdout_metrics(rows, task().labels, 0.7)
    assert derived["metrics"]["accuracy"] == derived["metrics"]["coverage"] == 0.5
    assert derived["per_label"]["high"]["recall"] == 0.0
    with pytest.raises(ValueError, match="applied_flag_mismatches_threshold"):
        _derive_holdout_metrics(rows, task().labels, 0.9)
