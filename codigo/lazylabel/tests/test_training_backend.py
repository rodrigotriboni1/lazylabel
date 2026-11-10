import json
import tempfile
import unittest
import sys
from pathlib import Path

from lazylabel.adapters.outbound.training.backend import TrainingConfig, validate_training_request


class TrainingGateTests(unittest.TestCase):
    def test_importing_training_contract_does_not_import_model_runtimes(self):
        self.assertNotIn("torch", sys.modules)
        self.assertNotIn("transformers", sys.modules)

    def test_validates_dataset_without_model_load_and_requires_project_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / "examples.jsonl"
            dataset.write_text('{"prompt":"Classify amount 10","completion":"low"}\n', encoding="utf-8")
            dataset.with_suffix(".jsonl.manifest.json").write_text(json.dumps({
                "dataset_sha256": __import__("hashlib").sha256(dataset.read_bytes()).hexdigest(),
                "row_count": 1, "model_ref": "local/model", "task_id": "risk",
            }), encoding="utf-8")
            config = TrainingConfig("local/model", None, root / "adapter", 1, 1, 0.0001, 8, 42)
            with self.assertRaisesRegex(ValueError, "training gate"):
                validate_training_request(dataset, config, gate_path=root / "training-gate.json")
            gate = {"model_id": "local/model", "license": "approved license", "hardware": "CPU test",
                    "data_policy": "synthetic only", "evaluation_protocol": "held-out synthetic split", "authorized": True}
            (root / "training-gate.json").write_text(json.dumps(gate), encoding="utf-8")
            result = validate_training_request(dataset, config, gate_path=root / "training-gate.json")
            self.assertEqual(result["dataset_sha256"], json.loads(dataset.with_suffix(".jsonl.manifest.json").read_text())["dataset_sha256"])
            self.assertFalse(config.output_dir.exists())

    def test_rejects_malformed_training_examples_before_any_backend_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / "bad.jsonl"
            dataset.write_text('{"prompt":"only prompt"}\n', encoding="utf-8")
            dataset.with_suffix(".jsonl.manifest.json").write_text(json.dumps({
                "dataset_sha256": __import__("hashlib").sha256(dataset.read_bytes()).hexdigest(), "row_count": 1,
            }), encoding="utf-8")
            config = TrainingConfig("local/model", None, root / "adapter", 1, 1, 0.0001, 8, 42)
            with self.assertRaisesRegex(ValueError, "prompt and completion"):
                validate_training_request(dataset, config, gate_path=root / "gate.json")

    def test_training_revision_must_match_reviewed_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset = root / "examples.jsonl"
            dataset.write_text('{"prompt":"Classify amount 10","completion":"low"}\n', encoding="utf-8")
            dataset.with_suffix(".jsonl.manifest.json").write_text(json.dumps({
                "dataset_sha256": __import__("hashlib").sha256(dataset.read_bytes()).hexdigest(),
                "row_count": 1, "model_ref": "local/model@revision-a", "task_id": "risk",
            }), encoding="utf-8")
            gate = {"model_id": "local/model", "license": "approved", "hardware": "CPU",
                    "data_policy": "synthetic", "evaluation_protocol": "held-out", "authorized": True}
            gate_path = root / "training-gate.json"
            gate_path.write_text(json.dumps(gate), encoding="utf-8")
            wrong_revision = TrainingConfig("local/model", "revision-b", root / "wrong", 1, 1, 0.0001, 8, 42)
            with self.assertRaisesRegex(ValueError, "revision"):
                validate_training_request(dataset, wrong_revision, gate_path=gate_path)

            matching_revision = TrainingConfig("local/model", "revision-a", root / "matching", 1, 1, 0.0001, 8, 42)
            validate_training_request(dataset, matching_revision, gate_path=gate_path)


if __name__ == "__main__":
    unittest.main()
