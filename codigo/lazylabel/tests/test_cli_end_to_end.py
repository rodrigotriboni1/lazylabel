import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from lazylabel.analysis.schema import AnalysisPlan, MetricSpec, TimeAxis, plan_to_dict
from lazylabel.cli import main
from lazylabel.adapters.inbound.cli.commands import main as inbound_cli_main
from lazylabel.project import init_project, load_project, save_project
from lazylabel.sources.base import SourceSpec


class AnalysisCliEndToEndTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(arguments)
        return status, output.getvalue() + errors.getvalue()

    def write_plan(self, root):
        path = root / "plan.json"
        path.write_text(json.dumps(plan_to_dict(AnalysisPlan(
            1, MetricSpec("sum", "amount"), ["product"], TimeAxis("period", "month"), [], "line",
        ))), encoding="utf-8")
        return path

    def test_csv_and_sqlite_analysis_monitoring_are_read_only_and_private(self):
        for kind in ("csv", "sqlite"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                init_project(root)
                project = load_project(root)
                schema = {"period": "date", "product": "string", "amount": "decimal", "private": "string"}
                if kind == "csv":
                    source_path = root / "sales.csv"
                    source_path.write_text(
                        "period,product,amount,private\n2025-01-03,A,10.25,RAW_ROW_SECRET\n"
                        "2025-02-04,B,12.50,RAW_ROW_SECRET\n",
                        encoding="utf-8",
                    )
                    project.sources["sales"] = SourceSpec("sales", "csv", source_path, schema=schema)
                else:
                    source_path = root / "sales.db"
                    connection = sqlite3.connect(source_path)
                    connection.execute("CREATE TABLE sales (period TEXT, product TEXT, amount TEXT, private TEXT)")
                    connection.executemany("INSERT INTO sales VALUES (?, ?, ?, ?)", [
                        ("2025-01-03", "A", "10.25", "RAW_ROW_SECRET"),
                        ("2025-02-04", "B", "12.50", "RAW_ROW_SECRET"),
                    ])
                    connection.commit()
                    connection.close()
                    project.sources["sales"] = SourceSpec("sales", "sqlite", source_path, table="sales", schema=schema)
                save_project(project, project.path)
                baseline = root / "schema.json"
                baseline.write_text(json.dumps({
                    "columns": {"period": "string", "product": "string",
                                "amount": "number" if kind == "csv" else "string"},
                    "required_columns": ["period", "product", "amount"],
                    "max_missing_ratio": {"amount": 0.0},
                    "allow_extra_columns": False,
                }), encoding="utf-8")
                plan_path = self.write_plan(root)
                original_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()

                status, monitor_output = self.run_cli([
                    "monitor", "sales", "--baseline", str(baseline), "--project", str(root),
                ])
                self.assertEqual(status, 0, monitor_output)
                findings = json.loads(monitor_output)
                self.assertEqual([finding["code"] for finding in findings], ["unexpected_column"])
                self.assertEqual(findings[0]["severity"], "warning")
                status, analyze_output = self.run_cli([
                    "analyze", "sales", "--question", "Monthly sales trend", "--plan", str(plan_path),
                    "--project", str(root),
                ])

                self.assertEqual(status, 0, analyze_output)
                summary = json.loads(analyze_output)
                self.assertEqual(summary["rows"], 2)
                self.assertEqual(summary["valid_row_count"], 2)
                artifact_dir = Path(summary["artifact_dir"])
                result = json.loads((artifact_dir / "result.json").read_text(encoding="utf-8"))
                self.assertEqual([row["value"] for row in result["rows"]], ["10.25", "12.50"])
                self.assertNotIn("RAW_ROW_SECRET", (artifact_dir / "result.json").read_text(encoding="utf-8"))
                self.assertNotIn("RAW_ROW_SECRET", (artifact_dir / "chart.html").read_text(encoding="utf-8"))
                self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), original_hash)

    def test_cli_rejects_missing_numeric_mapping_without_writing_analysis(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_project(root)
            csv_path = root / "sales.csv"
            csv_path.write_text("amount\n10\n", encoding="utf-8")
            project = load_project(root)
            project.sources["sales"] = SourceSpec("sales", "csv", csv_path)
            save_project(project, project.path)
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps({
                "version": 1, "metric": {"operation": "sum", "column": "amount"},
                "dimensions": [], "time_axis": None, "filters": [], "chart": "bar",
            }), encoding="utf-8")

            status, output = self.run_cli([
                "analyze", "sales", "--question", "Total", "--plan", str(plan_path), "--project", str(root),
            ])

            self.assertEqual(status, 2)
            self.assertIn("explicit type mapping", output)
            self.assertEqual(list((root / ".lazylabel" / "analyses").iterdir()), [])


