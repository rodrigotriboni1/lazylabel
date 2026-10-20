import importlib
import io
import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path

from finlabel.analysis.schema import AnalysisPlan, MetricSpec, TimeAxis
from finlabel.sources.base import SourceSpec


class AnalysisServiceTests(unittest.TestCase):
    def setUp(self):
        try:
            self.service = importlib.import_module("finlabel.analysis.service")
            self.csv_source = importlib.import_module("finlabel.sources.csv_source")
            self.sqlite_source = importlib.import_module("finlabel.sources.sqlite_source")
        except ImportError:
            self.fail("Analysis run persistence and offline charts are not implemented")

    def test_run_persists_unique_plan_result_chart_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "sales.csv"
            source_path.write_text("date,product,amount\n2025-01-01,A,10.50\n2025-02-01,A,12.00\n", encoding="utf-8")
            source = self.csv_source.CsvSource(SourceSpec(
                "sales", "csv", source_path,
                schema={"date": "date", "product": "string", "amount": "decimal"},
            ))
            plan = AnalysisPlan(
                1, MetricSpec("sum", "amount"), ["product"], TimeAxis("date", "month"), [], "line",
            )
            parent = root / ".finlabel" / "analyses"

            first = self.service.analyze_source(source, "Monthly sales trend", None, plan, output_parent=parent)
            second = self.service.analyze_source(source, "Monthly sales trend", None, plan, output_parent=parent)

            self.assertNotEqual(first.run_id, second.run_id)
            self.assertEqual({path.name for path in first.artifact_dir.iterdir()}, {"plan.json", "result.json", "chart.html", "run.json"})
            result = json.loads((first.artifact_dir / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["rows"][0]["value"], "10.50")
            chart = (first.artifact_dir / "chart.html").read_text(encoding="utf-8")
            self.assertIn("Plotly", chart)
            self.assertIn("10.50", chart)
            self.assertIsNone(re.search(r'<script[^>]+src=["\']https?://', chart, flags=re.IGNORECASE))

    def test_explicit_output_path_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "sales.csv"
            source_path.write_text("amount\n10\n", encoding="utf-8")
            source = self.csv_source.CsvSource(SourceSpec("sales", "csv", source_path, schema={"amount": "decimal"}))
            plan = AnalysisPlan(1, MetricSpec("sum", "amount"), [], None, [], "bar")
            destination = root / "saved-run"

            first = self.service.analyze_source(source, "Total", None, plan, output_path=destination)
            with self.assertRaises(FileExistsError):
                self.service.analyze_source(source, "Total", None, plan, output_path=destination)

            self.assertTrue((first.artifact_dir / "result.json").exists())

    def test_sqlite_market_share_run_uses_declared_scope_and_persists_offline_chart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            database = root / "market.db"
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE sales (period TEXT, product TEXT, revenue TEXT)")
            connection.executemany("INSERT INTO sales VALUES (?, ?, ?)", [
                ("2025-01-01", "A", "75.00"), ("2025-01-02", "B", "25.00"),
            ])
            connection.commit()
            connection.close()
            source = self.sqlite_source.SqliteSource(SourceSpec(
                "market", "sqlite", database, table="sales",
                schema={"period": "date", "product": "string", "revenue": "decimal"},
            ))
            plan = AnalysisPlan(
                1, MetricSpec("share_of_total", "revenue", ()), ["product"],
                TimeAxis("period", "month"), [], "stacked_bar",
            )

            run = self.service.analyze_source(
                source, "Monthly product market share", None, plan,
                output_parent=root / ".finlabel" / "analyses",
            )

            self.assertEqual([row["value"] for row in run.result.rows], [Decimal("0.75"), Decimal("0.25")])
            self.assertTrue((run.artifact_dir / "chart.html").exists())

    def test_chart_point_limit_fails_before_creating_partial_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_path = root / "many-groups.csv"
            source_path.write_text(
                "product,amount\n" + "".join("P{},1\n".format(index) for index in range(2001)),
                encoding="utf-8",
            )
            source = self.csv_source.CsvSource(SourceSpec(
                "sales", "csv", source_path,
                schema={"product": "string", "amount": "decimal"},
            ))
            plan = AnalysisPlan(1, MetricSpec("sum", "amount"), ["product"], None, [], "bar")
            parent = root / ".finlabel" / "analyses"

            with self.assertRaisesRegex(ValueError, "2000 chart points"):
                self.service.analyze_source(source, "Totals", None, plan, output_parent=parent)

            self.assertFalse(parent.exists())

    def test_cli_executes_reviewable_plan_and_saves_local_artifacts(self):
        from finlabel.cli import main
        from finlabel.project import init_project

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            init_project(root)
            source_path = root / "sales.csv"
            source_path.write_text("date,product,amount\n2025-01-01,A,10\n", encoding="utf-8")
            project = importlib.import_module("finlabel.project")
            config = project.load_project(root)
            config.sources["sales"] = SourceSpec(
                "sales", "csv", source_path,
                schema={"date": "date", "product": "string", "amount": "decimal"},
            )
            project.save_project(config, config.path)
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps({
                "version": 1,
                "metric": {"operation": "sum", "column": "amount"},
                "dimensions": ["product"],
                "time_axis": {"column": "date", "grain": "month"},
                "filters": [],
                "chart": "line",
            }), encoding="utf-8")

            with redirect_stdout(io.StringIO()):
                status = main([
                    "analyze", "sales", "--question", "Monthly sales trend", "--plan", str(plan_path),
                    "--project", str(root),
                ])

            self.assertEqual(status, 0)
            run_dirs = list((root / ".finlabel" / "analyses").iterdir())
            self.assertEqual(len(run_dirs), 1)
            self.assertTrue((run_dirs[0] / "chart.html").exists())


if __name__ == "__main__":
    unittest.main()
