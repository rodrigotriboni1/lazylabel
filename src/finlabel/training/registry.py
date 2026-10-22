"""Append-only local candidate registry and fail-closed automatic promotion."""

import hashlib
import json
import os
import re
import tempfile
import fcntl
from contextlib import contextmanager
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
        self.lock_path = self.root / "registry.lock"
        self._recover()

    @contextmanager
    def _locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

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
        with self._locked():
            self._recover_unlocked()
            return self._transition_unlocked(candidate_id, state, **fields)

    def _transition_unlocked(self, candidate_id, state, **fields):
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
        with self._locked():
            self._recover_unlocked()
            candidates = self._read(self.candidates_path, {})
            if candidate_id in candidates:
                return candidates[candidate_id]
            value = dict(payload); value.update({"candidate_id": candidate_id, "status": "queued"})
            candidates[candidate_id] = value
            self._write_atomic(self.candidates_path, candidates)
            return value

    def _write_atomic(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
            self._fsync_dir(path.parent)
        finally:
            try: os.unlink(temporary)
            except FileNotFoundError: pass

    def _append_event(self, event):
        self._validate_event(event)
        existing = self._read_events()
        if any(row.get("event_id") == event.get("event_id") for row in existing):
            return
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")
            handle.flush(); os.fsync(handle.fileno())
        self._fsync_dir(self.events_path.parent)

    @staticmethod
    def _fsync_dir(path):
        descriptor = os.open(path, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)

    @staticmethod
    def _validate_event(event):
        if not isinstance(event, dict):
            raise ValueError("Registry journal entry must be an object.")
        action = event.get("action")
        promote_fields = {"event_id", "candidate_id", "evaluation_id", "task_id", "action", "reason_codes",
                          "previous_model_ref", "active_model_ref", "policy_sha256", "evaluation_sha256", "created_at"}
        rollback_fields = {"event_id", "task_id", "action", "reason_codes", "active_model_ref", "rollback_from",
                           "health_sha256", "evaluation_id", "candidate_id", "policy_sha256", "created_at"}
        expected = rollback_fields if action == "rollback" else promote_fields
        if action not in {"promote", "reject", "rollback"} or set(event) != expected:
            raise ValueError("Registry journal entry has an invalid schema.")
        for key in ("event_id", "task_id", "created_at", "action"):
            if not isinstance(event.get(key), str) or not event[key]:
                raise ValueError("Registry journal entry has a missing identity field.")
        if (not isinstance(event["reason_codes"], (list, tuple))
                or any(not isinstance(reason, str) or not reason for reason in event["reason_codes"])):
            raise ValueError("Registry journal reason codes are malformed.")
        hash_fields = ["health_sha256"] if action == "rollback" else ["policy_sha256", "evaluation_sha256"]
        if any(not isinstance(event.get(key), str) or not _SHA.fullmatch(event[key]) for key in hash_fields):
            raise ValueError("Registry journal hashes are malformed.")
        identity_fields = (("rollback_from", "active_model_ref", "evaluation_id", "candidate_id") if action == "rollback"
                           else ("candidate_id", "evaluation_id") + (("active_model_ref",) if action == "promote" else ()))
        if any(not isinstance(event.get(key), str) or not event[key] for key in identity_fields):
            raise ValueError("Registry journal model or candidate identity is malformed.")
        if action != "rollback" and event.get("previous_model_ref") is not None and not isinstance(event["previous_model_ref"], str):
            raise ValueError("Registry journal previous model reference is malformed.")
        if action == "reject" and event.get("active_model_ref") is not None and not isinstance(event["active_model_ref"], str):
            raise ValueError("Registry journal active model reference is malformed.")
        if action == "rollback" and (not isinstance(event.get("policy_sha256"), str)
                                       or not _SHA.fullmatch(event["policy_sha256"])):
            raise ValueError("Rollback journal policy digest is malformed.")
        payload = {key: value for key, value in event.items() if key not in {"event_id", "created_at"}}
        if event["event_id"] != _digest(payload):
            raise ValueError("Registry journal event digest is invalid.")

    def _repair_and_read_events(self):
        if not self.events_path.exists():
            return []
        data = self.events_path.read_bytes()
        chunks = data.splitlines(keepends=True)
        valid, offset = [], 0
        for index, chunk in enumerate(chunks):
            final = index == len(chunks) - 1
            complete = chunk.endswith(b"\n")
            if final and not complete:
                # A final unterminated fragment is the only recoverable journal damage.
                with self.events_path.open("r+b") as handle:
                    handle.truncate(offset); handle.flush(); os.fsync(handle.fileno())
                break
            try:
                row = json.loads(chunk.decode("utf-8"))
                self._validate_event(row)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, TypeError):
                raise ValueError("Registry journal contains a malformed non-trailing entry.")
            valid.append(row)
            offset += len(chunk)
        return valid

    def _recover(self):
        """Replay durable decision events so a crash cannot leave state behind the journal."""
        if not self.events_path.exists():
            return
        with self._locked():
            self._recover_unlocked()

    def promote_if_eligible(self, candidate_id, evaluation_id, policy):
        with self._locked():
            self._recover_unlocked()
            return self._promote_locked(candidate_id, evaluation_id, policy)

    def _recover_unlocked(self):
        # Same recovery routine without acquiring the already-held process lock.
        active = self._read(self.active_path, {})
        candidates = self._read(self.candidates_path, {})
        changed_active = changed_candidates = False
        for event in self._read_events():
            if event.get("action") == "promote":
                evaluation_path = self.root / "evaluations" / (event["evaluation_id"] + ".json")
                evaluation_bytes = evaluation_path.read_bytes()
                if hashlib.sha256(evaluation_bytes).hexdigest() != event["evaluation_sha256"]:
                    raise ValueError("Registry promotion evaluation evidence changed after commit.")
                evaluation = json.loads(evaluation_bytes.decode("utf-8"))
                if (evaluation.get("candidate_id") != event["candidate_id"]
                        or evaluation.get("candidate_model_ref") != event["active_model_ref"]):
                    raise ValueError("Registry promotion evaluation identity does not match its journal event.")
                active[event["task_id"]] = {"model_ref": event["active_model_ref"],
                    "previous_model_ref": event.get("previous_model_ref"), "candidate_id": event.get("candidate_id"),
                    "evaluation_id": event.get("evaluation_id"),
                    "adapter_path": evaluation["candidate_adapter_path"],
                    "calibrator_path": evaluation["candidate_calibrator_path"]}; changed_active = True
                if event.get("candidate_id") in candidates:
                    candidates[event["candidate_id"]].update(status="promoted", decision_event_id=event["event_id"]); changed_candidates = True
            elif event.get("action") == "reject" and event.get("candidate_id") in candidates:
                candidates[event["candidate_id"]].update(status="rejected", decision_event_id=event["event_id"], rejection_reasons=event.get("reason_codes", [])); changed_candidates = True
            elif event.get("action") == "rollback":
                active[event["task_id"]] = {"model_ref": event["active_model_ref"], "previous_model_ref": None,
                    "rollback_from": event["rollback_from"], "health_sha256": event["health_sha256"]}; changed_active = True
        if changed_active: self._write_atomic(self.active_path, active)
        if changed_candidates: self._write_atomic(self.candidates_path, candidates)

    def _promote_locked(self, candidate_id, evaluation_id, policy):
        if not isinstance(policy, PromotionPolicy) or policy.sha256_payload() != policy.policy_sha256:
            raise ValueError("Promotion policy is invalid or changed after configuration.")
        candidate = self.candidate(candidate_id)
        evaluation_path = self.root / "evaluations" / (evaluation_id + ".json")
        evaluation_bytes = evaluation_path.read_bytes()
        evaluation = json.loads(evaluation_bytes.decode("utf-8"))
        evaluation_hash = hashlib.sha256(evaluation_bytes).hexdigest()
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
            event = PromotionEvent("", candidate_id, evaluation_id, policy.task_id, "reject", reasons,
                                   previous.get("model_ref") if previous else None,
                                   previous.get("model_ref") if previous else None, policy.policy_sha256,
                                   evaluation_hash, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
            event_dict = asdict(event)
            event_id = _digest({key: value for key, value in event_dict.items() if key not in {"event_id", "created_at"}})
            event = PromotionEvent(event_id, candidate_id, evaluation_id, policy.task_id, "reject", tuple(reasons),
                                   event.previous_model_ref, event.active_model_ref, event.policy_sha256,
                                   event.evaluation_sha256, event.created_at)
            self._append_event(asdict(event))
            self._transition_unlocked(candidate_id, "rejected", decision_event_id=event_id, rejection_reasons=reasons)
            return event
        previous = self.active(policy.task_id)
        reasons = _promotion_reasons(candidate, evaluation, policy)
        if _training_gate_failure(candidate, evaluation):
            reasons = sorted(set(reasons) | {"training_gate_missing_or_changed"})
        expected_incumbent = previous.get("model_ref") if previous else candidate.get("incumbent_model_ref")
        if evaluation.get("incumbent_model_ref") != expected_incumbent:
            reasons = sorted(set(reasons) | {"incumbent_changed_since_evaluation"})
        action = "promote" if not reasons else "reject"
        new_active = {"model_ref": candidate["model_ref"]} if action == "promote" else previous
        event = PromotionEvent("", candidate_id, evaluation_id, policy.task_id, action,
                               tuple(reasons), previous.get("model_ref") if previous else None,
                               new_active.get("model_ref") if new_active else None, policy.policy_sha256,
                               evaluation_hash, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        event_dict = asdict(event)
        event_id = _digest({key: value for key, value in event_dict.items() if key not in {"event_id", "created_at"}})
        event = PromotionEvent(event_id, candidate_id, evaluation_id, policy.task_id, action,
                               tuple(reasons), event.previous_model_ref, event.active_model_ref,
                               event.policy_sha256, event.evaluation_sha256, event.created_at)
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        self._append_event(asdict(event))
        if action == "promote":
            active = self._read(self.active_path, {})
            active[policy.task_id] = {"model_ref": candidate["model_ref"],
                                      "adapter_path": evaluation["candidate_adapter_path"],
                                      "calibrator_path": evaluation["candidate_calibrator_path"],
                                      "previous_model_ref": previous.get("model_ref") if previous else None,
                                      "candidate_id": candidate_id, "evaluation_id": evaluation_id}
            self._write_atomic(self.active_path, active)
            self._transition_unlocked(candidate_id, "promoted", decision_event_id=event_id)
        else:
            self._transition_unlocked(candidate_id, "rejected", decision_event_id=event_id, rejection_reasons=reasons)
        return event

    def _read_events(self):
        return self._repair_and_read_events()

    def rollback_if_unhealthy(self, task_id, health_evaluation):
        raise ValueError("trusted_health_evaluator_attestation_unavailable")


def _promotion_reasons(candidate, result, policy):
    reasons = []
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
    try:
        from finlabel.labeling.task import load_task, load_task_policy
        from finlabel.training.evaluation import labeling_policy_sha256
        from finlabel.training.task_spec import task_spec_sha256
        task = load_task(candidate["task_path"])
        labeling_policy = load_task_policy(task)
        if labeling_policy is None:
            raise ValueError("labeling_policy_missing")
        labels = list(task.labels)
        threshold = labeling_policy.min_calibrated_confidence
        if (not isinstance(labels, list) or not labels or len(set(labels)) != len(labels)
                or not _finite(threshold) or not 0 <= threshold <= 1
                or candidate.get("task_labels") != labels
                or candidate.get("labeling_policy_min_confidence") != threshold
                or labeling_policy_sha256(labeling_policy) != result.get("labeling_policy_sha256")
                or candidate.get("labeling_policy_sha256") != result.get("labeling_policy_sha256")
                or task_spec_sha256(task) != result.get("task_spec_sha256")):
            raise ValueError("invalid_policy_snapshot")
        candidate_rows = next(row["holdout_records"] for row in result["models"]
                              if row.get("role") == "candidate")
        incumbent_rows = next(row["holdout_records"] for row in result["models"]
                               if row.get("role") == "incumbent")
        manifest_path = Path(candidate["trusted_manifest_path"]).resolve()
        _validate_holdout_row_binding(manifest_path, result.get("dataset_manifest_sha256"),
            result.get("holdout_count"), task, labels, candidate_rows, incumbent_rows)
        manifest_bytes = manifest_path.read_bytes()
        trusted_manifest = json.loads(manifest_bytes.decode("utf-8"))
        holdout = trusted_manifest["partitions"]["holdout"]
        from finlabel.labeling.prediction import Prediction
        from finlabel.training.evaluation import CalibrationArtifact
        for role, rows in (("candidate", candidate_rows), ("incumbent", incumbent_rows)):
            model = next(row for row in result["models"] if row.get("role") == role)
            calibration_path = Path(model["calibrator_path"])
            calibration = CalibrationArtifact.load(calibration_path)
            if (hashlib.sha256(calibration_path.read_bytes()).hexdigest() != model.get("calibrator_sha256")
                    or calibration.model_ref != model.get("model_ref")
                    or calibration.task_id != task.task_id
                    or calibration.policy_id != labeling_policy.policy_id
                    or calibration.source_hashes.get("labeling_policy_sha256")
                        != labeling_policy_sha256(labeling_policy)):
                raise ValueError("calibrator_identity_invalid")
            for row in rows:
                if row["prediction"] is None:
                    continue
                prediction = Prediction(row["prediction"], None, row["scores"], None, None,
                    "label_json_mean_log_likelihood_v2", "0" * 64)
                confidence = calibration.calibrate(prediction, task=task,
                    policy=labeling_policy, model_ref=model["model_ref"]).confidence
                if not _finite(row["confidence"]) or abs(confidence - row["confidence"]) > 1e-12:
                    raise ValueError("calibrated_confidence_does_not_match_artifact")
        candidate_derived = _derive_holdout_metrics(candidate_rows, labels, threshold)
        incumbent_derived = _derive_holdout_metrics(incumbent_rows, labels, threshold)
        if candidate_derived["records_sha256"] != next(
                row["holdout_scores_sha256"] for row in result["models"] if row.get("role") == "candidate"):
            raise ValueError("candidate_metric_evidence_digest_mismatch")
        if incumbent_derived["records_sha256"] != next(
                row["holdout_scores_sha256"] for row in result["models"] if row.get("role") == "incumbent"):
            raise ValueError("incumbent_metric_evidence_digest_mismatch")
        candidate_ref_targets = [(row["record_ref"], row["input_digest"], row["target"])
                                 for row in candidate_rows]
        incumbent_ref_targets = [(row["record_ref"], row["input_digest"], row["target"])
                                 for row in incumbent_rows]
        if candidate_ref_targets != incumbent_ref_targets:
            raise ValueError("candidate_incumbent_holdout_rows_differ")
        for role, derived in (("candidate", candidate_derived), ("incumbent", incumbent_derived)):
            stored = next(row for row in result["models"] if row.get("role") == role)
            if (not _metrics_equal(stored.get("metrics"), derived["metrics"])
                    or stored.get("per_label") != derived["per_label"]
                    or stored.get("confusion") != derived["confusion"]):
                raise ValueError(role + "_metrics_do_not_match_row_evidence")
        if (not _metrics_equal(result.get("candidate_metrics"), candidate_derived["metrics"])
                or not _metrics_equal(result.get("incumbent_metrics"), incumbent_derived["metrics"])
                or result.get("candidate_per_label") != candidate_derived["per_label_f1"]
                or result.get("incumbent_per_label") != incumbent_derived["per_label_f1"]):
            raise ValueError("aggregate_metrics_do_not_match_row_evidence")
    except (OSError, KeyError, TypeError, ValueError, StopIteration):
        reasons.append("holdout_metric_evidence_invalid")
    try:
        from finlabel.training.backend import _artifact_tree_sha256
        from finlabel.training.evaluation import CalibrationArtifact
        manifest_path = Path(candidate.get("trusted_manifest_path", "")).resolve()
        manifest_bytes = manifest_path.read_bytes()
        trusted_manifest = json.loads(manifest_bytes.decode("utf-8"))
        holdout = trusted_manifest["partitions"]["holdout"]
        adapter_path = Path(result.get("candidate_adapter_path", "")).resolve()
        calibration_path = Path(result.get("candidate_calibrator_path", "")).resolve()
        calibration = CalibrationArtifact.load(calibration_path)
        model = next(item for item in result.get("models", []) if item.get("role") == "candidate")
        if (not adapter_path.is_dir() or _artifact_tree_sha256(adapter_path) != model.get("adapter_sha256")
                or calibration.model_ref != result.get("candidate_model_ref")
                or calibration.policy_id != policy.policy_id
                or calibration.task_id != policy.task_id
                or calibration.task_spec_sha256 != result.get("task_spec_sha256")
                or calibration.source_hashes.get("labeling_policy_sha256")
                    != result.get("labeling_policy_sha256")
                or hashlib.sha256(calibration_path.read_bytes()).hexdigest() != model.get("calibrator_sha256")
                or hashlib.sha256(manifest_bytes).hexdigest() != result.get("dataset_manifest_sha256")
                or trusted_manifest.get("task_id") != policy.task_id
                or trusted_manifest.get("trust_kind") not in {"provided_ground_truth", "validated_rule"}
                or hashlib.sha256(json.dumps(
                    [{"input_digest": row["input_digest"]} for row in holdout["records"]],
                    sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
                    != result.get("holdout_sha256")
                or holdout.get("dataset_sha256") != result.get("holdout_dataset_sha256")
                or holdout.get("count") != result.get("holdout_count")
                or result.get("trusted_label_provenance", {}).get("snapshot_sha256")
                    != trusted_manifest.get("snapshot_sha256")
                or not _SHA.fullmatch(str(model.get("holdout_scores_sha256", "")))):
            reasons.append("candidate_model_or_calibrator_artifact_mismatch")
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        reasons.append("candidate_model_or_calibrator_artifact_missing")
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


def _training_gate_failure(candidate, evaluation):
    """Recheck the exact authorized gate under the registry promotion lock."""
    path_value = candidate.get("training_gate_path")
    expected = candidate.get("training_gate_sha256")
    if (not isinstance(path_value, str) or not path_value
            or not isinstance(expected, str) or not _SHA.fullmatch(expected)
            or evaluation.get("training_gate_sha256") != expected):
        return True
    try:
        return hashlib.sha256(Path(path_value).read_bytes()).hexdigest() != expected
    except OSError:
        return True


def _metrics_equal(left, right):
    if not isinstance(left, Mapping) or set(left) != set(right):
        return False
    return all(_finite(left.get(key)) and abs(left[key] - value) <= 1e-12
               for key, value in right.items())


def _validate_holdout_row_binding(manifest_path, manifest_digest, holdout_count, task, labels,
                                  candidate_rows, incumbent_rows):
    """Bind both model evidence sequences to the exact frozen references and JSONL targets."""
    manifest_path = Path(manifest_path).resolve()
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_digest:
        raise ValueError("holdout_manifest_digest_mismatch")
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    holdout = manifest["partitions"]["holdout"]
    refs = holdout.get("records")
    if (isinstance(holdout_count, bool) or not isinstance(holdout_count, int)
            or holdout_count < 0 or not isinstance(refs, list) or isinstance(holdout.get("count"), bool)
            or not isinstance(holdout.get("count"), int) or holdout["count"] != len(refs)
            or holdout["count"] != holdout_count):
        raise ValueError("frozen_holdout_reference_manifest_invalid")
    ordered_refs, seen_refs = [], set()
    for ref in refs:
        if (not isinstance(ref, Mapping) or set(ref) != {"record_ref", "input_digest"}
                or not isinstance(ref.get("record_ref"), str) or not _SHA.fullmatch(ref["record_ref"])
                or not isinstance(ref.get("input_digest"), str) or not _SHA.fullmatch(ref["input_digest"])
                or ref["record_ref"] in seen_refs):
            raise ValueError("frozen_holdout_reference_manifest_invalid")
        seen_refs.add(ref["record_ref"])
        ordered_refs.append((ref["record_ref"], ref["input_digest"]))
    if holdout.get("path") != "holdout.jsonl":
        raise ValueError("frozen_holdout_path_invalid")
    holdout_bytes = (manifest_path.parent / holdout["path"]).read_bytes()
    if hashlib.sha256(holdout_bytes).hexdigest() != holdout.get("dataset_sha256"):
        raise ValueError("frozen_holdout_dataset_digest_mismatch")
    from finlabel.training.dataset import _trusted_prompt
    from finlabel.training.local_evaluator import _prompt_values
    frozen_rows = []
    for line in holdout_bytes.decode("utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if (not isinstance(item, dict) or set(item) != {"prompt", "completion"}
                or not isinstance(item["prompt"], str) or not isinstance(item["completion"], str)):
            raise ValueError("frozen_holdout_row_schema_invalid")
        completion = json.loads(item["completion"])
        if not isinstance(completion, dict) or set(completion) != {"label"}:
            raise ValueError("frozen_holdout_completion_schema_invalid")
        target = completion["label"]
        if not isinstance(target, str) or target not in labels:
            raise ValueError("frozen_holdout_target_invalid")
        features = _prompt_values(item["prompt"], task)
        canonical_features = json.dumps(features, ensure_ascii=False, sort_keys=True,
                                        separators=(",", ":"), default=str)
        input_digest = hashlib.sha256(canonical_features.encode("utf-8")).hexdigest()
        if _trusted_prompt(task, features) != item["prompt"]:
            raise ValueError("frozen_holdout_prompt_invalid")
        frozen_rows.append((input_digest, target))
    if len(frozen_rows) != len(ordered_refs):
        raise ValueError("frozen_holdout_row_count_mismatch")
    expected = [(ref, digest, row[1]) for (ref, digest), row in zip(ordered_refs, frozen_rows)]
    if any(digest != row[0] for (_, digest), row in zip(ordered_refs, frozen_rows)):
        raise ValueError("frozen_holdout_input_digest_does_not_match_prompt")
    for role, rows in (("candidate", candidate_rows), ("incumbent", incumbent_rows)):
        if not isinstance(rows, list):
            raise ValueError(role + "_holdout_rows_malformed")
        observed = [(row.get("record_ref"), row.get("input_digest"), row.get("target"))
                    if isinstance(row, Mapping) else None for row in rows]
        if observed != expected:
            raise ValueError(role + "_holdout_rows_do_not_match_frozen_partition")
    return expected


def _derive_holdout_metrics(rows, labels, threshold):
    """Recompute gates from privacy-minimized per-row target/prediction evidence."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("holdout_rows_missing")
    allowed_reasons = {None, "below_threshold", "rule_conflict", "invalid_input", "unknown_label",
                       "invalid_output", "backend_error", "calibration_error", "stale_source"}
    abstain = "__finlabel_abstain__"
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
