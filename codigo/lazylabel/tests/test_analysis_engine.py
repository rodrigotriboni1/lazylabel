import importlib
import tempfile
import unittest
from pathlib import Path

from lazylabel.adapters.outbound.sources.base import SourceSpec


class AnalysisEngineTests(unittest.TestCase):
    def setUp(self):
        try:
            self.schema = importlib.import_module("lazylabel.domain.analysis.schema")
            self.engine = importlib.import_module("lazylabel.adapters.outbound.sources.analysis")
            self.csv_source = importlib.import_module("lazylabel.adapters.outbound.sources.csv_source")
        except ImportError:
            self.fail("Typed analytics plans and deterministic aggregation are not implemented")

    def make_source(self, path, rows):
        path.write_text("date,product,amount\n" + rows, encoding="utf-8")
        spec = SourceSpec(
            "sales", "csv", path,
            schema={"date": "date", "product": "string", "amount": "decimal"},
        )
        return self.csv_source.CsvSource(spec)

    def test_sums_decimal_values_by_group_and_iso_month_in_stable_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary) / "sales.csv", (
                "2025-02-01,B,3.25\n2025-01-15,A,10.10\n2025-01-20,B,2.50\n"
            ))
            plan = self.schema.AnalysisPlan(
                1, self.schema.MetricSpec("sum", "amount"), ["product"],
                self.schema.TimeAxis("date", "month"), [], "line",
            )

            result = self.engine.run_analysis(source, plan)

            self.assertEqual(
                [(row["date"], row["product"], row["value"]) for row in result.rows],
                [("2025-01", "A", self.engine.Decimal("10.10")),
                 ("2025-01", "B", self.engine.Decimal("2.50")),
                 ("2025-02", "B", self.engine.Decimal("3.25"))],
            )
            self.assertEqual(result.valid_row_count, 3)

    def test_share_of_total_uses_only_explicit_denominator_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary) / "sales.csv", (
                "2025-01-01,A,75\n2025-01-02,B,25\n2025-02-01,A,2\n2025-02-02,B,8\n"
            ))
            plan = self.schema.AnalysisPlan(
                1, self.schema.MetricSpec("share_of_total", "amount", ()), ["product"],
                self.schema.TimeAxis("date", "month"), [], "stacked_bar",
            )

            result = self.engine.run_analysis(source, plan)

            shares = {(row["date"], row["product"]): row["value"] for row in result.rows}
            self.assertEqual(shares[("2025-01", "A")], self.engine.Decimal("0.75"))
            self.assertEqual(shares[("2025-02", "B")], self.engine.Decimal("0.8"))
            self.assertEqual(result.formula_metadata["denominator_scope"], [])

    def test_invalid_values_are_counted_and_excluded_from_numeric_metric(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary) / "sales.csv", (
                "2025-01-01,A,10\n2025-01-02,A,not-a-number\n2025-01-03,A,\n"
            ))
            plan = self.schema.AnalysisPlan(
                1, self.schema.MetricSpec("sum", "amount"), ["product"], None, [], "bar",
            )

            result = self.engine.run_analysis(source, plan)

            self.assertEqual(result.rows[0]["value"], self.engine.Decimal("10"))
            self.assertEqual(result.invalid_value_counts["invalid:amount"], 1)
            self.assertEqual(result.invalid_value_counts["missing:amount"], 1)

    def test_invalid_metric_value_cannot_match_a_filter_as_if_it_were_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary) / "sales.csv", "2025-01-01,A,not-a-number\n")
            plan = self.schema.AnalysisPlan(
                1, self.schema.MetricSpec("sum", "amount"), ["product"], None,
                [self.schema.FilterSpec("amount", "eq", None)], "bar",
            )

            result = self.engine.run_analysis(source, plan)

            self.assertEqual(result.valid_row_count, 0)
            self.assertEqual(result.rows, [])

    def test_plan_rejects_unknown_columns_operations_and_ambiguous_shares(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_source(Path(temporary) / "sales.csv", "2025-01-01,A,10\n")
            schema = source.columns()
            invalid = self.schema.AnalysisPlan(
                1, self.schema.MetricSpec("share_of_total", "amount"), ["product"], None, [], "pie",
            )

            with self.assertRaisesRegex(ValueError, "chart"):
                self.schema.validate_analysis_plan(invalid, schema)
            with self.assertRaisesRegex(ValueError, "denominator"):
                self.schema.validate_analysis_plan(
                    self.schema.AnalysisPlan(1, self.schema.MetricSpec("share_of_total", "amount", ("date",)),
                                             ["product"], None, [], "bar"), schema
                )
            with self.assertRaisesRegex(ValueError, "column"):
                self.schema.validate_analysis_plan(
                    self.schema.AnalysisPlan(1, self.schema.MetricSpec("sum", "unknown"), [], None, [], "bar"), schema
                )

    def test_share_denominator_must_exclude_at_least_one_group_dimension(self):
        schema = [
            self.schema.ColumnProfile("date", "date", 0, 1),
            self.schema.ColumnProfile("product", "string", 0, 1),
            self.schema.ColumnProfile("amount", "decimal", 0, 1),
        ]
        for dimensions, scope in ((["product"], ["product"]), ([], [])):
            plan = self.schema.AnalysisPlan(
                1, self.schema.MetricSpec("share_of_total", "amount", scope), dimensions, None, [], "bar",
            )
            with self.subTest(dimensions=dimensions, scope=scope), self.assertRaisesRegex(ValueError, "exclude"):
                self.schema.validate_analysis_plan(plan, schema)


if __name__ == "__main__":
    unittest.main()
