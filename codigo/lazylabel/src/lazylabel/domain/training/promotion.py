"""Promotion policy values and deterministic promotion/rollback gates."""

import re
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from lazylabel.domain.training.metrics import _digest, _finite

_SHA = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PromotionPolicy:
    task_id: str
    version: str
    required_metrics: Mapping[str, float]
    minimum_coverage: float
    allowed_per_label_regression: Mapping[str, float]
    max_calibration_error: float
    rollback_monitor_limits: Mapping[str, float]
    min_holdout_count: int
    policy_sha256: str = ""

    def __post_init__(self):
        if not self.task_id or not self.version:
            raise ValueError("Promotion policy requires task_id and version.")
        if not self.required_metrics or not self.allowed_per_label_regression or not self.rollback_monitor_limits:
            raise ValueError("Promotion policy required metrics, per-label limits, and rollback limits are mandatory.")
        for group in (self.required_metrics, self.allowed_per_label_regression, self.rollback_monitor_limits):
            if not isinstance(group, Mapping) or not group or any(not isinstance(k, str) or not k or not _finite(v) for k, v in group.items()):
                raise ValueError("Promotion policy metric gates must be non-empty finite numeric mappings.")
        if not _finite(self.minimum_coverage) or not 0 <= self.minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be between 0 and 1.")
        if not _finite(self.max_calibration_error) or not 0 <= self.max_calibration_error <= 1:
            raise ValueError("max_calibration_error must be between 0 and 1.")
        if isinstance(self.min_holdout_count, bool) or not isinstance(self.min_holdout_count, int) or self.min_holdout_count < 1:
            raise ValueError("min_holdout_count must be a positive integer.")
        expected = self.sha256_payload()
        if self.policy_sha256 and self.policy_sha256 != expected:
            raise ValueError("Promotion policy digest does not match its configured gates.")
        object.__setattr__(self, "policy_sha256", expected)

    def sha256_payload(self):
        return _digest({"task_id": self.task_id, "version": self.version,
                        "required_metrics": dict(self.required_metrics), "minimum_coverage": self.minimum_coverage,
                        "allowed_per_label_regression": dict(self.allowed_per_label_regression),
                        "max_calibration_error": self.max_calibration_error,
                        "rollback_monitor_limits": dict(self.rollback_monitor_limits),
                        "min_holdout_count": self.min_holdout_count})

    @classmethod
    def from_dict(cls, raw, *, task_id):
        if not isinstance(raw, dict) or set(raw) != {"task_id", "version", "required_metrics", "minimum_coverage",
            "allowed_per_label_regression", "max_calibration_error", "rollback_monitor_limits", "min_holdout_count"}:
            raise ValueError("Promotion policy must define exactly every required task gate.")
        if raw["task_id"] != task_id:
            raise ValueError("Promotion policy task_id does not match.")
        return cls(**raw)


@dataclass(frozen=True)
class PromotionEvent:
    event_id: str
    candidate_id: str
    evaluation_id: str
    task_id: str
    action: str
    reason_codes: Sequence[str]
    previous_model_ref: Optional[str]
    active_model_ref: Optional[str]
    policy_sha256: str
    evaluation_sha256: str
    created_at: str


