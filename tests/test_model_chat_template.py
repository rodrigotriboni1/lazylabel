import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from finlabel.labeling.service import _prompt
from finlabel.labeling.task import LabelTask
from finlabel.models.text_generation import TransformersTextGenerationBackend
from finlabel.training.backend import format_training_example


class FakeTensor:
    def __init__(self, rows):
        self.rows = rows
        self.shape = (len(rows), len(rows[0]))

    def to(self, device):
        return self

    def __getitem__(self, index):
        return self.rows[index]


class FakeInputs(dict):
    def to(self, device):
        return self


class FakeTokenizer:
    def __init__(self, *, chat_template=True):
        self.chat_template = "fake-template" if chat_template else None
        self.messages = None
        self.add_generation_prompt = None
        self.encoded = None

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        self.messages = messages
        self.add_generation_prompt = add_generation_prompt
        return "<chat>" + messages[0]["content"] + "</chat>"

    def __call__(self, value, *, return_tensors):
        self.encoded = value
        return FakeInputs(input_ids=FakeTensor([[1, 2]]))

    def decode(self, tokens, *, skip_special_tokens):
        return '{"label":"receita"}'


class FakeModel:
    device = "cpu"

    def __init__(self):
        self.call = None

    def generate(self, **kwargs):
        self.call = kwargs
        return FakeTensor([[1, 2, 3]])


class ChatTemplateTests(unittest.TestCase):
    def _run(self, tokenizer):
        backend = TransformersTextGenerationBackend("local/model", device="cpu")
        model = FakeModel()
        backend._tokenizer = tokenizer
        backend._model = model
        result = backend.generate("Classify this record", max_new_tokens=16)
        return result, model

    def test_chat_template_renders_user_message_before_encoding(self):
        tokenizer = FakeTokenizer(chat_template=True)
        result, model = self._run(tokenizer)
        self.assertEqual(result, '{"label":"receita"}')
        self.assertEqual(tokenizer.messages, [{"role": "user", "content": "Classify this record"}])
        self.assertTrue(tokenizer.add_generation_prompt)
        self.assertEqual(tokenizer.encoded, "<chat>Classify this record</chat>")
        self.assertEqual(model.call["max_new_tokens"], 16)
        self.assertFalse(model.call["do_sample"])

    def test_models_without_chat_template_use_plain_prompt_fallback(self):
        tokenizer = FakeTokenizer(chat_template=False)
        self._run(tokenizer)
        self.assertIsNone(tokenizer.messages)
        self.assertEqual(tokenizer.encoded, "Classify this record")

    def test_training_prompt_uses_same_chat_template_and_keeps_completion_separate(self):
        tokenizer = FakeTokenizer(chat_template=True)
        row = format_training_example({"prompt": "Classify row", "completion": '{"label":"receita"}'}, tokenizer)
        self.assertEqual(row, {"prompt": "<chat>Classify row</chat>", "completion": '{"label":"receita"}'})
        self.assertTrue(tokenizer.add_generation_prompt)

    def test_prompt_serializes_only_task_selected_columns(self):
        task = LabelTask("expense", "Classify transaction", ("description",), ("receita", "despesa"), "local/model")
        prompt = _prompt(task, {"description": "supplier payment"})
        self.assertIn('"description":"supplier payment"', prompt)
        self.assertNotIn("account_number", prompt)
        self.assertNotIn("123456789", prompt)


class VerifiedAdapterTests(unittest.TestCase):
    def _artifact(self, root):
        adapter = root / "adapter"
        adapter.mkdir()
        (adapter / "adapter_model.safetensors").write_bytes(b"fake adapter weights")
        tokenizer_dir = adapter
        (tokenizer_dir / "tokenizer_config.json").write_text('{"chat_template":"sample"}', encoding="utf-8")
        from finlabel.training.active_model import adapter_sha256, tokenizer_sha256
        metadata = {
            "base_model_ref": "org/model@rev-a",
            "adapter_sha256": adapter_sha256(adapter),
            "tokenizer_sha256": tokenizer_sha256(adapter),
            "generation": {"do_sample": False, "max_new_tokens": 256},
        }
        (adapter / "finlabel-training.json").write_text(json.dumps(metadata), encoding="utf-8")
        calibrator = root / "calibrator.json"
        calibrator.write_text(json.dumps({
            "base_model_ref": metadata["base_model_ref"], "adapter_sha256": metadata["adapter_sha256"],
            "temperature": 1.0, "threshold": 0.8,
        }), encoding="utf-8")
        return adapter, calibrator, metadata

    def test_load_checks_base_revision_and_integrity_metadata(self):
        from finlabel.training.active_model import load_verified_adapter

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter, calibrator, _ = self._artifact(root)
            loaded = load_verified_adapter(adapter, "org/model", "rev-a", calibrator_path=calibrator)
            self.assertEqual(loaded["base_model_ref"], "org/model@rev-a")
            with self.assertRaisesRegex(ValueError, "base model"):
                load_verified_adapter(adapter, "org/model", "rev-b", calibrator_path=calibrator)

    def test_load_rejects_corrupted_metadata_missing_calibrator_and_changed_weights(self):
        from finlabel.training.active_model import load_verified_adapter

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter, calibrator, metadata = self._artifact(root)
            (adapter / "finlabel-training.json").write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "metadata"):
                load_verified_adapter(adapter, "org/model", "rev-a", calibrator_path=calibrator)
            (adapter / "finlabel-training.json").write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "calibrator"):
                load_verified_adapter(adapter, "org/model", "rev-a", calibrator_path=root / "missing.json")
            (adapter / "adapter_model.safetensors").write_bytes(b"tampered weights")
            with self.assertRaisesRegex(ValueError, "(?i)adapter integrity"):
                load_verified_adapter(adapter, "org/model", "rev-a", calibrator_path=calibrator)

    def test_calibrator_score_is_bound_to_model_and_adapter_identity(self):
        from finlabel.training.active_model import load_verified_adapter, calibrated_score

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter, calibrator, _ = self._artifact(root)
            loaded = load_verified_adapter(adapter, "org/model", "rev-a", calibrator_path=calibrator)
            self.assertAlmostEqual(calibrated_score(0.5, loaded), 0.5)
            calibrator.write_text(json.dumps({"base_model_ref": "org/model@rev-b", "adapter_sha256": "0" * 64,
                                              "temperature": 1.0, "threshold": 0.8}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "(?i)calibrator identity"):
                load_verified_adapter(adapter, "org/model", "rev-a", calibrator_path=calibrator)


if __name__ == "__main__":
    unittest.main()
