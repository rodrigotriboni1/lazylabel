import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from lazylabel.adapters.outbound.training.backend import TrainingConfig, TrainingResult
from lazylabel.adapters.outbound.training.jobs import TrainingJobManager


class TrainingJobTests(unittest.TestCase):
    def make_project(self, root):
        dataset = root / "examples.jsonl"
        dataset.write_text('{"prompt":"Classify amount 10","completion":"low"}\n', encoding="utf-8")
        dataset.with_suffix(".jsonl.manifest.json").write_text(json.dumps({
            "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(), "row_count": 1,
            "model_ref": "local/model", "task_id": "risk",
        }), encoding="utf-8")
        gate = {"model_id": "local/model", "license": "approved", "hardware": "local", "data_policy": "local",
                "evaluation_protocol": "held out", "authorized": True}
        (root / "training-gate.json").write_text(json.dumps(gate), encoding="utf-8")
        config = TrainingConfig("local/model", None, root / "adapter", 1, 1, 0.0001, 8, 42)
        return dataset, config

    def test_manager_persists_sanitized_status_from_shared_training_service(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset, config = self.make_project(root)
            manager = TrainingJobManager(root)
            with patch("lazylabel.adapters.outbound.training.jobs.train_adapter", return_value=TrainingResult(
                config.output_dir, "local/model", hashlib.sha256(dataset.read_bytes()).hexdigest(), (), {"loss": 0.5},
            )):
                job_id = manager.submit(dataset, config)
                deadline = time.monotonic() + 2
                while manager.get(job_id).state not in {"succeeded", "failed"} and time.monotonic() < deadline:
                    time.sleep(0.01)
            status = manager.get(job_id)
            self.assertEqual(status.state, "succeeded")
            self.assertEqual(status.final_metrics, {"loss": 0.5})
            saved = root / "training" / "jobs" / (job_id + ".json")
            self.assertTrue(saved.exists())
            self.assertNotIn("prompt", saved.read_text())

    def test_gate_failure_prevents_job_creation_and_worker_start(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset, config = self.make_project(root)
            (root / "training-gate.json").unlink()
            manager = TrainingJobManager(root)
            with patch("lazylabel.adapters.outbound.training.jobs.train_adapter") as train:
                with self.assertRaisesRegex(ValueError, "training gate"):
                    manager.submit(dataset, config)
                train.assert_not_called()
            self.assertFalse(manager.jobs_dir.exists())

    def test_process_restart_marks_previous_running_job_failed_without_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs_dir = root / "training" / "jobs"
            jobs_dir.mkdir(parents=True)
            job_id = "b" * 32
            (jobs_dir / (job_id + ".json")).write_text(json.dumps({
                "job_id": job_id, "state": "running", "progress": "running", "error": None,
                "dataset_path": str(root / "data.jsonl"), "output_dir": str(root / "adapter"),
                "model_id": "local/model", "dataset_sha256": "a" * 64,
                "created_at": "2026-10-19T00:00:00Z", "final_metrics": {},
            }), encoding="utf-8")

            status = TrainingJobManager(root).get(job_id)

            self.assertEqual(status.state, "failed")
            self.assertIn("No job was resumed", status.error)


if __name__ == "__main__":
    unittest.main()
