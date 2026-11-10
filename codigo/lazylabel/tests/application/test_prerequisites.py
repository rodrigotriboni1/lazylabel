import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lazylabel.bootstrap.application import build_application
from lazylabel.bootstrap.cli import run as main
from lazylabel.adapters.outbound.persistence.projects import init_project

CHECKS = ["labeling_policy", "trusted_label_source", "training_gate", "promotion_policy", "calibrator"]
POLICY = {
    "policy_id": "risk-v1", "task_id": "risk", "allowed_labels": ["low", "high"], "rules_version": "1",
    "rules": [{"field": "amount", "operator": "number_between", "minimum": 0}],
    "calibration_ref": "calibration-1", "min_calibrated_confidence": 0.8, "max_staleness_seconds": 30,
}


def cli(arguments):
    output, errors = io.StringIO(), io.StringIO()
    with redirect_stdout(output), redirect_stderr(errors):
        status = main(arguments)
    return status, output.getvalue(), errors.getvalue()


class PrerequisitesTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        init_project(self.root)
        self.csv = self.root / "ledger.csv"
        self.csv.write_text("amount,class\n10,ROW_VALUE_SECRET\n20,ROW_VALUE_SECRET\n", encoding="utf-8")
        self.task = {"task_id": "risk", "instructions": "x", "input_columns": ["amount"],
                     "labels": ["low", "high"], "model_id": "unused-local-model"}
        self.add_task(self.task)
        for command in (["source", "add-csv", "ledger", str(self.csv)],
                        ["source", "set-type", "ledger", "amount", "decimal"]):
            self.assertEqual(cli(command + ["--project", str(self.root)])[0], 0)
        self.workspace = self.root / ".lazylabel"

    def add_task(self, task):
        path = self.root / "task.json"
        path.write_text(json.dumps(task), encoding="utf-8")
        self.assertEqual(cli(["task", "add", str(path), "--project", str(self.root)])[0], 0)

    def prerequisites(self):
        return build_application(self.root).prerequisites("risk")

    def assert_private(self, items):
        text = json.dumps(items)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("ROW_VALUE_SECRET", text)

    def add_some(self):
        status, output, errors = cli(["supervision", "add", "ledger", "--task", "risk", "--label-column", "class",
            "--provenance", "p-v1", "--trust-kind", "provided_ground_truth",
            "--label-map", '{"ROW_VALUE_SECRET":"low"}', "--project", str(self.root)])
        self.assertEqual(status, 0, errors)
        (self.workspace / "training-gate.json").write_text("{}", encoding="utf-8")
        policies = self.workspace / "models" / "promotion-policies"
        policies.mkdir(parents=True)
        (policies / "risk.json").write_text("{}", encoding="utf-8")

    def test_all_missing_through_cli(self):
        status, output, errors = cli(["label", "ledger", "--task", "risk", "--project", str(self.root)])
        self.assertEqual(status, 0, errors)
        result = json.loads(output)
        self.assertIn("notice", result)
        self.assertEqual([item["check"] for item in result["prerequisites"]], CHECKS)
        for item in result["prerequisites"]:
            self.assertEqual(item["status"], "missing")
            self.assertIn("docs/verified-training-cycle.md", item["fix"])
        self.assert_private(result["prerequisites"])

    def test_some_present(self):
        self.add_some()
        items = {item["check"]: item for item in self.prerequisites()}
        for check in ("trusted_label_source", "training_gate", "promotion_policy"):
            self.assertEqual(items[check], {"check": check, "status": "present"})
        for check in ("labeling_policy", "calibrator"):
            self.assertEqual(items[check]["status"], "missing")
            self.assertIn("fix", items[check])
        self.assert_private(list(items.values()))

    def test_all_present(self):
        self.add_some()
        (self.root / "policy.json").write_text(json.dumps(POLICY), encoding="utf-8")
        (self.workspace / "tasks" / "risk.json").unlink()
        self.add_task({**self.task, "policy_path": str(self.root / "policy.json")})
        calibrator = self.workspace / "models" / "cal.json"
        calibrator.write_text("{}", encoding="utf-8")
        (self.workspace / "models" / "active-models.json").write_text(
            json.dumps({"risk": {"calibrator_path": str(calibrator)}}), encoding="utf-8")
        items = self.prerequisites()
        self.assertEqual(items, [{"check": check, "status": "present"} for check in CHECKS])
        self.assert_private(items)

    def test_invalid_policy(self):
        (self.root / "policy.json").write_text("not json", encoding="utf-8")
        task_file = self.workspace / "tasks" / "risk.json"
        task = json.loads(task_file.read_text(encoding="utf-8"))
        task["policy_path"] = str(self.root / "policy.json")
        task_file.write_text(json.dumps(task), encoding="utf-8")
        item = self.prerequisites()[0]
        self.assertEqual((item["check"], item["status"]), ("labeling_policy", "invalid"))
        self.assertIn("fix", item)

    def test_malformed_active_pointer_counts_as_missing(self):
        (self.workspace / "models").mkdir(exist_ok=True)
        (self.workspace / "models" / "active-models.json").write_text("[", encoding="utf-8")
        self.assertEqual(self.prerequisites()[-1]["status"], "missing")

    def test_read_only(self):
        def snapshot():
            return {str(path): path.stat().st_mtime_ns for path in self.root.rglob("*")}
        before = snapshot()
        self.prerequisites()
        self.assertEqual(snapshot(), before)

    def test_run_prints_checklist_but_stores_nothing(self):
        status, output, errors = cli(["run", "--task", "risk", "--source", "ledger", "--project", str(self.root)])
        self.assertEqual(status, 0, errors)
        run = json.loads(output)
        self.assertEqual([item["check"] for item in run["prerequisites"]], CHECKS)
        self.assertEqual(cli(["run-status", run["run_id"], "--project", str(self.root)])[1], output)
        stored = list((self.workspace / "pipeline-runs").glob("*/run.json")) + list(
            (self.workspace / "label-runs").glob("*/run.json"))
        self.assertTrue(stored)
        for path in stored:
            self.assertNotIn("prerequisites", path.read_text(encoding="utf-8"))
        status, label_output, errors = cli(["label-run", run["label_run_id"], "--project", str(self.root)])
        self.assertEqual(status, 0, errors)
        self.assertNotIn("prerequisites", json.loads(label_output))
