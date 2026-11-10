"""Pure labeling rules keep decisions separate from local effects."""

import pytest
from types import SimpleNamespace
import lazylabel.domain.labeling.outcomes as outcome_values

from lazylabel.domain.labeling import (
    LabelOutcome, LabelTask, LabelingPolicy, Prediction, PredictionError,
    choose_quarantine_reason, parse_suggestion, policy_matches_task, rules_match,
    policy_from_dict, task_from_dict, validate_calibration, validate_label,
)


def task():
    return LabelTask("risk", "Classify", ("amount",), ("low", "high"), "model")


def policy(**overrides):
    fields = dict(policy_id="risk-v1", task_id="risk", allowed_labels=("low", "high"),
                  rules_version="1", calibration_ref="cal-v1", min_calibrated_confidence=0.8,
                  max_staleness_seconds=30,
                  rules=({"field": "amount", "operator": "number_between", "minimum": 0},))
    fields.update(overrides)
    return LabelingPolicy(**fields)


def test_task_and_prediction_reject_invalid_values():
    with pytest.raises(ValueError, match="unique"):
        task_from_dict(dict(task_id="risk", instructions="Classify", input_columns=["amount"],
                            labels=["low", "low"], model_id="model"))
    with pytest.raises(ValueError, match="unknown source"):
        task_from_dict(dict(task_id="risk", instructions="Classify", input_columns=["amount"],
                            labels=["low"], model_id="model"), available_columns=["private"])
    with pytest.raises(ValueError, match="not configured"):
        validate_label(task(), "private")
    with pytest.raises(ValueError, match="confidence_method"):
        Prediction("low", None, {"low": 0.7}, None, None, None, "a" * 64)
    with pytest.raises(ValueError, match="calibrated_confidence"):
        Prediction("low", None, {"low": 0.7}, 1.2, "cal-v1", "scores", "a" * 64)


def test_prediction_parser_and_policy_fail_closed():
    assert parse_suggestion('{"label":"low"}', valid_labels=task().labels) == ("low", None)
    with pytest.raises(PredictionError) as error:
        parse_suggestion('{"label":"private"}', valid_labels=task().labels)
    assert error.value.reason_code == "unknown_label"
    assert policy_matches_task(policy(), task())
    assert not policy_matches_task(policy(allowed_labels=("low",)), task())
    assert not policy_matches_task(policy(rules=()), task())
    assert rules_match(policy().rules, {"amount": "10"})
    assert not rules_match(policy().rules, {"amount": "-1"})


def test_policy_document_validation_has_no_file_dependency():
    raw = dict(policy_id="risk-v1", task_id="risk", allowed_labels=["low", "high"],
               rules_version="1", calibration_ref="cal-v1", min_calibrated_confidence=0.8,
               max_staleness_seconds=30,
               rules=[{"field": "amount", "operator": "number_between", "minimum": 0}])
    assert policy_from_dict(raw, task=task()).policy_id == "risk-v1"
    with pytest.raises(ValueError, match="Unknown labeling policy field"):
        policy_from_dict({**raw, "private": "data"}, task=task())
    with pytest.raises(ValueError, match="not selected"):
        policy_from_dict({**raw, "rules": [{"field": "private", "operator": "not_empty"}]}, task=task())


@pytest.mark.parametrize("label,confidence,elapsed,reason", [
    ("low", 0.9, 1, None), ("low", None, 1, "uncalibrated"),
    ("low", 0.7, 1, "below_threshold"), ("private", 0.9, 1, "unknown_label"),
    ("low", 0.9, 31, "stale_source"),
    ("low", float("nan"), 1, "uncalibrated"),
    ("low", True, 1, "uncalibrated"),
])
def test_confidence_and_quarantine_decision(label, confidence, elapsed, reason):
    assert choose_quarantine_reason(task(), policy(), label, confidence, elapsed) == reason


def test_outcome_rejects_private_reason_text():
    with pytest.raises(ValueError, match="reason_code"):
        LabelOutcome("a" * 32, "b" * 64, "c" * 64, "risk", "risk-v1", "model",
                     None, "quarantined", "raw private value", None, "2026-10-26T00:00:00Z")


def test_domain_outcomes_do_not_create_timestamps():
    assert not hasattr(outcome_values, "utc_now")


def test_calibration_evidence_requires_matching_provenance_and_finite_score():
    prediction = Prediction("low", None, {"low": 0.8, "high": 0.2}, None, None,
                            "scores", "a" * 64)
    result = SimpleNamespace(task_id="risk", policy_id="risk-v1", model_ref="model",
                             confidence_method="scores", calibration_ref="cal-v1", confidence=0.9)
    assert validate_calibration(result, prediction, task(), policy(), "model") == 0.9
    assert validate_calibration(SimpleNamespace(**{**vars(result), "policy_id": "other"}),
                                prediction, task(), policy(), "model") is None
    assert validate_calibration(SimpleNamespace(**{**vars(result), "confidence": float("nan")}),
                                prediction, task(), policy(), "model") is None