class AutonomousCliEndToEndTests(unittest.TestCase):
    def run_cli(self, arguments):
        output = io.StringIO()
        errors = io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            status = main(arguments)
        return status, output.getvalue() + errors.getvalue()

    def test_model_status_reports_local_active_model_and_lifecycle_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_project(root)

            status, output = self.run_cli(["model-status", "risk", "--project", str(root)])

            self.assertEqual(status, 0, output)
            summary = json.loads(output)
            self.assertEqual(summary["task_id"], "risk")
            self.assertIsNone(summary["active_model"])
            self.assertEqual(summary["events"], [])
            self.assertNotIn(str(root), output)

    def test_run_and_status_quarantine_without_policy_and_link_blocked_training(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_project(root)
            source_path = root / "ledger.csv"
            source_path.write_text(
                "amount,private,class\n10,RAW_ROW_SECRET,G\n20,RAW_ROW_SECRET,B\n", encoding="utf-8")
            task_path = root / "task.json"
            task_path.write_text(json.dumps({
                "task_id": "risk", "instructions": "TASK_INSTRUCTION_SECRET",
                "input_columns": ["amount"], "labels": ["low", "high"], "model_id": "unused-local-model",
            }), encoding="utf-8")
            self.assertEqual(self.run_cli(["source", "add-csv", "ledger", str(source_path), "--project", str(root)])[0], 0)
            self.assertEqual(self.run_cli(["source", "set-type", "ledger", "amount", "decimal", "--project", str(root)])[0], 0)
            self.assertEqual(self.run_cli(["task", "add", str(task_path), "--project", str(root)])[0], 0)
            source_digest_before = hashlib.sha256(source_path.read_bytes()).hexdigest()
            status, supervision_output = self.run_cli([
                "supervision", "add", "ledger", "--task", "risk", "--label-column", "class",
                "--provenance", "synthetic-ground-truth-v1", "--trust-kind", "provided_ground_truth",
                "--label-map", '{"G":"low","B":"high"}', "--project", str(root),
            ])
            self.assertEqual(status, 0, supervision_output)
            registered = json.loads(supervision_output)
            self.assertEqual(registered["rows"], 2)
            self.assertEqual(len(registered["snapshot_sha256"]), 64)
            self.assertNotIn("RAW_ROW_SECRET", supervision_output)

            status, run_output = self.run_cli([
                "run", "--task", "risk", "--source", "ledger", "--project", str(root),
            ])

            self.assertEqual(status, 0, run_output)
            run = json.loads(run_output)
            self.assertEqual(run["labels"]["applied"], 0)
            self.assertEqual(run["labels"]["quarantined"], 2)
            self.assertEqual(run["training"]["state"], "blocked")
            self.assertIn("task_labeling_policy_missing", run["training"]["reason_codes"])
            status, status_output = self.run_cli([
                "run-status", run["run_id"], "--project", str(root),
            ])
            self.assertEqual(status, 0, status_output)
            self.assertEqual(json.loads(status_output), run)
            workspace = root / ".lazylabel"
            serialized = "".join(
                path.read_text(encoding="utf-8")
                for folder in ("label-runs", "pipeline-runs", "training/cycles")
                for path in (workspace / folder).rglob("*") if path.is_file()
            )
            self.assertNotIn("RAW_ROW_SECRET", serialized)
            self.assertNotIn("TASK_INSTRUCTION_SECRET", serialized)
            self.assertEqual(hashlib.sha256(source_path.read_bytes()).hexdigest(), source_digest_before)


if __name__ == "__main__":
    unittest.main()


class ServeCliTests(unittest.TestCase):
    def test_serve_calls_injected_server_with_project_host_and_port(self):
        calls = []

        status = inbound_cli_main(
            ["serve", "--project", "./demo-project", "--host", "127.0.0.1", "--port", "9123"],
            application_factory=lambda _project: object(),
            serve=lambda project, **options: calls.append((project, options)),
        )

        self.assertEqual(status, 0)
        self.assertEqual(calls, [("./demo-project", {"host": "127.0.0.1", "port": 9123})])
