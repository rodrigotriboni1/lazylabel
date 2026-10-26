import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from finlabel.labeling.policy import LabelingPolicy
from finlabel.labeling.prediction import Prediction, PredictionError
from finlabel.labeling.task import LabelTask
from finlabel.training.dataset import prepare_trusted_dataset
from finlabel.training.local_evaluator import _metrics, _read_partition, _score
from finlabel.training.registry import PromotionPolicy, _derive_holdout_metrics, _promotion_reasons, _validate_holdout_row_binding
from finlabel.training.trusted_labels import TrustedLabelBatch, TrustedLabelRecord
from finlabel.models.text_generation import RAW_SCORE_METHOD


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


if __name__ == "__main__":
    unittest.main()
