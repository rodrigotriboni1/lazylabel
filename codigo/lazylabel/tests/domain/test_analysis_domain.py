"""Pure analysis contracts and parity with the legacy source entrypoint."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from lazylabel.domain.analysis import (
    AnalysisPlan, AnalysisResult, FilterSpec, MetricSpec, TimeAxis,
    required_fields, run_analysis, validate_analysis_plan,
)
from lazylabel.domain.analysis.charts import MAX_CHART_POINTS, chart_specification
from lazylabel.domain.projects import ColumnProfile, DatasetProfile
from lazylabel.analysis.engine import run_analysis as legacy_run_analysis


PROFILES = [ColumnProfile(name, kind, 0, 4) for name, kind in
            (("period", "string"), ("segment", "string"), ("amount", "number"))]
TYPES = {"period": "date", "amount": "decimal"}
ROWS = [
    {"period": "2025-02-02", "segment": "B", "amount": "8"},
    {"period": "2025-01-02", "segment": "B", "amount": "25"},
    {"period": "2025-01-01", "segment": "A", "amount": "75"},
    {"period": "2025-02-01", "segment": "A", "amount": "2"},
]


def calculate(plan, rows=ROWS, types=TYPES):
    return run_analysis(plan, PROFILES, types, iter(rows))


def test_profile_values_keep_identity_and_serialization():
    from lazylabel.profile import ColumnProfile as LegacyColumn, DatasetProfile as LegacyDataset
    assert LegacyColumn is ColumnProfile
    assert LegacyDataset is DatasetProfile
    assert ColumnProfile.__module__.startswith("lazylabel.domain.projects")
    assert DatasetProfile("source.csv", 4, PROFILES, "segment", {"A": 2, "B": 2}).to_dict() == {
        "source_name": "source.csv", "row_count": 4,
        "columns": [{"name": p.name, "inferred_type": p.inferred_type,
                     "missing_count": 0, "non_missing_count": 4} for p in PROFILES],
        "target_name": "segment", "target_counts": {"A": 2, "B": 2},
    }


@pytest.mark.parametrize("metric, expected", [
    (MetricSpec("count_rows"), [2, 2]),
    (MetricSpec("sum", "amount"), [Decimal("77"), Decimal("33")]),
    (MetricSpec("average", "amount"), [Decimal("38.5"), Decimal("16.5")]),
    (MetricSpec("distinct_count", "amount"), [2, 2]),
    (MetricSpec("share_of_total", "amount", ()), [Decimal("0.7"), Decimal("0.3")]),
])
def test_aggregates_and_legacy_adapter_are_identical(metric, expected):
    plan = AnalysisPlan(1, metric, ("segment",))
    calls = []
    def records():
        calls.append("read")
        yield from ROWS
    result = run_analysis(plan, PROFILES, TYPES, records())
    assert [row["value"] for row in result.rows] == expected
    assert result.valid_row_count == 4
    assert calls == ["read"]
    assert required_fields(plan) == list(result.selected_fields)
    assert result == calculate(plan, list(reversed(ROWS)))
    source = SimpleNamespace(
        columns=lambda: PROFILES, spec=SimpleNamespace(schema=TYPES),
        iter_records=lambda fields: (SimpleNamespace(values=row) for row in ROWS),
    )
    assert legacy_run_analysis(source, plan) == result


@pytest.mark.parametrize("plan, error", [
    (AnalysisPlan(2, MetricSpec("count_rows")), "version"),
    (AnalysisPlan(1, MetricSpec("median", "amount")), "metric"),
    (AnalysisPlan(1, MetricSpec("sum", "missing")), "column"),
    (AnalysisPlan(1, MetricSpec("count_rows"), chart="pie"), "chart"),
    (AnalysisPlan(1, MetricSpec("share_of_total", "amount"), ("segment",)), "denominator"),
    (AnalysisPlan(1, MetricSpec("count_rows"), filters=(FilterSpec("amount", "between", [1]),)), "two"),
])
def test_invalid_plan_fails_before_requesting_record_iteration(plan, error):
    def unread():
        pytest.fail("Validation must precede record access")
        yield {}
    with pytest.raises(ValueError, match=error):
        run_analysis(plan, PROFILES, TYPES, unread())
    with pytest.raises(ValueError, match=error):
        validate_analysis_plan(plan, PROFILES)


def test_explicit_mapping_is_required_before_record_access():
    def unread():
        pytest.fail("Invalid mapping must not read records")
        yield {}
    with pytest.raises(ValueError, match="explicit type mapping"):
        run_analysis(AnalysisPlan(1, MetricSpec("sum", "amount")), PROFILES, {}, unread())


def test_kpi_and_heatmap_input_values_preserve_exact_period_category_shares():
    plan = AnalysisPlan(1, MetricSpec("share_of_total", "amount", ()),
                        ("segment",), TimeAxis("period", "month"), chart="stacked_bar")
    result = calculate(plan)
    assert result.rows == [
        {"segment": "A", "period": "2025-01", "value": Decimal("0.75")},
        {"segment": "A", "period": "2025-02", "value": Decimal("0.2")},
        {"segment": "B", "period": "2025-01", "value": Decimal("0.25")},
        {"segment": "B", "period": "2025-02", "value": Decimal("0.8")},
    ]
    assert result.formula_metadata == {
        "operation": "share_of_total", "column": "amount", "denominator_scope": [],
        "filters": [], "time_grain": "month", "valid_row_count": 4,
        "group_fields": ["segment", "period"],
    }
    assert result.invalid_value_counts == {}
    spec = chart_specification(result)
    assert spec.kind == "stacked_bar"
    assert spec.title == "share_of_total por segment"
    assert spec.xaxis_title == "period"
    assert spec.yaxis_title == "amount"
    assert [(s.name, s.x_values, s.y_values) for s in spec.series] == [
        ("segment=A", ("2025-01", "2025-02"), (Decimal("0.75"), Decimal("0.2"))),
        ("segment=B", ("2025-01", "2025-02"), (Decimal("0.25"), Decimal("0.8"))),
    ]


@pytest.mark.parametrize("amounts, expected, invalid", [
    (["", " "], [None, None], {"missing:amount": 2}),
    (["5", "-5"], [None, None], {}),
    (["-2", "-3"], [Decimal("0.4"), Decimal("0.6")], {}),
])
def test_share_edge_cases(amounts, expected, invalid):
    rows = [{"segment": name, "amount": amount} for name, amount in zip(("A", "B"), amounts)]
    result = calculate(AnalysisPlan(1, MetricSpec("share_of_total", "amount", ()), ("segment",)), rows)
    assert [row["value"] for row in result.rows] == expected
    assert result.invalid_value_counts == invalid


def test_invalid_dates_and_numbers_preserve_exclusions():
    plan = AnalysisPlan(1, MetricSpec("sum", "amount"), time_axis=TimeAxis("period", "month"))
    result = calculate(plan, [
        {"period": "not-a-date", "amount": "7"},
        {"period": "2025-01-01", "amount": "3"},
        {"period": "2025-01-02", "amount": "bad"},
    ])
    assert result.valid_row_count == 2
    assert result.invalid_value_counts == {"invalid:amount": 1, "invalid:period": 1}
    assert result.rows == [{"period": "2025-01", "value": Decimal("3")}]


def test_chart_total_empty_missing_and_limit_contracts():
    plan = AnalysisPlan(1, MetricSpec("sum", "amount"))
    spec = chart_specification(calculate(plan))
    assert spec.series[0].x_values == ("Total",)
    assert spec.series[0].y_values == (Decimal("110"),)
    assert spec.title == "sum"
    assert spec.xaxis_title == "Agregado"
    assert chart_specification(calculate(plan, [])).series == ()
    result = calculate(plan, [{"amount": ""}])
    assert chart_specification(result).series[0].y_values == (None,)
    too_many = AnalysisResult(plan, [{"value": 1}] * (MAX_CHART_POINTS + 1), 0, {}, (), {})
    with pytest.raises(ValueError, match="chart points"):
        chart_specification(too_many)


def test_legacy_bridge_projects_only_required_fields_and_defers_reading():
    calls = []
    def records(fields):
        calls.append(fields)
        return iter([SimpleNamespace(values=ROWS[0])])
    source = SimpleNamespace(columns=lambda: PROFILES, spec=SimpleNamespace(schema=TYPES), iter_records=records)
    plan = AnalysisPlan(1, MetricSpec("sum", "amount"), ("segment",),
                        filters=(FilterSpec("segment", "eq", "B"),))
    assert legacy_run_analysis(source, plan).rows == [{"segment": "B", "value": Decimal("8")}]
    assert calls == [["segment", "amount"]]
    calls.clear()
    with pytest.raises(ValueError, match="version"):
        legacy_run_analysis(source, AnalysisPlan(2, MetricSpec("count_rows")))
    assert calls == []


@pytest.mark.parametrize("kind, trace_type, mode", [
    ("line", "scatter", None), ("bar", "bar", "group"), ("stacked_bar", "bar", "stack"),
])
def test_legacy_renderer_preserves_plotly_trace_values(monkeypatch, kind, trace_type, mode):
    import plotly.io
    from lazylabel.analysis.charts import render_chart
    captured = []
    def capture(figure, **options):
        captured.append((figure.to_plotly_json(), options))
        return "offline html"
    monkeypatch.setattr(plotly.io, "to_html", capture)
    plan = AnalysisPlan(1, MetricSpec("sum", "amount"), ("segment",), TimeAxis("period", "month"), chart=kind)
    assert render_chart(calculate(plan)) == "offline html"
    figure, options = captured[0]
    assert options == {"full_html": True, "include_plotlyjs": True, "config": {"displaylogo": False}}
    assert figure["layout"].get("barmode") == mode
    assert [(trace["type"], trace["name"], trace["x"], trace["y"], trace["customdata"]) for trace in figure["data"]] == [
        (trace_type, "segment=A", ["2025-01", "2025-02"], [75.0, 2.0], ["75", "2"]),
        (trace_type, "segment=B", ["2025-01", "2025-02"], [25.0, 8.0], ["25", "8"]),
    ]


def test_records_are_consumed_as_a_stream_without_materialization():
    # A streaming reader can reuse its mapping buffer after each yielded row.
    def records():
        row = {}
        for amount in ("1", "2", "3"):
            row["amount"] = amount
            yield row
    result = run_analysis(AnalysisPlan(1, MetricSpec("sum", "amount")), PROFILES, TYPES, records())
    assert result.rows == [{"value": Decimal("6")}]
    assert result.valid_row_count == 3
