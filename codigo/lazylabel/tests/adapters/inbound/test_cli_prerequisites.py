import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace

from lazylabel.adapters.inbound.cli import commands

STUB = [{"check": "labeling_policy", "status": "missing"}]


def forbidden():
    raise AssertionError("prerequisites must not be computed")


def run(argv, **methods):
    output = io.StringIO()
    with redirect_stdout(output):
        status = commands.main(argv, application=SimpleNamespace(**methods))
    assert status == 0
    return json.loads(output.getvalue())


def pipeline(reason_counts, state="completed"):
    return {"task_id": "t", "labels": {"reason_counts": reason_counts}, "training": {"state": state}}


class CliPrerequisitesTriggerTests(unittest.TestCase):
    def label(self, reason_counts, prerequisites, policy_id="p"):
        return run(["label", "s", "--task", "t"], prerequisites=prerequisites,
            label=lambda *a, **k: {"task_id": "t", "policy_id": policy_id, "reason_counts": reason_counts})

    def test_label_uncalibrated_dominant_or_tied(self):
        for counts in ({"uncalibrated": 3, "low_confidence": 1}, {"uncalibrated": 2, "low_confidence": 2}):
            self.assertEqual(self.label(counts, lambda task: STUB)["prerequisites"], STUB)

    def test_label_without_policy(self):
        self.assertEqual(self.label({"missing_policy": 2}, lambda task: STUB, policy_id=None)["prerequisites"], STUB)

    def test_label_no_trigger(self):
        self.assertNotIn("prerequisites", self.label({"low_confidence": 3, "uncalibrated": 1}, forbidden))

    def test_run_and_status_triggers(self):
        for counts, state in (({"uncalibrated": 2}, "completed"), ({"missing_policy": 1, "applied": 1}, "completed"),
                              ({"applied": 2}, "blocked")):
            result = pipeline(counts, state)
            self.assertEqual(run(["run", "--task", "t", "--source", "s"], prerequisites=lambda task: STUB,
                pipeline=lambda *a, **k: dict(result))["prerequisites"], STUB)
            self.assertEqual(run(["run-status", "r"], prerequisites=lambda task: STUB,
                pipeline_status=lambda run_id: dict(result))["prerequisites"], STUB)

    def test_run_no_trigger(self):
        result = pipeline({"applied": 3, "uncalibrated": 1})
        self.assertNotIn("prerequisites", run(["run", "--task", "t", "--source", "s"],
            prerequisites=forbidden, pipeline=lambda *a, **k: dict(result)))
