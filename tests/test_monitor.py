import importlib
import json
import tempfile
import unittest
from pathlib import Path

from finlabel.sources.base import SourceSpec


class MonitorTests(unittest.TestCase):
    def setUp(self):
        try:
            self.monitor = importlib.import_module("finlabel.monitor")
            self.csv_source = importlib.import_module("finlabel.sources.csv_source")
        except ImportError:
            self.fail("Structural and quality monitoring is not implemented")

    def test_reports_missing_required_extra_type_and_missing_ratio_findings(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.csv"
            path.write_text("amount,note\n10,ok\n,blank\n", encoding="utf-8")
            source = self.csv_source.CsvSource(SourceSpec("ledger", "csv", path))
            baseline = self.monitor.SchemaBaseline(
                columns={"amount": "string", "account": "string"},
                required_columns=["account", "amount"],
                max_missing_ratio={"amount": 0.1},
                allow_extra_columns=False,
            )

            codes = {finding.code for finding in self.monitor.monitor_source(source, baseline)}

            self.assertEqual(codes, {
                "missing_required_column", "unexpected_column", "type_mismatch", "missing_ratio_exceeded"
            })

    def test_capture_schema_is_only_a_candidate_with_no_implicit_threshold(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.csv"
            path.write_text("amount\n10\n", encoding="utf-8")
            source = self.csv_source.CsvSource(SourceSpec("ledger", "csv", path))

            candidate = self.monitor.capture_schema(source)

            self.assertEqual(candidate.columns, {"amount": "integer"})
            self.assertEqual(candidate.max_missing_ratio, {})
            self.assertEqual(candidate.required_columns, ("amount",))
            self.assertFalse(candidate.allow_extra_columns)

    def test_schema_cli_writes_candidate_and_monitor_reports_it(self):
        from finlabel.cli import main

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            from finlabel.project import init_project
            init_project(root)
            csv_path = root / "ledger.csv"
            csv_path.write_text("amount\n10\n", encoding="utf-8")
            from finlabel.project import load_project, save_project
            config = load_project(root)
            config.sources["ledger"] = SourceSpec("ledger", "csv", csv_path)
            save_project(config, config.path)
            baseline_path = root / "candidate.json"

            self.assertEqual(main(["schema", "capture", "ledger", "--output", str(baseline_path), "--project", str(root)]), 0)
            candidate = json.loads(baseline_path.read_text(encoding="utf-8"))
            self.assertEqual(candidate["columns"], {"amount": "integer"})
            self.assertEqual(main(["monitor", "ledger", "--baseline", str(baseline_path), "--project", str(root)]), 0)


if __name__ == "__main__":
    unittest.main()
