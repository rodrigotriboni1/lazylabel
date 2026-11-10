import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from lazylabel.labeling.service import _prompt
from lazylabel.labeling.policy import LabelingPolicy
from lazylabel.labeling.task import LabelTask
from lazylabel.models.text_generation import TransformersTextGenerationBackend
from lazylabel.training.backend import _artifact_tree_sha256, format_training_example
from lazylabel.training.active_model import active_inference


class FakeTensor:
    def __init__(self, values):
        self.values = values
        self.shape = (len(values), len(values[0]))

    def __getitem__(self, index):
        return self.values[index]


class FakeInputs(dict):
    def to(self, device):
        return self


class FakeTokenizer:
    def __init__(self, chat_template=True):
        self.chat_template = "fake-template" if chat_template else None
        self.messages = None
        self.encoded = None

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        self.messages = messages
        return "<chat>{}</chat>".format(messages[0]["content"])

    def __call__(self, prompt, *, return_tensors, add_special_tokens=True):
        self.encoded = (prompt, add_special_tokens)
        return FakeInputs(input_ids=FakeTensor([[1, 2]]))

    def decode(self, tokens, *, skip_special_tokens):
        return '{"label":"receita"}'


class FakeModel:
    device = "cpu"

    def to(self, device):
        return self

    def eval(self):
        return self

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return FakeTensor([[1, 2, 3]])


class FakeTorch:
    class inference_mode:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False


def task_and_policy():
    task = LabelTask("risk", "Classify record", ("memo",), ("receita", "despesa"), "org/model", "rev-a")
    policy = LabelingPolicy("policy-a", "risk", ("receita", "despesa"), "rules-v1", "cal-a", 0.8, 3600,
                            ({"field": "memo", "operator": "not_empty"},))
    return task, policy


class ChatTemplateTests(unittest.TestCase):
    def _run(self, tokenizer):
        backend = TransformersTextGenerationBackend("org/model", "rev-a", device="cpu")
        model = FakeModel()
        backend._tokenizer = tokenizer
        backend._model = model
        with patch.dict("sys.modules", {"torch": FakeTorch}):
            result = backend.generate("Classify this record", max_new_tokens=16)
        return result, model

    def test_generation_formats_prompt_with_chat_template_and_greedy_settings(self):
        tokenizer = FakeTokenizer()
        result, model = self._run(tokenizer)
        self.assertEqual(result, '{"label":"receita"}')
        self.assertEqual(tokenizer.messages, [{"role": "user", "content": "Classify this record"}])
        self.assertEqual(tokenizer.encoded, ("<chat>Classify this record</chat>", False))
        self.assertEqual(model.kwargs["max_new_tokens"], 16)
        self.assertFalse(model.kwargs["do_sample"])

    def test_generation_falls_back_to_plain_text_without_chat_template(self):
        tokenizer = FakeTokenizer(chat_template=False)
        self._run(tokenizer)
        self.assertIsNone(tokenizer.messages)
        self.assertEqual(tokenizer.encoded, ("Classify this record", True))

    def test_verified_adapter_enforces_recorded_generation_length(self):
        backend = TransformersTextGenerationBackend(
            "org/model", "rev-a", device="cpu", adapter_path="/tmp/adapter",
            generation_config={"do_sample": False, "max_new_tokens": 32,
                               "raw_score_method": "label_json_mean_log_likelihood_v2"},
        )
        with self.assertRaisesRegex(ValueError, "(?i)generation length"):
            backend.generate("Classify", max_new_tokens=16)

    def test_task_prompt_contains_only_selected_columns(self):
        task, _ = task_and_policy()
        prompt = _prompt(task, {"memo": "customer payment"})
        self.assertIn('"memo":"customer payment"', prompt)
        self.assertNotIn("account_number", prompt)
        self.assertNotIn("998877", prompt)

    def test_training_uses_the_same_chat_template_and_preserves_prompt_completion(self):
        tokenizer = FakeTokenizer()
        example = format_training_example({"prompt": "Classify row", "completion": '{"label":"receita"}'}, tokenizer)
        self.assertEqual(example, {"prompt": "<chat>Classify row</chat>", "completion": '{"label":"receita"}'})
        self.assertEqual(tokenizer.messages, [{"role": "user", "content": "Classify row"}])

    def test_training_keeps_plain_text_fallback_without_template(self):
        tokenizer = FakeTokenizer(chat_template=False)
        example = format_training_example({"prompt": "Classify row", "completion": '{"label":"receita"}'}, tokenizer)
        self.assertEqual(example, {"prompt": "Classify row", "completion": '{"label":"receita"}'})


