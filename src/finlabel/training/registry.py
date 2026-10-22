"""Append-only local candidate registry and fail-closed automatic promotion."""

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional, Sequence


_SHA = re.compile(r"^[0-9a-f]{64}$")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), default=str).encode()).hexdigest()


def _finite(value):
    import math
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value))


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
    def load(cls, path, *, task_id):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
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


class ModelRegistry:
    """Small local state store. Events append; active pointer is atomically replaced."""
    def __init__(self, workspace_dir):
        self.root = Path(workspace_dir).expanduser().resolve() / "models"
        self.root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.root / "registry-events.jsonl"
        self.active_path = self.root / "active-models.json"
        self.candidates_path = self.root / "candidates.json"

    def _read(self, path, default):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default

    def active(self, task_id):
        return self._read(self.active_path, {}).get(task_id)

    def candidate(self, candidate_id):
        value = self._read(self.candidates_path, {}).get(candidate_id)
        if value is None:
            raise KeyError("Unknown candidate ID.")
        return value

    def transition(self, candidate_id, state, **fields):
        candidates = self._read(self.candidates_path, {})
        value = candidates.get(candidate_id)
        if value is None:
            raise KeyError("Unknown candidate ID.")
        allowed = {"queued": {"training", "rejected"}, "training": {"evaluated", "rejected"},
                   "evaluated": {"promoted", "rejected"}, "promoted": set(), "rejected": set()}
        if state not in allowed.get(value["status"], set()):
            raise ValueError("Invalid candidate state transition: {} -> {}.".format(value["status"], state))
        value.update(fields); value["status"] = state
        self._write_atomic(self.candidates_path, candidates)

    def create_candidate(self, candidate_id, payload):
        candidates = self._read(self.candidates_path, {})
        if candidate_id in candidates:
            return candidates[candidate_id]
        value = dict(payload); value.update({"candidate_id": candidate_id, "status": "queued"})
        candidates[candidate_id] = value
        self._write_atomic(self.candidates_path, candidates)
        return value

    def _write_atomic(self, path, value):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    def promote_if_eligible(self, candidate_id, evaluation_id, policy):
        if not isinstance(policy, PromotionPolicy) or policy.sha256_payload() != policy.policy_sha256:
            raise ValueError("Promotion policy is invalid or changed after configuration.")
        candidate = self.candidate(candidate_id)
        evaluation_path = self.root / "evaluations" / (evaluation_id + ".json")
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        evaluation_hash = hashlib.sha256(evaluation_path.read_bytes()).hexdigest()
        if candidate["status"] in {"promoted", "rejected"}:
            events = self._read_events()
            prior = next((row for row in events if row["candidate_id"] == candidate_id and row["evaluation_id"] == evaluation_id), None)
            if prior:
                return PromotionEvent(**prior)
            raise ValueError("Terminal candidate already has a different promotion decision.")
        if candidate.get("status") != "evaluated":
            reasons = ["candidate_not_evaluated"]
            previous = self.active(policy.task_id)
            evaluation_hash = hashlib.sha256(evaluation_path.read_bytes()).hexdigest()
            event_id = _digest({"candidate_id": candidate_id, "evaluation_id": evaluation_id,
                                "policy_sha256": policy.policy_sha256, "evaluation_sha256": evaluation_hash})
            event = PromotionEvent(event_id, candidate_id, evaluation_id, policy.task_id, "reject", tuple(reasons),
                                   previous.get("model_ref") if previous else None,
                                   previous.get("model_ref") if previous else None, policy.policy_sha256,
                                   evaluation_hash, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")
            self.transition(candidate_id, "rejected", decision_event_id=event_id, rejection_reasons=reasons)
            return event
        reasons = _promotion_reasons(candidate, evaluation, policy)
        previous = self.active(policy.task_id)
        action = "promote" if not reasons else "reject"
        new_active = {"model_ref": candidate["model_ref"]} if action == "promote" else previous
        event_id = _digest({"candidate_id": candidate_id, "evaluation_id": evaluation_id,
                            "policy_sha256": policy.policy_sha256, "evaluation_sha256": evaluation_hash})
        event = PromotionEvent(event_id, candidate_id, evaluation_id, policy.task_id, action,
                               tuple(reasons), previous.get("model_ref") if previous else None,
                               new_active.get("model_ref") if new_active else None, policy.policy_sha256,
                               evaluation_hash, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), sort_keys=True) + "\n")
        if action == "promote":
            active = self._read(self.active_path, {})
            active[policy.task_id] = {"model_ref": candidate["model_ref"],
                                      "previous_model_ref": previous.get("model_ref") if previous else None,
                                      "candidate_id": candidate_id, "evaluation_id": evaluation_id}
            self._write_atomic(self.active_path, active)
            self.transition(candidate_id, "promoted", decision_event_id=event_id)
        else:
            self.transition(candidate_id, "rejected", decision_event_id=event_id, rejection_reasons=reasons)
        return event

    def _read_events(self):
        if not self.events_path.exists():
            return []
        return [json.loads(line) for line in self.events_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def rollback_if_unhealthy(self, task_id, health_evaluation):
        active = self.active(task_id)
        if not active or not active.get("previous_model_ref"):
            return None
        policy = PromotionPolicy.load(self.root / "promotion-policies" / (task_id + ".json"), task_id=task_id)
        if not isinstance(health_evaluation, Mapping):
            raise ValueError("Health evaluation requires configured metric evidence.")
        metrics = health_evaluation.get("metrics", {})
        if not isinstance(metrics, Mapping):
            raise ValueError("Health evaluation requires configured metric evidence.")
        reasons = ["rollback_gate_failed:{}".format(name) for name, minimum in policy.rollback_monitor_limits.items()
                   if name not in metrics or not _finite(metrics[name]) or metrics[name] < minimum]
        if not reasons:
            return None
        digest = _digest(health_evaluation)
        pointer = {"model_ref": active["previous_model_ref"], "previous_model_ref": None,
                   "rollback_from": active["model_ref"], "health_sha256": digest}
        current = self._read(self.active_path, {})
        current[task_id] = pointer
        self._write_atomic(self.active_path, current)
        event = {"event_id": _digest({"task_id": task_id, "health_sha256": digest}), "task_id": task_id,
                 "action": "rollback", "reason_codes": reasons, "active_model_ref": pointer["model_ref"],
                 "health_sha256": digest, "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
        return event


def _promotion_reasons(candidate, result, policy):
    reasons = []
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
    if result.get("holdout_count", 0) < policy.min_holdout_count:
        reasons.append("holdout_count_below_minimum")
    if not result.get("trusted_label_provenance"):
        reasons.append("trusted_label_provenance_missing")
    if result.get("candidate_model_ref") != candidate.get("model_ref"):
        reasons.append("candidate_model_provenance_mismatch")
    if not isinstance(result.get("incumbent_model_ref"), str) or not result["incumbent_model_ref"]:
        reasons.append("incumbent_model_provenance_mismatch")
    previous = candidate.get("incumbent_model_ref")
    if previous is None or result.get("incumbent_model_ref") != previous:
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