def promotion_reasons(candidate, result, policy, *, evidence_reasons):
    """Decide gates after the caller supplies artifact/holdout verification failures.

    The caller must verify frozen files and report failures in evidence_reasons;
    an empty sequence means those external checks passed.
    """
    if not isinstance(policy, PromotionPolicy) or policy.sha256_payload() != policy.policy_sha256:
        raise ValueError("Promotion policy is invalid or changed after configuration.")
    reasons = list(evidence_reasons)
    # This is a format/version check, not an authenticated evaluator identity.
    if result.get("evaluator") != "finlabel-local-transformers-peft-v1":
        reasons.append("unsupported_evaluator_contract")
    unsigned = dict(result)
    recorded = unsigned.pop("evaluation_sha256", None)
    if not isinstance(recorded, str) or _digest(unsigned) != recorded:
        reasons.append("evaluation_integrity_mismatch")
    if result.get("score_method") != "label_json_mean_log_likelihood_v2":
        reasons.append("unsupported_score_evidence")
    if (not isinstance(candidate.get("training_gate_sha256"), str)
            or not _SHA.fullmatch(candidate["training_gate_sha256"])
            or result.get("training_gate_sha256") != candidate.get("training_gate_sha256")):
        reasons.append("training_gate_evidence_missing_or_mismatched")
    if candidate.get("task_id") != policy.task_id or result.get("task_id") != policy.task_id:
        reasons.append("task_identity_mismatch")
    if candidate.get("status") != "evaluated":
        reasons.append("candidate_not_evaluated")
    if result.get("candidate_id") != candidate.get("candidate_id"):
        reasons.append("candidate_evaluation_mismatch")
    if result.get("policy_sha256") != policy.policy_sha256:
        reasons.append("policy_changed_or_mismatched")
    if (not result.get("same_frozen_holdout") or not _SHA.fullmatch(str(result.get("holdout_sha256", "")))
            or not _SHA.fullmatch(str(result.get("holdout_dataset_sha256", "")))
            or not _SHA.fullmatch(str(result.get("dataset_manifest_sha256", "")))):
        reasons.append("holdout_provenance_missing")
    holdout_count = result.get("holdout_count")
    if isinstance(holdout_count, bool) or not isinstance(holdout_count, int) or holdout_count < 0:
        reasons.append("holdout_count_invalid")
    elif holdout_count < policy.min_holdout_count:
        reasons.append("holdout_count_below_minimum")
    if not result.get("trusted_label_provenance"):
        reasons.append("trusted_label_provenance_missing")
    if result.get("candidate_model_ref") != candidate.get("model_ref"):
        reasons.append("candidate_model_provenance_mismatch")
    if result.get("candidate_id") != candidate.get("candidate_id"):
        reasons.append("candidate_evaluation_mismatch")
    if not isinstance(result.get("incumbent_model_ref"), str) or not result["incumbent_model_ref"]:
        reasons.append("incumbent_model_provenance_mismatch")
    previous = candidate.get("incumbent_model_ref")
    if previous is None or result.get("incumbent_model_ref") != previous:
        reasons.append("incumbent_model_mismatch")
    active_record = candidate.get("expected_active_model_ref")
    if result.get("incumbent_model_ref") != (active_record or previous):
        reasons.append("incumbent_model_mismatch")
    provenance = result.get("trusted_label_provenance")
    if (not isinstance(provenance, Mapping)
            or not all(isinstance(provenance.get(field), str) and provenance[field]
                       for field in ("source_name", "provenance_id", "trust_kind"))
            or not _SHA.fullmatch(str(provenance.get("snapshot_sha256", "")))):
        reasons.append("trusted_label_provenance_invalid")
    coverage = result.get("coverage")
    if not _finite(coverage) or coverage < policy.minimum_coverage:
        reasons.append("coverage_gate_failed")
    calibration_error = result.get("calibration_error")
    if not _finite(calibration_error) or calibration_error > policy.max_calibration_error:
        reasons.append("calibration_gate_failed")
    candidate_metrics = result.get("candidate_metrics", {})
    incumbent_metrics = result.get("incumbent_metrics", {})
    for metric, minimum in policy.required_metrics.items():
        value = candidate_metrics.get(metric)
        if not _finite(value) or value < minimum:
            reasons.append("required_metric_failed:{}".format(metric))
        old = incumbent_metrics.get(metric)
        if old is None or not _finite(old) or _finite(value) and value < old:
            reasons.append("incumbent_comparison_missing_or_regressed:{}".format(metric))
    candidate_labels = result.get("candidate_per_label", {})
    incumbent_labels = result.get("incumbent_per_label", {})
    for label, allowance in policy.allowed_per_label_regression.items():
        current, old = candidate_labels.get(label), incumbent_labels.get(label)
        if not _finite(current) or not _finite(old) or old - current > allowance:
            reasons.append("per_label_regression_failed:{}".format(label))
    return sorted(set(reasons))


def rollback_reasons(recomputed, policy):
    reasons = []
    for metric, limit in policy.rollback_monitor_limits.items():
        value = recomputed.get(metric)
        if metric not in {"accuracy", "macro_f1", "coverage", "brier_score", "calibration_error"}:
            raise ValueError("health_metric_unsupported:{}".format(metric))
        if not _finite(value):
            raise ValueError("health_metric_missing_or_invalid:{}".format(metric))
        violated = value > limit if metric in {"brier_score", "calibration_error"} else value < limit
        if violated:
            reasons.append("rollback_limit_violated:{}".format(metric))
    return reasons
