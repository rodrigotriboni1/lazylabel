import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from lazylabel.adapters.outbound.persistence.policies import LabelingPolicy
from lazylabel.domain.labeling.prediction import Prediction, PredictionError
from lazylabel.adapters.outbound.persistence.tasks import LabelTask, save_task
from lazylabel.adapters.outbound.training.backend import _artifact_tree_sha256
from lazylabel.adapters.outbound.persistence.datasets import prepare_trusted_dataset
from lazylabel.adapters.outbound.training.evaluation import CalibrationArtifact, fit_calibrator, labeling_policy_sha256
from lazylabel.adapters.outbound.training.local_evaluator import _metrics, _read_partition, _score
from lazylabel.adapters.outbound.persistence.registry import ModelRegistry, PromotionPolicy, _derive_holdout_metrics, _digest, _promotion_reasons, _validate_holdout_row_binding
from lazylabel.domain.training.task_spec import task_spec_sha256
from lazylabel.adapters.outbound.sources.trusted_labels import TrustedLabelBatch, TrustedLabelRecord
from lazylabel.adapters.outbound.models.text_generation import RAW_SCORE_METHOD


def _prediction(label="low"):
    scores = {"low": 0.9, "high": 0.1} if label == "low" else {"low": 0.1, "high": 0.9}
    return Prediction(label, None, scores, None, None, RAW_SCORE_METHOD, hashlib.sha256(label.encode()).hexdigest())


class Calibrator:
    def calibrate(self, prediction, **kwargs):
        return type("Result", (), {"confidence": 0.8})()


class Backend:
    def __init__(self, result): self.result = result
    def predict_prompt(self, *args, **kwargs):
        if isinstance(self.result, Exception): raise self.result
        return self.result


class LocalEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.task = LabelTask("risk", "classify", ("amount",), ("low", "high"), "local/model")
        self.policy = LabelingPolicy("risk-v1", "risk", ("low", "high"), "rules-v1", "cal-v1", 0.7, 30)

    def test_accuracy_and_coverage_denominators_include_abstentions(self):
        scored = [
            {"record_ref": "a" * 64, "input_digest": "1" * 64, "prediction": _prediction("low"), "target": "low", "reason_code": None, "confidence": None, "applied": False},
            {"record_ref": "b" * 64, "input_digest": "2" * 64, "prediction": None, "target": "high", "reason_code": "invalid_output", "confidence": None, "applied": False},
        ]
        metrics, labels, confusion = _metrics(scored, Calibrator(), self.task, self.policy, "model@rev")
        self.assertEqual(metrics["accuracy"], 0.5)
        self.assertEqual(metrics["coverage"], 0.5)
        self.assertEqual(labels["high"]["support"], 1)
        self.assertEqual(confusion["high"]["__finlabel_abstain__"], 1)

    def test_recomputed_holdout_metrics_count_abstention_in_per_label_recall(self):
        rows = [
            {"record_ref": "a" * 64, "input_digest": "1" * 64, "target": "low", "prediction": "low",
             "scores": {"low": 0.9, "high": 0.1}, "confidence": 0.9, "applied": True, "reason_code": None},
            {"record_ref": "b" * 64, "input_digest": "2" * 64, "target": "high", "prediction": None,
             "scores": None, "confidence": None, "applied": False, "reason_code": "invalid_output"},
        ]
        derived = _derive_holdout_metrics(rows, self.task.labels, 0.7)
        self.assertEqual(derived["metrics"]["accuracy"], 0.5)
        self.assertEqual(derived["metrics"]["coverage"], 0.5)
        self.assertEqual(derived["per_label"]["high"]["recall"], 0.0)

    def test_task_specific_per_label_regression_gate_is_applied(self):
        policy = PromotionPolicy("risk", "v1", {"macro_f1": 0.5}, 0.5,
            {"low": 0.1, "high": 0.1}, 0.2, {"accuracy": 0.2}, 2)
        gate_hash = "a" * 64
        candidate = {"task_id": "risk", "candidate_id": "candidate", "model_ref": "candidate-ref",
                     "status": "evaluated", "training_gate_sha256": gate_hash,
                     "incumbent_model_ref": "incumbent-ref", "expected_active_model_ref": "incumbent-ref",
                     "task_path": "/missing/task.json", "trusted_manifest_path": "/missing/manifest.json"}
        result = {"evaluator": "unavailable-test-fixture", "evaluation_sha256": "0" * 64,
            "task_id": "risk", "candidate_id": "candidate", "candidate_model_ref": "candidate-ref",
            "incumbent_model_ref": "incumbent-ref", "policy_sha256": policy.policy_sha256,
            "training_gate_sha256": gate_hash, "same_frozen_holdout": True,
            "holdout_sha256": "b" * 64, "holdout_dataset_sha256": "c" * 64,
            "dataset_manifest_sha256": "d" * 64, "holdout_count": 10, "coverage": 0.8,
            "calibration_error": 0.1, "trusted_label_provenance": {"source_name": "labels",
            "provenance_id": "reviewed-v1", "trust_kind": "provided_ground_truth", "snapshot_sha256": "e" * 64},
            "candidate_metrics": {"macro_f1": 0.8}, "incumbent_metrics": {"macro_f1": 0.7},
            "candidate_per_label": {"low": 0.5, "high": 0.9},
            "incumbent_per_label": {"low": 0.9, "high": 0.9}}
        reasons = _promotion_reasons(candidate, result, policy)
        self.assertIn("per_label_regression_failed:low", reasons)

    def test_malformed_model_outputs_are_counted_as_abstentions(self):
        row = ("a" * 64, "b" * 64, "prompt", "low")
        scored = _score([row], Backend(PredictionError("bad output", reason_code="invalid_output")),
                        self.task, self.policy)
        self.assertIsNone(scored[0]["prediction"])
        metrics, _, _ = _metrics(scored, Calibrator(), self.task, self.policy, "model@rev")
        self.assertEqual(metrics["accuracy"], 0.0)
        self.assertEqual(metrics["coverage"], 0.0)

    def test_calibration_partition_order_and_dataset_tampering_are_rejected(self):
        records = []
        for i in range(28):
            features = {"amount": i}
            digest = hashlib.sha256(json.dumps(features, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            records.append(TrustedLabelRecord(hashlib.sha256(str(i).encode()).hexdigest(), features,
                            "low" if i < 14 else "high", digest, hashlib.sha256(("s" + str(i)).encode()).hexdigest()))
        batch = TrustedLabelBatch("labels", "risk", "advisor-reviewed", "provided_ground_truth", ("amount",),
                                  "class", records, "c" * 64)
        with tempfile.TemporaryDirectory() as temporary:
            manifest = prepare_trusted_dataset(batch, self.task, workspace_dir=temporary)
            _raw, part, rows = _read_partition(manifest, "calibration")
            self.assertEqual(len(rows), part["count"])
            data_path = manifest.path / part["path"]
            lines = data_path.read_text().splitlines()
            data_path.write_text("\n".join(reversed(lines)) + "\n")
            with self.assertRaisesRegex(ValueError, "dataset_digest_mismatch"):
                _read_partition(manifest, "calibration")

    def test_candidate_and_incumbent_must_bind_to_same_ordered_holdout_rows(self):
        records = []
        for i in range(28):
            features = {"amount": str(i)}
            digest = hashlib.sha256(json.dumps(features, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            records.append(TrustedLabelRecord(hashlib.sha256(("row" + str(i)).encode()).hexdigest(), features,
                "low" if i < 14 else "high", digest, hashlib.sha256(("split" + str(i)).encode()).hexdigest()))
        batch = TrustedLabelBatch("labels", "risk", "advisor-reviewed", "provided_ground_truth", ("amount",),
                                  "class", records, "d" * 64)
        with tempfile.TemporaryDirectory() as temporary:
            manifest = prepare_trusted_dataset(batch, self.task, workspace_dir=temporary)
            raw = json.loads(manifest.manifest_path.read_text())
            refs = raw["partitions"]["holdout"]["records"]
            lines = [json.loads(line) for line in (manifest.path / "holdout.jsonl").read_text().splitlines()]
            rows = [{"record_ref": ref["record_ref"], "input_digest": ref["input_digest"],
                     "target": json.loads(line["completion"])["label"]}
                    for ref, line in zip(refs, lines)]
            args = (manifest.manifest_path, manifest.manifest_sha256, len(rows), self.task,
                    self.task.labels, rows, rows)
            self.assertEqual(len(_validate_holdout_row_binding(*args)), len(rows))
            altered = [dict(row) for row in rows]
            altered[0]["record_ref"] = "f" * 64
            with self.assertRaisesRegex(ValueError, "candidate_holdout_rows_do_not_match"):
                _validate_holdout_row_binding(manifest.manifest_path, manifest.manifest_sha256, len(rows),
                    self.task, self.task.labels, altered, rows)
            reordered = list(reversed(rows))
            with self.assertRaisesRegex(ValueError, "incumbent_holdout_rows_do_not_match"):
                _validate_holdout_row_binding(manifest.manifest_path, manifest.manifest_sha256, len(rows),
                    self.task, self.task.labels, rows, reordered)

    def _verified_promotion_artifacts(self, root):
        """Persist real task, frozen rows, fitted calibrators and evaluator evidence."""
        self.policy = replace(self.policy, rules=({"field": "amount", "operator": "not_empty"},))
        policy_path = root / "risk-policy.json"
        policy_path.write_text(json.dumps({
            "policy_id": self.policy.policy_id, "task_id": self.policy.task_id,
            "allowed_labels": list(self.policy.allowed_labels), "rules_version": self.policy.rules_version,
            "calibration_ref": self.policy.calibration_ref,
            "min_calibrated_confidence": self.policy.min_calibrated_confidence,
            "max_staleness_seconds": self.policy.max_staleness_seconds,
            "rules": [dict(rule) for rule in self.policy.rules],
        }), encoding="utf-8")
        task = replace(self.task, policy_path=str(policy_path))
        task_path = save_task(task, root / "risk.json")
        records = []
        for index in range(28):
            features = {"amount": index}
            records.append(TrustedLabelRecord(_digest(index), features,
                "low" if index < 14 else "high", _digest(features)))
        batch = TrustedLabelBatch("labels", task.task_id, "advisor-ground-truth", "provided_ground_truth",
                                  task.input_columns, "class", records, "a" * 64)
        manifest = prepare_trusted_dataset(batch, task, workspace_dir=root)
        raw, holdout, holdout_rows = _read_partition(manifest, "holdout")
        _, _, calibration_rows = _read_partition(manifest, "calibration")
        registry = ModelRegistry(root)
        adapter = registry.root / "adapters" / "candidate"
        adapter.mkdir(parents=True)
        (adapter / "adapter_model.safetensors").write_bytes(b"local candidate weights")
        adapter_digest = _artifact_tree_sha256(adapter)
        candidate_ref = task.model_id + "+peft:" + adapter_digest
        gate_path = root / "training-gate.json"
        gate_path.write_text("{}", encoding="utf-8")
        gate_digest = hashlib.sha256(gate_path.read_bytes()).hexdigest()
        gates = PromotionPolicy("risk", "v1", {"accuracy": 0.5}, 0.5,
            {"low": 0.1, "high": 0.1}, 0.2, {"accuracy": 0.2}, 2)
        models = []
        for role, model_ref in (("candidate", candidate_ref), ("incumbent", task.model_id)):
            predictions = []
            labels = {}
            for index, (ref, _, _, target) in enumerate(calibration_rows):
                correct = index % 2 == 0
                predicted = target if correct else next(label for label in task.labels if label != target)
                top = (-0.1 if correct else -4.0) + index * 0.001
                scores = {label: top if label == predicted else top - 1 for label in task.labels}
                predictions.append({"record_ref": ref, "prediction": Prediction(
                    predicted, None, scores, None, None, RAW_SCORE_METHOD, ref)})
                labels[ref] = target
            fitted = fit_calibrator(predictions, labels, method=RAW_SCORE_METHOD,
                dataset_manifest=manifest, task=task, policy=self.policy,
                model_ref=model_ref, calibration_ref=self.policy.calibration_ref)
            calibrator_path = fitted.save(registry.root / "calibrators" / (role + ".json"))
            scored = [{"record_ref": ref, "input_digest": input_digest, "target": target,
                "prediction": _prediction(target), "confidence": None, "applied": False, "reason_code": None}
                for ref, input_digest, _, target in holdout_rows]
            metrics, per_label, confusion = _metrics(scored, fitted, task, self.policy, model_ref)
            evidence = [{**row, "prediction": row["prediction"].label,
                         "scores": dict(row["prediction"].confidence_evidence)} for row in scored]
            models.append({"role": role, "model_ref": model_ref, "adapter_sha256": adapter_digest,
                "calibrator_path": str(calibrator_path),
                "calibrator_sha256": hashlib.sha256(calibrator_path.read_bytes()).hexdigest(),
                "metrics": metrics, "per_label": per_label, "confusion": confusion,
                "holdout_records": evidence, "holdout_scores_sha256": _digest(evidence)})
        candidate = registry.create_candidate("candidate", {
            "task_id": task.task_id, "model_ref": candidate_ref,
            "incumbent_model_ref": task.model_id, "expected_active_model_ref": task.model_id,
            "task_path": str(task_path), "trusted_manifest_path": str(manifest.manifest_path),
            "task_labels": list(task.labels), "labeling_policy_min_confidence": self.policy.min_calibrated_confidence,
            "labeling_policy_sha256": labeling_policy_sha256(self.policy),
            "training_gate_path": str(gate_path), "training_gate_sha256": gate_digest,
        })
        registry.transition(candidate["candidate_id"], "training")
        registry.transition(candidate["candidate_id"], "evaluated")
        result = {"schema_version": 1, "evaluation_id": "verified-evaluation",
            "evaluator": "finlabel-local-transformers-peft-v1", "score_method": RAW_SCORE_METHOD,
            "task_id": task.task_id, "task_spec_sha256": task_spec_sha256(task),
            "policy_id": self.policy.policy_id, "policy_sha256": gates.policy_sha256,
            "labeling_policy_sha256": labeling_policy_sha256(self.policy),
            "candidate_id": candidate["candidate_id"], "candidate_model_ref": candidate_ref,
            "incumbent_model_ref": task.model_id, "candidate_adapter_path": str(adapter),
            "candidate_calibrator_path": models[0]["calibrator_path"], "models": models,
            "same_frozen_holdout": True, "holdout_count": len(holdout_rows),
            "dataset_manifest_sha256": manifest.manifest_sha256,
            "holdout_sha256": holdout["sha256"], "holdout_dataset_sha256": holdout["dataset_sha256"],
            "training_gate_sha256": gate_digest,
            "trusted_label_provenance": {field: raw[field] for field in (
                "source_name", "provenance_id", "trust_kind", "snapshot_sha256")},
            "candidate_metrics": models[0]["metrics"], "incumbent_metrics": models[1]["metrics"],
            "candidate_per_label": {label: values["f1"] for label, values in models[0]["per_label"].items()},
            "incumbent_per_label": {label: values["f1"] for label, values in models[1]["per_label"].items()},
            "coverage": models[0]["metrics"]["coverage"],
            "calibration_error": models[0]["metrics"]["calibration_error"]}
        return registry, result, gates

    def _persist_evaluation(self, registry, result):
        unsigned = {key: value for key, value in result.items() if key != "evaluation_sha256"}
        result["evaluation_sha256"] = _digest(unsigned)
        path = registry.root / "evaluations" / (result["evaluation_id"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result), encoding="utf-8")

    def test_verified_candidate_reaches_promotion_decision_with_labeling_policy_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            registry, result, gates = self._verified_promotion_artifacts(Path(temporary))
            self._persist_evaluation(registry, result)
            event = registry.promote_if_eligible(result["candidate_id"], result["evaluation_id"], gates)
            self.assertEqual(event.action, "promote", event.reason_codes)
            self.assertEqual(event.reason_codes, ())
            self.assertEqual(registry.active("risk")["model_ref"], result["candidate_model_ref"])
            self.assertEqual(registry.candidate(result["candidate_id"])["status"], "promoted")
            self.assertEqual([row["action"] for row in registry.history("risk")], ["promote"])

    def test_calibrator_for_another_labeling_policy_is_rejected_with_verified_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            registry, result, gates = self._verified_promotion_artifacts(Path(temporary))
            model = result["models"][0]
            path = Path(model["calibrator_path"])
            artifact = replace(CalibrationArtifact.load(path), policy_id="other-labeling-policy")
            path.unlink()
            artifact.save(path)
            model["calibrator_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            self._persist_evaluation(registry, result)
            event = registry.promote_if_eligible(result["candidate_id"], result["evaluation_id"], gates)
            self.assertEqual(event.action, "reject")
            self.assertIn("holdout_metric_evidence_invalid", event.reason_codes)
            self.assertIn("candidate_model_or_calibrator_artifact_mismatch", event.reason_codes)
            self.assertIsNone(registry.active("risk"))
            self.assertEqual(registry.candidate(result["candidate_id"])["status"], "rejected")
            self.assertEqual([row["action"] for row in registry.history("risk")], ["reject"])

    def test_missing_labeling_policy_rejects_verified_candidate_without_pointer_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry, result, gates = self._verified_promotion_artifacts(root)
            (root / "risk-policy.json").unlink()
            self._persist_evaluation(registry, result)
            event = registry.promote_if_eligible(result["candidate_id"], result["evaluation_id"], gates)
            self.assertEqual(event.action, "reject")
            self.assertIn("holdout_metric_evidence_invalid", event.reason_codes)
            self.assertIn("candidate_model_or_calibrator_artifact_mismatch", event.reason_codes)
            self.assertIsNone(registry.active("risk"))
            self.assertEqual([row["action"] for row in registry.history("risk")], ["reject"])


if __name__ == "__main__":
    unittest.main()
