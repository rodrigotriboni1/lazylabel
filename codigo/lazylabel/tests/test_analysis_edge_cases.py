import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from lazylabel.analysis.engine import run_analysis
from lazylabel.analysis.schema import AnalysisPlan, FilterSpec, MetricSpec, TimeAxis
from lazylabel.sources.base import SourceSpec
from lazylabel.sources.csv_source import CsvSource


class AnalysisEdgeCaseTests(unittest.TestCase):
    def source(self, root, contents, schema=None):
        path = root / "source.csv"
        path.write_text(contents, encoding="utf-8")
        return CsvSource(SourceSpec("source", "csv", path, schema=schema or {}))

    def test_missing_numeric_and_date_mappings_fail_before_reading_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source(root, "amount,period\n10,2025-01-01\n")
            with self.assertRaisesRegex(ValueError, "explicit type mapping"):
                run_analysis(source, AnalysisPlan(1, MetricSpec("sum", "amount"), [], None, [], "bar"))
            source = self.source(root, "amount,period\n10,2025-01-01\n", {"amount": "decimal"})
            with self.assertRaisesRegex(ValueError, "explicit date or datetime mapping"):
                run_analysis(source, AnalysisPlan(1, MetricSpec("sum", "amount"), [], TimeAxis("period", "month"), [], "line"))

    def test_invalid_explicit_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.source(Path(temporary), "amount\n10\n", {"amount": "currency"})
            with self.assertRaisesRegex(ValueError, "Unsupported explicit type mapping"):
                run_analysis(source, AnalysisPlan(1, MetricSpec("sum", "amount"), [], None, [], "bar"))

    def test_invalid_dates_are_counted_and_excluded_from_groups(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.source(Path(temporary), "period,amount\nnot-a-date,7\n2025-01-01,3\n",
                                 {"period": "date", "amount": "decimal"})
            result = run_analysis(source, AnalysisPlan(
                1, MetricSpec("sum", "amount"), [], TimeAxis("period", "month"), [], "line"))
            self.assertEqual(result.valid_row_count, 1)
            self.assertEqual(result.invalid_value_counts, {"invalid:period": 1})
            self.assertEqual(result.rows, [{"period": "2025-01", "value": Decimal("3")}])

    def test_null_only_metric_produces_no_groups_and_tracks_missing_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.source(Path(temporary), "segment,amount\nA,\nB, \n", {"amount": "decimal"})
            result = run_analysis(source, AnalysisPlan(
                1, MetricSpec("average", "amount"), ["segment"], None, [], "bar"))
            self.assertEqual(result.valid_row_count, 2)
            self.assertEqual(result.invalid_value_counts["missing:amount"], 2)
            self.assertEqual([row["value"] for row in result.rows], [None, None])

    def test_zero_share_denominator_returns_null_and_negative_total_is_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.source(Path(temporary), "segment,amount\nA,5\nB,-5\n",
                                 {"amount": "decimal"})
            plan = AnalysisPlan(1, MetricSpec("share_of_total", "amount", ()), ["segment"], None, [], "bar")
            result = run_analysis(source, plan)
            shares = {row["segment"]: row["value"] for row in result.rows}
            self.assertIsNone(shares["A"])
            self.assertIsNone(shares["B"])

            source = self.source(Path(temporary), "segment,amount\nC,-2\nD,-3\n", {"amount": "decimal"})
            result = run_analysis(source, plan)
            shares = {row["segment"]: row["value"] for row in result.rows}
            self.assertEqual(shares["C"], Decimal("0.4"))
            self.assertEqual(shares["D"], Decimal("0.6"))

    def test_empty_input_returns_empty_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.source(Path(temporary), "segment,amount\n", {"amount": "decimal"})
            result = run_analysis(source, AnalysisPlan(
                1, MetricSpec("sum", "amount"), ["segment"], None, [], "bar"))
            self.assertEqual(result.valid_row_count, 0)
            self.assertEqual(result.rows, [])


if __name__ == "__main__":
    unittest.main()
