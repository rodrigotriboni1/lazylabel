import importlib
import json
import tempfile
import unittest
from pathlib import Path

from lazylabel.domain.analysis.schema import AnalysisPlan, FilterSpec, MetricSpec
from lazylabel.adapters.outbound.sources.base import SourceSpec


class FakeBackend:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate(self, prompt, *, max_new_tokens):
        self.prompts.append((prompt, max_new_tokens))
        return self.response


class PlannerTests(unittest.TestCase):
    def setUp(self):
        try:
            self.planner = importlib.import_module("lazylabel.adapters.outbound.models.analysis_planner")
            self.backend_module = importlib.import_module("lazylabel.adapters.outbound.models.text_generation")
            self.csv_source = importlib.import_module("lazylabel.adapters.outbound.sources.csv_source")
            self.engine = importlib.import_module("lazylabel.adapters.outbound.sources.analysis")
        except ImportError:
            self.fail("Local analysis planner and optional model backend are not implemented")

    def test_planner_parses_versioned_json_and_prompt_contains_schema_not_rows(self):
        backend = FakeBackend(json.dumps({
            "version": 1,
            "metric": {"operation": "sum", "column": "amount"},
            "dimensions": ["product"],
            "time_axis": {"column": "date", "grain": "month"},
            "filters": [],
            "chart": "line",
        }))
        schema = [
            type("Column", (), {"name": "product", "inferred_type": "string"})(),
            type("Column", (), {"name": "amount", "inferred_type": "number"})(),
            type("Column", (), {"name": "date", "inferred_type": "string"})(),
        ]

        plan = self.planner.plan_analysis("Tendência das vendas?", schema, backend)

        self.assertEqual(plan.metric.operation, "sum")
        self.assertEqual(plan.chart, "line")
        self.assertIn("Tendência das vendas?", backend.prompts[0][0])
        self.assertIn("amount", backend.prompts[0][0])
        self.assertNotIn("SECRET_ROW_VALUE", backend.prompts[0][0])

    def test_planner_returns_clarification_instead_of_guessing_ambiguous_definition(self):
        backend = FakeBackend(json.dumps({
            "needs_clarification": True,
            "questions": ["Qual campo representa o valor total do mercado?"],
        }))
        schema = [type("Column", (), {"name": "product", "inferred_type": "string"})()]

        with self.assertRaises(self.planner.AnalysisClarificationError) as captured:
            self.planner.plan_analysis("Qual o market share?", schema, backend)

        self.assertIn("mercado", captured.exception.questions[0])

    def test_model_highlight_is_a_validated_reference_and_renderer_uses_exact_result_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sales.csv"
            path.write_text("product,amount\nA,20\nB,10\n", encoding="utf-8")
            source = self.csv_source.CsvSource(SourceSpec(
                "sales", "csv", path, schema={"product": "string", "amount": "decimal"}
            ))
            plan = AnalysisPlan(1, MetricSpec("sum", "amount"), ["product"], None, [], "bar")
            result = self.engine.run_analysis(source, plan)
            backend = FakeBackend(json.dumps({
                "highlights": [{"result_key": ["A"], "observation": "highest"}],
            }))

            highlights = self.planner.plan_highlights("Compare", result, backend)

            self.assertEqual(len(highlights), 1)
            self.assertEqual(highlights[0].result_key, ("A",))
            self.assertIn("20", self.planner.render_highlight(result, highlights[0]))

    def test_invalid_model_reference_is_rejected_and_transformers_backend_is_lazy(self):
        backend = FakeBackend(json.dumps({
            "highlights": [{"result_key": ["not-in-results"], "observation": "highest"}],
        }))
        result = type("Result", (), {
            "rows": [{"product": "A", "value": 1}],
            "plan": AnalysisPlan(1, MetricSpec("sum", "amount"), ["product"], None, [], "bar"),
            "formula_metadata": {"group_fields": ["product"], "time_grain": None},
        })()

        with self.assertRaisesRegex(ValueError, "result key"):
            self.planner.plan_highlights("Compare", result, backend)
        local_backend = self.backend_module.TransformersTextGenerationBackend("not-downloaded/model")
        self.assertIsNone(local_backend._model)
        self.assertIsNone(local_backend._tokenizer)

    def test_numeric_result_keys_are_matched_without_changing_the_grounded_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sales.csv"
            path.write_text("product,amount\n1,10\n2,20\n", encoding="utf-8")
            source = self.csv_source.CsvSource(SourceSpec(
                "sales", "csv", path, schema={"product": "integer", "amount": "decimal"}
            ))
            plan = AnalysisPlan(1, MetricSpec("sum", "amount"), ["product"], None, [], "bar")
            result = self.engine.run_analysis(source, plan)
            backend = FakeBackend(json.dumps({
                "highlights": [{"result_key": ["2"], "observation": "highest"}],
            }))

            highlights = self.planner.plan_highlights("Compare", result, backend)

            self.assertEqual(highlights[0].result_key, ("2",))
            self.assertIn("20", self.planner.render_highlight(result, highlights[0]))

    def test_trend_highlight_compares_calculated_endpoints(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sales.csv"
            path.write_text("date,product,amount\n2025-01-01,A,10\n2025-02-01,A,20\n", encoding="utf-8")
            source = self.csv_source.CsvSource(SourceSpec(
                "sales", "csv", path, schema={"date": "date", "product": "string", "amount": "decimal"}
            ))
            plan = AnalysisPlan(
                1, MetricSpec("sum", "amount"), ["product"],
                importlib.import_module("lazylabel.domain.analysis.schema").TimeAxis("date", "month"), [], "line",
            )
            result = self.engine.run_analysis(source, plan)
            backend = FakeBackend(json.dumps({
                "highlights": [{"result_key": ["A"], "observation": "overall_increase"}],
            }))

            reference = self.planner.plan_highlights("Trend", result, backend)[0]

            rendered = self.planner.render_highlight(result, reference)
            self.assertIn("10", rendered)
            self.assertIn("20", rendered)

    def test_point_highlight_includes_time_bucket_in_grounded_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sales.csv"
            path.write_text("date,product,amount\n2025-01-01,A,10\n2025-02-01,A,20\n", encoding="utf-8")
            source = self.csv_source.CsvSource(SourceSpec(
                "sales", "csv", path, schema={"date": "date", "product": "string", "amount": "decimal"}
            ))
            TimeAxis = importlib.import_module("lazylabel.domain.analysis.schema").TimeAxis
            plan = AnalysisPlan(1, MetricSpec("sum", "amount"), ["product"], TimeAxis("date", "month"), [], "line")
            result = self.engine.run_analysis(source, plan)
            backend = FakeBackend(json.dumps({
                "highlights": [{"result_key": ["A", "2025-02"], "observation": "highest"}],
            }))

            reference = self.planner.plan_highlights("Trend", result, backend)[0]

            rendered = self.planner.render_highlight(result, reference)
            self.assertIn("date=2025-02", rendered)


if __name__ == "__main__":
    unittest.main()
