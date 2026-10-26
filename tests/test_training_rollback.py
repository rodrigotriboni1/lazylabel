import hashlib
import json
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from finlabel.training.backend import _artifact_tree_sha256
from finlabel.training.registry import ModelRegistry, PromotionPolicy, _derive_holdout_metrics, _digest


class TrainingRollbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.task_id = "risk"
        self.labels = ["good", "bad"]
        self.policy = PromotionPolicy(
            task_id=self.task_id,
            version="risk-v1",
            required_metrics={"accuracy": 0.5},
            minimum_coverage=0.5,
            allowed_per_label_regression={label: 0.2 for label in self.labels},
            max_calibration_error=0.4,
            rollback_monitor_limits={"accuracy": 0.75},
            min_holdout_count=2,
        )
        self.policy_path = self.root / "models" / "promotion-policies" / "risk.json"
        self.policy_path.parent.mkdir(parents=True)
        self.policy_path.write_text(json.dumps({
            "task_id": self.policy.task_id,
            "version": self.policy.version,
            "required_metrics": dict(self.policy.required_metrics),
            "minimum_coverage": self.policy.minimum_coverage,
            "allowed_per_label_regression": dict(self.policy.allowed_per_label_regression),
            "max_calibration_error": self.policy.max_calibration_error,
            "rollback_monitor_limits": dict(self.policy.rollback_monitor_limits),
            "min_holdout_count": self.policy.min_holdout_count,
        }), encoding="utf-8")
        self.gate_path = self.root / "training-gate.json"
        self.gate_path.write_text("{}", encoding="utf-8")
        self.registry = ModelRegistry(self.root)
        self.workspace = SimpleNamespace(
            workspace_dir=self.root,
            config_path=self.root / "finlabel.yaml",
            supervision_sources={"risk::trusted": {
                "source_name": "trusted", "task_id": "risk", "label_column": "label",
                "label_mapping": {"G": "good", "B": "bad"},
                "provenance_id": "analyst-ground-truth", "trust_kind": "provided_ground_truth",
                "snapshot_sha256": "a" * 64, "row_count": 2,
            }},
        )
        self.task = SimpleNamespace(task_id="risk", labels=self.labels, input_columns=("amount",))
        self.labeling_policy = SimpleNamespace(min_calibrated_confidence=0.5)
        self.snapshot_sha256 = "a" * 64
        self.records = [
            SimpleNamespace(record_ref="1" * 64, input_digest="2" * 64, label="good"),
            SimpleNamespace(record_ref="3" * 64, input_digest="4" * 64, label="bad"),
        ]
        self._promote("model-v1", "base-model", "candidate-v1")
        self._promote("model-v2", "model-v1", "candidate-v2")

    def tearDown(self):
        self.temporary.cleanup()

    def _promote(self, model_ref, incumbent_ref, candidate_id):
        adapter = self.registry.root / "adapters" / candidate_id
        adapter.mkdir(parents=True)
        (adapter / "weights.safetensors").write_bytes((candidate_id + "-weights").encode())
        calibrator = self.registry.root / "calibrators" / (candidate_id + ".json")
        calibrator.parent.mkdir(exist_ok=True)
        calibrator.write_text("{}", encoding="utf-8")
        self.registry.create_candidate(candidate_id, {
            "task_id": self.task_id, "model_ref": model_ref,
            "incumbent_model_ref": incumbent_ref, "expected_active_model_ref": incumbent_ref,
            "adapter_path": str(adapter), "trusted_manifest_path": str(self.root / "trusted.json"),
            "task_path": str(self.root / "tasks" / "risk.json"),
            "policy_sha256": self.policy.policy_sha256,
            "training_gate_path": str(self.gate_path),
            "training_gate_sha256": hashlib.sha256(self.gate_path.read_bytes()).hexdigest(),
        })
        self.registry.transition(candidate_id, "training")
        self.registry.transition(candidate_id, "evaluated")
        evaluation_id = "evaluation-" + candidate_id
        evaluation = {
            "evaluation_id": evaluation_id, "task_id": self.task_id,
            "candidate_id": candidate_id, "candidate_model_ref": model_ref,
            "candidate_adapter_path": str(adapter), "candidate_calibrator_path": str(calibrator),
            "policy_sha256": self.policy.policy_sha256,
            "training_gate_sha256": hashlib.sha256(self.gate_path.read_bytes()).hexdigest(),
            "incumbent_model_ref": incumbent_ref,
            "models": [{"role": "candidate", "model_ref": model_ref,
                        "adapter_path": str(adapter), "adapter_sha256": _artifact_tree_sha256(adapter),
                        "calibrator_path": str(calibrator),
                        "calibrator_sha256": hashlib.sha256(calibrator.read_bytes()).hexdigest()}],
        }
        evaluation_path = self.registry.root / "evaluations" / (evaluation_id + ".json")
        evaluation_path.parent.mkdir(parents=True, exist_ok=True)
        evaluation_path.write_text(json.dumps(evaluation), encoding="utf-8")
        with patch("finlabel.training.registry._promotion_reasons", return_value=[]):
            return self.registry.promote_if_eligible(candidate_id, evaluation_id, self.policy)

    def _row(self, record, prediction, confidence=0.9):
        scores = {"good": 0.1, "bad": 0.9} if prediction == "bad" else {"good": 0.9, "bad": 0.1}
        return {"record_ref": record.record_ref, "input_digest": record.input_digest,
                "target": record.label, "prediction": prediction, "scores": scores,
                "confidence": confidence, "applied": True, "reason_code": None}

    def _health(self, *, rows=None, **changes):
        rows = rows if rows is not None else [
            self._row(self.records[0], "bad"), self._row(self.records[1], "good")
        ]
        metrics = _derive_holdout_metrics(rows, self.labels, 0.5)["metrics"]
        active = self.registry.active(self.task_id)
        payload = {
            "schema_version": 1,
            "evaluation_id": "c" * 32,
            "task_id": self.task_id,
            "active_model_ref": active["model_ref"],
            "previous_model_ref": active["previous_model_ref"],
            "promotion_evaluation_id": active["evaluation_id"],
            "policy_sha256": self.policy.policy_sha256,
            "trusted_snapshot_sha256": self.snapshot_sha256,
            "evaluated_count": len(rows),
            "row_evidence": rows,
            "metrics": metrics,
        }
        payload.update(changes)
        payload["health_sha256"] = _digest(payload)
        return payload

    def _with_trusted_context(self, call):
        with patch("finlabel.project.load_project", return_value=self.workspace), \
             patch("finlabel.labeling.task.load_task", return_value=self.task), \
             patch("finlabel.labeling.task.load_task_policy", return_value=self.labeling_policy), \
             patch("finlabel.training.trusted_labels.load_trusted_labels", return_value=SimpleNamespace(
                 task_id=self.task_id, trust_kind="provided_ground_truth",
                 snapshot_sha256=self.snapshot_sha256, records=self.records)):
            return call()

    def test_healthy_evaluation_does_not_change_pointer_or_journal(self):
        health = self._health(rows=[self._row(self.records[0], "good"), self._row(self.records[1], "bad")])
        before_active = self.registry.active_path.read_bytes()
        before_events = self.registry.events_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "health_gates_passed"):
            self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))

        self.assertEqual(self.registry.active_path.read_bytes(), before_active)
        self.assertEqual(self.registry.events_path.read_bytes(), before_events)

    def test_valid_unhealthy_evaluation_restores_previous_verified_adapter_and_calibrator(self):
        health = self._health()

        event = self._with_trusted_context(
            lambda: self.registry.rollback_if_unhealthy(self.task_id, health))

        active = self.registry.active(self.task_id)
        self.assertEqual(event.action, "rollback")
        self.assertEqual(active["model_ref"], "model-v1")
        self.assertEqual(active["adapter_path"], str(self.registry.root / "adapters" / "candidate-v1"))
        self.assertEqual(active["calibrator_path"], str(self.registry.root / "calibrators" / "candidate-v1.json"))
        self.assertEqual(sum(row["action"] == "rollback" for row in self.registry._read_events()), 1)
        recovered = ModelRegistry(self.root).active(self.task_id)
        self.assertEqual(recovered, active)

    def test_missing_previous_model_fails_closed(self):
        remaining = [event for event in self.registry._read_events()
                     if event.get("candidate_id") != "candidate-v1"]
        self.registry.events_path.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in remaining), encoding="utf-8")
        self.registry._recover_unlocked()
        health = self._health()
        before = self.registry.active_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "rollback_target_missing"):
            self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))
        self.assertEqual(self.registry.active_path.read_bytes(), before)

    def test_stale_trusted_labels_fail_closed(self):
        health = self._health()
        with patch("finlabel.project.load_project", return_value=self.workspace), \
             patch("finlabel.labeling.task.load_task", return_value=self.task), \
             patch("finlabel.labeling.task.load_task_policy", return_value=self.labeling_policy), \
             patch("finlabel.training.trusted_labels.load_trusted_labels", side_effect=ValueError("stale")):
            before = self.registry.active_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "trusted_labels_unavailable_or_stale"):
                self.registry.rollback_if_unhealthy(self.task_id, health)
            self.assertEqual(self.registry.active_path.read_bytes(), before)

    def test_undersized_evaluation_fails_closed(self):
        health = self._health(rows=[self._row(self.records[0], "bad")])
        before = self.registry.active_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "health_evaluation_too_small"):
            self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))
        self.assertEqual(self.registry.active_path.read_bytes(), before)

    def test_active_model_mismatch_fails_closed(self):
        health = self._health(active_model_ref="different-model")
        before = self.registry.active_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "health_evaluation_identity_mismatch"):
            self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))
        self.assertEqual(self.registry.active_path.read_bytes(), before)

    def test_policy_change_fails_closed(self):
        health = self._health()
        configured = json.loads(self.policy_path.read_text(encoding="utf-8"))
        configured["version"] = "risk-v2"
        self.policy_path.write_text(json.dumps(configured), encoding="utf-8")
        before = self.registry.active_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "health_evaluation_identity_mismatch"):
            self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))
        self.assertEqual(self.registry.active_path.read_bytes(), before)

    def test_corrupt_row_evidence_fails_closed(self):
        health = self._health()
        health["row_evidence"][0]["target"] = "forged"
        health["health_sha256"] = _digest({key: value for key, value in health.items() if key != "health_sha256"})
        before = self.registry.active_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "health_row_evidence_invalid"):
            self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))
        self.assertEqual(self.registry.active_path.read_bytes(), before)

    def test_replay_does_not_append_a_second_rollback_or_change_restored_pointer(self):
        health = self._health()
        self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))
        before = self.registry.active_path.read_bytes()
        event_count = len(self.registry._read_events())
        with self.assertRaisesRegex(ValueError, "rollback_already_applied"):
            self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))
        self.assertEqual(self.registry.active_path.read_bytes(), before)
        self.assertEqual(len(self.registry._read_events()), event_count)

    def test_registry_write_failure_preserves_current_pointer_and_journal(self):
        health = self._health()
        before_active = self.registry.active_path.read_bytes()
        before_events = self.registry.events_path.read_bytes()
        with patch.object(self.registry, "_append_event", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))
        self.assertEqual(self.registry.active_path.read_bytes(), before_active)
        self.assertEqual(self.registry.events_path.read_bytes(), before_events)

    def test_concurrent_rollback_requests_append_one_event_and_restore_once(self):
        health = self._health()
        registries = [ModelRegistry(self.root), ModelRegistry(self.root)]

        def attempt(registry):
            try:
                return self._with_trusted_context(
                    lambda: registry.rollback_if_unhealthy(self.task_id, health)).action
            except ValueError as exc:
                return str(exc)

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(attempt, registries))

        self.assertEqual(results.count("rollback"), 1)
        self.assertEqual(results.count("rollback_already_applied"), 1)
        self.assertEqual(self.registry.active(self.task_id)["model_ref"], "model-v1")
        self.assertEqual(sum(row["action"] == "rollback" for row in self.registry._read_events()), 1)

    def test_changed_previous_adapter_fails_closed(self):
        health = self._health()
        adapter = self.registry.root / "adapters" / "candidate-v1" / "weights.safetensors"
        adapter.write_bytes(b"changed after verified promotion")
        before = self.registry.active_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "promoted_model_artifact_missing_or_mismatched"):
            self._with_trusted_context(lambda: self.registry.rollback_if_unhealthy(self.task_id, health))
        self.assertEqual(self.registry.active_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
