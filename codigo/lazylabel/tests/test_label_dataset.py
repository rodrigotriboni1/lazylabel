import json
import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lazylabel.labeling.service import suggest_labels
from lazylabel.labeling.task import LabelTask, save_task
from lazylabel.review import ReviewAction, ReviewLog
from lazylabel.sources.base import SourceSpec
from lazylabel.sources.csv_source import CsvSource
from lazylabel.project import init_project, load_project, save_project


class FixedBackend:
    model_id = "mock-local"

    def __init__(self):
        self.index = 0

    def generate(self, prompt, *, max_new_tokens):
        self.index += 1
        return json.dumps({"label": "low" if self.index == 1 else "high"})


class LabelDatasetTests(unittest.TestCase):
    def test_historical_review_artifacts_remain_exportable(self):
        from lazylabel.cli import main

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_project(root)
            source_path = root / "ledger.csv"
            source_path.write_text("id,amount,private\na,10,SECRET\nb,20,SECRET\n", encoding="utf-8")
            config = load_project(root)
            config.sources["ledger"] = SourceSpec("ledger", "csv", source_path, schema={"id": "string"})
            save_project(config, config.path)
            backend = FixedBackend()
            task = LabelTask("risk", "Classify risk", ("amount",), ("low", "high"), "mock-local")
            save_task(task, config.workspace_dir / "tasks" / "risk.json")
            run = suggest_labels(CsvSource(config.sources["ledger"]), task, backend,
                                 workspace_dir=config.workspace_dir)
            suggestions = [json.loads(line) for line in run.suggestion_path.read_text().splitlines()]
            legacy = ReviewLog(config.workspace_dir / "review.jsonl")
            legacy.record(suggestions[0]["record_id"], suggestions[0]["label"], ReviewAction.ACCEPTED,
                          suggestions[0]["label"], suggestions[0]["model_ref"], run_id=run.run_id,
                          source_name="ledger", task_id="risk", input_digest=suggestions[0]["input_digest"],
                          suggestion_id=suggestions[0]["suggestion_id"])
            output = root / ".lazylabel" / "training" / "cli.jsonl"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["dataset", "prepare", run.run_id, "--output", str(output), "--project", str(root)]), 0)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(json.loads(rows[0]["completion"])["label"], "low")
            self.assertNotIn("SECRET", output.read_text())

    def test_interactive_review_cli_command_is_retired(self):
        from lazylabel.cli import main

        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main(["review", "a" * 32])
        self.assertEqual(error.exception.code, 2)

    def test_export_includes_only_latest_accepted_or_corrected_review_and_selected_fields(self):
        from lazylabel.training.dataset import prepare_training_dataset

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_project(root)
            source_path = root / "ledger.csv"
            source_path.write_text("id,amount,private\na,10,SECRET\nb,20,SECRET\n", encoding="utf-8")
            config = load_project(root)
            config.sources["ledger"] = SourceSpec("ledger", "csv", source_path, schema={"id": "string"})
            save_project(config, config.path)
            task = LabelTask("risk", "Classify risk", ("amount",), ("low", "high"), "mock-local")
            save_task(task, config.workspace_dir / "tasks" / "risk.json")
            source = CsvSource(config.sources["ledger"])
            run = suggest_labels(source, task, FixedBackend(), workspace_dir=config.workspace_dir)
            suggestions = [json.loads(line) for line in run.suggestion_path.read_text().splitlines()]
            review = ReviewLog(config.workspace_dir / "review.jsonl")
            review.record(
                suggestions[0]["record_id"], suggestions[0]["label"], ReviewAction.ACCEPTED, suggestions[0]["label"],
                suggestions[0]["model_ref"], run_id=run.run_id, source_name="ledger", task_id="risk",
                input_digest=suggestions[0]["input_digest"], suggestion_id=suggestions[0]["suggestion_id"],
            )
            review.record(
                suggestions[1]["record_id"], suggestions[1]["label"], ReviewAction.CORRECTED, "low",
                suggestions[1]["model_ref"], run_id=run.run_id, source_name="ledger", task_id="risk",
                input_digest=suggestions[1]["input_digest"], suggestion_id=suggestions[1]["suggestion_id"],
            )
            output = root / "training.jsonl"

            manifest = prepare_training_dataset(config, run.run_id, output)

            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual([json.loads(row["completion"])["label"] for row in rows], ["low", "low"])
            self.assertEqual(manifest.row_count, 2)
            self.assertEqual(manifest.selected_columns, ("amount",))
            self.assertNotIn("SECRET", output.read_text())
            self.assertTrue(output.with_suffix(".jsonl.manifest.json").exists())
            with self.assertRaises(FileExistsError):
                prepare_training_dataset(config, run.run_id, output)


if __name__ == "__main__":
    unittest.main()
