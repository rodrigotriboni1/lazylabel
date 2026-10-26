import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finlabel.labeling.policy import LabelingPolicy
from finlabel.labeling.task import LabelTask, save_task, task_file_path
from finlabel.project import init_project, save_project
from finlabel.sources.base import ProjectConfig, SourceSpec
from finlabel.training.backend import TrainingResult
from finlabel.training.autopipeline import run_training_cycle
from finlabel.training.registry import ModelRegistry, PromotionPolicy
from finlabel.training.trusted_labels import TrustedLabelSourceSpec, load_trusted_labels, supervision_key


class AutonomousTrainingCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config_path = init_project(self.root)
        self.source_path = self.root / "reference.csv"
        lines = ["amount,class"]
        lines.extend("{},{}".format(i, "L" if i < 14 else "H") for i in range(28))
        self.source_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.source = SourceSpec("reference", "csv", self.source_path)
        self.policy_path = self.root / ".finlabel" / "tasks" / "risk-policy.json"
        self.policy_path.write_text(json.dumps({
            "policy_id": "risk-v1", "task_id": "risk", "allowed_labels": ["low", "high"],
            "rules_version": "r1", "rules": [{"field": "amount", "operator": "number_between", "minimum": 0}],
            "calibration_ref": "cal-v1", "min_calibrated_confidence": 0.7, "max_staleness_seconds": 30,
        }), encoding="utf-8")
        self.task = LabelTask("risk", "classify risk", ("amount",), ("low", "high"), "local/model",
                              policy_path=str(self.policy_path))
        save_task(self.task, task_file_path(self.root / ".finlabel", "risk"))
        trusted = TrustedLabelSourceSpec("reference", "risk", "class", {"L": "low", "H": "high"},
                                         "reviewed-reference-v1", "provided_ground_truth")
        initial = ProjectConfig(self.config_path, {"reference": self.source}, {}, self.root / ".finlabel",
                                {supervision_key("risk", "reference"): trusted.to_dict()})
        batch = load_trusted_labels(initial, self.task)
        saved_trusted = {**trusted.to_dict(), "snapshot_sha256": batch.snapshot_sha256, "row_count": batch.row_count}
        self.config = ProjectConfig(self.config_path, {"reference": self.source}, {}, self.root / ".finlabel",
                                    {supervision_key("risk", "reference"): saved_trusted})
        save_project(self.config, self.config_path)
        registry = ModelRegistry(self.root / ".finlabel")
        self.base_ref = "local/model"
        self.previous_ref = self.base_ref + "+peft:" + "a" * 64
        registry._write_atomic(registry.active_path, {"risk": {"model_ref": self.previous_ref,
            "adapter_path": str(self.root / "active-adapter"), "calibrator_path": "unused"}})

    def tearDown(self):
        self.temp.cleanup()

    def _promotion_policy(self):
        return PromotionPolicy("risk", "v1", {"macro_f1": 0.5}, 0.5, {"low": 0.1, "high": 0.1},
                               0.2, {"accuracy": 0.2}, 2)

    def _promotion_payload(self):
        policy = self._promotion_policy()
        return {"task_id": policy.task_id, "version": policy.version,
            "required_metrics": dict(policy.required_metrics), "minimum_coverage": policy.minimum_coverage,
            "allowed_per_label_regression": dict(policy.allowed_per_label_regression),
            "max_calibration_error": policy.max_calibration_error,
            "rollback_monitor_limits": dict(policy.rollback_monitor_limits), "min_holdout_count": policy.min_holdout_count}

    def test_missing_gate_blocks_cycle_and_preserves_active_model_pointer(self):
        policy_path = self.root / ".finlabel" / "models" / "promotion-policies" / "risk.json"
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps(self._promotion_payload()), encoding="utf-8")
        summary = run_training_cycle(self.config_path, "risk")
        self.assertEqual(summary.state, "blocked")
        self.assertIn("training_gate_missing", summary.reason_codes)
        active = ModelRegistry(self.root / ".finlabel").active("risk")
        self.assertEqual(active["model_ref"], self.previous_ref)

    def test_changed_gate_after_evaluation_rejects_candidate_without_pointer_change(self):
        models = self.root / ".finlabel" / "models"
        policy_dir = models / "promotion-policies"
        policy_dir.mkdir(parents=True, exist_ok=True)
        policy_dir.joinpath("risk.json").write_text(json.dumps(self._promotion_payload()), encoding="utf-8")
        gate = self.root / ".finlabel" / "training-gate.json"
        gate.write_text(json.dumps({"authorized": True, "model_id": "local/model", "license": "test",
            "hardware": "cpu", "data_policy": "synthetic", "evaluation_protocol": "frozen holdout"}), encoding="utf-8")

        def fake_evaluate(task, policy, manifest, candidate_adapter, incumbent_adapter, **kwargs):
            gate.write_text(gate.read_text() + " ")
            candidate_ref = self.base_ref + "+peft:" + "d" * 64
            path = models / "evaluations" / "fake.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"evaluation_id": "e" * 32, "candidate_model_ref": candidate_ref,
                                        "incumbent_model_ref": self.previous_ref}), encoding="utf-8")
            return path

        output = models / "adapters" / "candidate"
        output.mkdir(parents=True)
        with patch("finlabel.training.autopipeline.validate_training_request"), \
             patch("finlabel.training.autopipeline.train_adapter", return_value=TrainingResult(
                 output, self.base_ref, "f" * 64, (), {}, "d" * 64)), \
             patch("finlabel.training.autopipeline.evaluate_candidate", side_effect=fake_evaluate):
            summary = run_training_cycle(self.config_path, "risk")
        self.assertEqual(summary.state, "blocked")
        self.assertIn("training_gate_changed_during_cycle", summary.reason_codes)
        active = ModelRegistry(self.root / ".finlabel").active("risk")
        self.assertEqual(active["model_ref"], self.previous_ref)
        candidate = ModelRegistry(self.root / ".finlabel").candidate(summary.candidate_id)
        self.assertEqual(candidate["status"], "rejected")

    def test_deleted_promotion_policy_after_evaluation_preserves_failure_reason(self):
        models = self.root / ".finlabel" / "models"
        policy_dir = models / "promotion-policies"
        policy_dir.mkdir(parents=True, exist_ok=True)
        promotion_path = policy_dir / "risk.json"
        promotion_path.write_text(json.dumps(self._promotion_payload()), encoding="utf-8")
        gate = self.root / ".finlabel" / "training-gate.json"
        gate.write_text(json.dumps({"authorized": True, "model_id": "local/model", "license": "test",
            "hardware": "cpu", "data_policy": "synthetic", "evaluation_protocol": "frozen holdout"}), encoding="utf-8")

        def fake_evaluate(task, policy, manifest, candidate_adapter, incumbent_adapter, **kwargs):
            promotion_path.unlink()
            path = models / "evaluations" / "fake.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"evaluation_id": "e" * 32,
                "candidate_model_ref": self.base_ref + "+peft:" + "d" * 64,
                "incumbent_model_ref": self.previous_ref}), encoding="utf-8")
            return path

        output = models / "adapters" / "candidate"
        output.mkdir(parents=True)
        with patch("finlabel.training.autopipeline.validate_training_request"), \
             patch("finlabel.training.autopipeline.train_adapter", return_value=TrainingResult(
                 output, self.base_ref, "f" * 64, (), {}, "d" * 64)), \
             patch("finlabel.training.autopipeline.evaluate_candidate", side_effect=fake_evaluate):
            summary = run_training_cycle(self.config_path, "risk")
        expected = "cycle_prerequisite_failed:FileNotFoundError"
        self.assertEqual(summary.state, "blocked")
        self.assertEqual(summary.reason_codes, (expected,))
        self.assertEqual(ModelRegistry(self.root / ".finlabel").active("risk")["model_ref"], self.previous_ref)
        candidate = ModelRegistry(self.root / ".finlabel").candidate(summary.candidate_id)
        self.assertEqual(candidate["status"], "rejected")
        self.assertEqual(candidate["rejection_reasons"], [expected])
        self.assertEqual(json.loads(Path(summary.manifest_path).read_text())["reason_codes"], [expected])

    def test_changed_promotion_threshold_after_evaluation_blocks_without_pointer_change(self):
        models = self.root / ".finlabel" / "models"
        policy_dir = models / "promotion-policies"
        policy_dir.mkdir(parents=True, exist_ok=True)
        promotion_path = policy_dir / "risk.json"
        promotion_path.write_text(json.dumps(self._promotion_payload()), encoding="utf-8")
        gate = self.root / ".finlabel" / "training-gate.json"
        gate.write_text(json.dumps({"authorized": True, "model_id": "local/model", "license": "test",
            "hardware": "cpu", "data_policy": "synthetic", "evaluation_protocol": "frozen holdout"}), encoding="utf-8")

        def fake_evaluate(task, policy, manifest, candidate_adapter, incumbent_adapter, **kwargs):
            payload = self._promotion_payload()
            payload["minimum_coverage"] = 0.8
            promotion_path.write_text(json.dumps(payload), encoding="utf-8")
            path = models / "evaluations" / "fake.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"evaluation_id": "e" * 32,
                "candidate_model_ref": self.base_ref + "+peft:" + "d" * 64,
                "incumbent_model_ref": self.previous_ref}), encoding="utf-8")
            return path

        output = models / "adapters" / "candidate"
        output.mkdir(parents=True)
        with patch("finlabel.training.autopipeline.validate_training_request"), \
             patch("finlabel.training.autopipeline.train_adapter", return_value=TrainingResult(
                 output, self.base_ref, "f" * 64, (), {}, "d" * 64)), \
             patch("finlabel.training.autopipeline.evaluate_candidate", side_effect=fake_evaluate):
            summary = run_training_cycle(self.config_path, "risk")
        self.assertEqual(summary.state, "blocked")
        self.assertIn("task_or_promotion_policy_changed_during_cycle", summary.reason_codes)
        self.assertEqual(ModelRegistry(self.root / ".finlabel").active("risk")["model_ref"], self.previous_ref)


import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from finlabel.training.autopipeline import evaluate_post_promotion_health


class PostPromotionHealthTests(unittest.TestCase):
    def test_health_entry_point_uses_shared_registry_decision(self):
        project = SimpleNamespace(workspace_dir=Path("/tmp/finlabel-workspace"))
        health_evaluation = {"evaluation_id": "a" * 32}
        event = object()
        registry = SimpleNamespace(rollback_if_unhealthy=lambda task_id, evaluation: event)
        with patch("finlabel.training.autopipeline.ModelRegistry", return_value=registry) as factory:
            result = evaluate_post_promotion_health(project, "risk", health_evaluation)

        factory.assert_called_once_with(project.workspace_dir)
        self.assertIs(result, event)