class ActiveModelArtifactTests(unittest.TestCase):
    def _project(self, root):
        task, policy = task_and_policy()
        models = root / "models"
        models.mkdir()
        adapter = models / "adapter"
        adapter.mkdir()
        (adapter / "adapter_model.safetensors").write_bytes(b"local fake weights")
        (adapter / "tokenizer_config.json").write_text('{"chat_template":"qwen-like"}', encoding="utf-8")
        (adapter / "adapter_config.json").write_text(json.dumps({
            "base_model_name_or_path": "org/model", "revision": "rev-a",
        }), encoding="utf-8")
        base_ref = "org/model@rev-a"
        metadata = {"base_model_ref": base_ref, "generation": {
            "do_sample": False, "max_new_tokens": 256,
            "raw_score_method": "label_json_mean_log_likelihood_v2",
        }}
        (adapter / "lazylabel-training.json").write_text(json.dumps(metadata), encoding="utf-8")
        digest = _artifact_tree_sha256(adapter)
        metadata["adapter_artifacts_sha256"] = digest
        (adapter / "lazylabel-training.json").write_text(json.dumps(metadata), encoding="utf-8")
        model_ref = "{}+peft:{}".format(base_ref, digest)
        calibrator_path = models / "calibrator.json"
        calibrator_path.write_text("{}", encoding="utf-8")
        pointer = {task.task_id: {"adapter_path": str(adapter), "calibrator_path": str(calibrator_path),
                                 "model_ref": model_ref}}
        (models / "active-models.json").write_text(json.dumps(pointer), encoding="utf-8")
        return SimpleNamespace(workspace_dir=root), task, policy, adapter, calibrator_path, model_ref

    def test_loads_only_matching_adapter_base_revision_and_calibrator(self):
        from lazylabel.training.evaluation import labeling_policy_sha256
        from lazylabel.training.task_spec import task_spec_sha256

        with tempfile.TemporaryDirectory() as temporary:
            project, task, policy, adapter, calibrator_path, model_ref = self._project(Path(temporary))
            calibrator = SimpleNamespace(task_id=task.task_id, model_ref=model_ref,
                                         policy_id=policy.policy_id, calibration_ref=policy.calibration_ref,
                                         task_spec_sha256=task_spec_sha256(task), labels=tuple(task.labels),
                                         source_hashes={"labeling_policy_sha256": labeling_policy_sha256(policy)})
            with patch("lazylabel.training.active_model.CalibrationArtifact.load", return_value=calibrator):
                backend, loaded_calibrator = active_inference(project, task, policy, device="cpu")
            self.assertEqual(Path(backend.adapter_path), adapter.resolve())
            self.assertEqual(backend.generation_config["max_new_tokens"], 256)
            self.assertIs(loaded_calibrator, calibrator)

            from types import ModuleType
            transformers = ModuleType("transformers")
            tokenizer_calls = []
            class AutoTokenizerFake:
                @staticmethod
                def from_pretrained(model_ref, **kwargs):
                    tokenizer_calls.append((model_ref, kwargs))
                    return FakeTokenizer()
            class AutoModelFake:
                @staticmethod
                def from_pretrained(model_ref, **kwargs):
                    self.assertEqual(model_ref, "org/model")
                    return FakeModel()
            transformers.AutoTokenizer = AutoTokenizerFake
            transformers.AutoModelForCausalLM = AutoModelFake
            peft = ModuleType("peft")
            class PeftModelFake:
                @staticmethod
                def from_pretrained(model, adapter_path, **kwargs):
                    self.assertEqual(Path(adapter_path), adapter.resolve())
                    return model
            peft.PeftModel = PeftModelFake
            with patch.dict("sys.modules", {"transformers": transformers, "peft": peft}):
                backend._load()
            self.assertEqual(tokenizer_calls[0][0], str(adapter.resolve()))
            self.assertTrue(tokenizer_calls[0][1]["local_files_only"])

    def test_rejects_adapter_revision_mismatch_corrupt_artifact_and_missing_calibrator(self):
        from lazylabel.training.evaluation import labeling_policy_sha256
        from lazylabel.training.task_spec import task_spec_sha256

        with tempfile.TemporaryDirectory() as temporary:
            project, task, policy, adapter, calibrator_path, model_ref = self._project(Path(temporary))
            calibrator = SimpleNamespace(task_id=task.task_id, model_ref=model_ref,
                                         policy_id=policy.policy_id, calibration_ref=policy.calibration_ref,
                                         task_spec_sha256=task_spec_sha256(task), labels=tuple(task.labels),
                                         source_hashes={"labeling_policy_sha256": labeling_policy_sha256(policy)})
            metadata_path = adapter / "lazylabel-training.json"
            metadata = json.loads(metadata_path.read_text())
            metadata_path.write_text("{malformed", encoding="utf-8")
            with self.assertRaises(ValueError):
                active_inference(project, task, policy)

            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            metadata["generation"]["raw_score_method"] = "legacy-score"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "generation_contract"):
                active_inference(project, task, policy)

            metadata["generation"]["raw_score_method"] = "label_json_mean_log_likelihood_v2"
            metadata["base_model_ref"] = "org/model@old-revision"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "(?i)mismatch"):
                active_inference(project, task, policy)

            metadata["base_model_ref"] = "org/model@rev-a"
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            (adapter / "adapter_model.safetensors").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "(?i)mismatch"):
                active_inference(project, task, policy)

            second_root = Path(temporary) / "second"
            second_root.mkdir()
            project, task, policy, adapter, calibrator_path, model_ref = self._project(second_root)
            with patch("lazylabel.training.active_model.CalibrationArtifact.load", return_value=calibrator):
                (Path(project.workspace_dir) / "models" / "active-models.json").write_text(json.dumps({task.task_id: {
                    "adapter_path": str(adapter), "calibrator_path": str(Path(temporary) / "absent.json"),
                    "model_ref": model_ref}}))
                with self.assertRaisesRegex(ValueError, "(?i)missing"):
                    active_inference(project, task, policy)

    def test_rejects_calibrator_bound_to_another_policy_or_model(self):
        from lazylabel.training.evaluation import labeling_policy_sha256
        from lazylabel.training.task_spec import task_spec_sha256

        with tempfile.TemporaryDirectory() as temporary:
            project, task, policy, *_ = self._project(Path(temporary))
            calibrator = SimpleNamespace(task_id=task.task_id, model_ref="other-model", policy_id="other-policy",
                                         calibration_ref="other-calibration", labels=tuple(task.labels),
                                         task_spec_sha256=task_spec_sha256(task),
                                         source_hashes={"labeling_policy_sha256": labeling_policy_sha256(policy)})
            with patch("lazylabel.training.active_model.CalibrationArtifact.load", return_value=calibrator):
                with self.assertRaisesRegex(ValueError, "(?i)calibrator.*identity"):
                    active_inference(project, task, policy)

    def test_rejects_corrupted_calibrator_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            project, task, policy, _adapter, calibrator_path, _model_ref = self._project(Path(temporary))
            calibrator_path.write_text('{"tampered":true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "(?i)calibration artifact"):
                active_inference(project, task, policy)

    def test_calibrated_score_requires_the_exact_model_task_and_policy_identity(self):
        from lazylabel.labeling.prediction import Prediction
        from lazylabel.training.evaluation import (
            CALIBRATOR_METHOD, SUPPORTED_SCORE_METHOD, CalibrationArtifact, labeling_policy_sha256,
        )
        from lazylabel.training.task_spec import task_spec_sha256

        task, policy = task_and_policy()
        digest = "a" * 64
        artifact = CalibrationArtifact(
            task_id=task.task_id,
            task_spec_sha256=task_spec_sha256(task),
            policy_id=policy.policy_id,
            model_ref="model-v1",
            confidence_method=SUPPORTED_SCORE_METHOD,
            calibration_ref=policy.calibration_ref,
            calibrator_method=CALIBRATOR_METHOD,
            parameters={"slope": 1.0, "intercept": 0.0, "mean": 0.0, "scale": 1.0},
            source_hashes={
                "task_spec_sha256": task_spec_sha256(task),
                "labeling_policy_sha256": labeling_policy_sha256(policy),
                "calibration_manifest_sha256": digest,
                "calibration_partition_sha256": digest,
                "calibration_dataset_sha256": digest,
                "calibration_scores_sha256": digest,
                "trusted_labels_sha256": digest,
            },
            metrics={"brier_score": 0.2, "row_count": 6, "correct_count": 3},
            labels=tuple(task.labels),
        )
        prediction = Prediction("receita", None, {"receita": 0.7, "despesa": 0.2}, None, None,
                                SUPPORTED_SCORE_METHOD, "b" * 64)
        calibrated = artifact.calibrate(prediction, task=task, policy=policy, model_ref="model-v1")
        self.assertGreater(calibrated.confidence, 0.5)
        with self.assertRaisesRegex(ValueError, "identity"):
            artifact.calibrate(prediction, task=task, policy=policy, model_ref="other-model")


if __name__ == "__main__":
    unittest.main()
