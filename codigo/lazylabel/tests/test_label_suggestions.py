import json
import tempfile
import unittest
from pathlib import Path

from lazylabel.adapters.outbound.models.labeling import suggest_labels
from lazylabel.adapters.outbound.persistence.suggestions import verify_suggestions_file
from lazylabel.adapters.outbound.persistence.tasks import LabelTask
from lazylabel.adapters.outbound.sources.base import SourceSpec
from lazylabel.adapters.outbound.sources.csv_source import CsvSource


class MockBackend:
    model_id = "mock-local"

    def __init__(self):
        self.responses = ['{"label":"low","rationale":"within range"}', 'not json', '{"label":"unknown"}']
        self.prompts = []

    def generate(self, prompt, *, max_new_tokens):
        self.prompts.append(prompt)
        return self.responses.pop(0)


class LabelSuggestionTests(unittest.TestCase):
    def test_suggestion_run_stores_only_selected_fields_digest_and_valid_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "ledger.csv"
            source_path.write_text("amount,private\n10,SECRET_VALUE\n20,SECRET_VALUE\n30,SECRET_VALUE\n", encoding="utf-8")
            source = CsvSource(SourceSpec("ledger", "csv", source_path))
            task = LabelTask("risk", "Classify risk", ("amount",), ("low", "high"), "mock-local")
            backend = MockBackend()

            run = suggest_labels(source, task, backend, workspace_dir=root / ".lazylabel")

            self.assertEqual((run.row_count, run.invalid_count), (1, 2))
            stored = run.suggestion_path.read_text(encoding="utf-8")
            suggestion = json.loads(stored)
            self.assertEqual(suggestion["label"], "low")
            self.assertNotIn("SECRET_VALUE", stored)
            self.assertNotIn('"private"', backend.prompts[0])
            self.assertEqual(len(suggestion["input_digest"]), 64)

    def test_rejects_sources_without_stable_ids_before_model_calls(self):
        class AggregateOnly:
            spec = SourceSpec("aggregate", "sqlite", Path("unused"))

            def capabilities(self):
                from lazylabel.adapters.outbound.sources.base import SourceCapabilities
                return SourceCapabilities(False, True, True, True)

        backend = MockBackend()
        task = LabelTask("risk", "Classify risk", ("amount",), ("low", "high"), "mock-local")
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(ValueError, "stable"):
            suggest_labels(AggregateOnly(), task, backend, workspace_dir=Path(temporary))
        self.assertEqual(backend.prompts, [])

    def test_detects_suggestion_file_tampering_before_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "ledger.csv"
            source_path.write_text("amount\n10\n", encoding="utf-8")
            source = CsvSource(SourceSpec("ledger", "csv", source_path))
            task = LabelTask("risk", "Classify risk", ("amount",), ("low", "high"), "mock-local")
            run = suggest_labels(source, task, MockBackend(), workspace_dir=root / ".lazylabel")
            metadata = json.loads((run.suggestion_path.parent / "run.json").read_text())
            run.suggestion_path.write_text(run.suggestion_path.read_text().replace('"low"', '"high"'), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "changed"):
                verify_suggestions_file(run.suggestion_path, metadata["suggestions_sha256"])


if __name__ == "__main__":
    unittest.main()
