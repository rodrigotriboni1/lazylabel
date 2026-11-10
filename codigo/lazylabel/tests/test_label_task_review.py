import json
import tempfile
import unittest
from pathlib import Path

from lazylabel.adapters.outbound.persistence.tasks import LabelTask, load_task, save_task, task_file_path
from lazylabel.adapters.outbound.persistence.reviews import ReviewAction, ReviewLog


class LabelTaskReviewTests(unittest.TestCase):
    def test_task_storage_path_rejects_traversal_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "safe filename"):
                task_file_path(temporary, "../../outside")

    def test_task_round_trip_validates_selected_columns_and_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tasks" / "risk.json"
            task = LabelTask("risk", "Classify risk", ("amount",), ("low", "high"), "local/model")
            save_task(task, path)
            self.assertEqual(load_task(path, available_columns=("amount", "private")), task)
            with self.assertRaisesRegex(ValueError, "unknown"):
                load_task(path, available_columns=("private",))
            with self.assertRaisesRegex(ValueError, "unique"):
                LabelTask("risk", "Classify risk", ("amount",), ("low", "low"), "local/model")

    def test_review_log_reads_v1_and_appends_v2_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "review.jsonl"
            legacy = {
                "event_id": "legacy-event", "schema_version": 1, "record_id": "row-1",
                "suggested_label": "low", "action": "accepted", "final_label": "low",
                "model_ref": "model@rev", "created_at": "2026-10-19T00:00:00Z",
            }
            path.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
            log = ReviewLog(path)
            event = log.record(
                "row-2", "low", ReviewAction.ACCEPTED, "low", "model@rev",
                run_id="run-1", source_name="ledger", task_id="risk", input_digest="a" * 64,
                suggestion_id="suggestion-2",
            )

            events = log.read()

            self.assertEqual([item.schema_version for item in events], [1, 2])
            self.assertIsNone(events[0].input_digest)
            self.assertEqual(event.task_id, "risk")
            self.assertEqual(events[1].input_digest, "a" * 64)

    def test_review_log_reports_malformed_event_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "review.jsonl"
            valid = {
                "event_id": "event-1", "schema_version": 1, "record_id": "row-1",
                "suggested_label": "low", "action": "accepted", "final_label": "low",
                "model_ref": None, "created_at": "2026-10-19T00:00:00Z",
            }
            path.write_text(json.dumps(valid) + "\nnot-json\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                ReviewLog(path).read()

    def test_boolean_schema_version_is_not_treated_as_legacy_version_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "review.jsonl"
            event = {
                "event_id": "event-1", "schema_version": True, "record_id": "row-1",
                "suggested_label": "low", "action": "accepted", "final_label": "low",
                "model_ref": None, "created_at": "2026-10-19T00:00:00Z",
            }
            path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                ReviewLog(path).read()


if __name__ == "__main__":
    unittest.main()
