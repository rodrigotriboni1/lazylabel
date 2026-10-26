"""Monitoring compares value profiles without touching a source."""

import pytest

from finlabel.domain.monitoring import SchemaBaseline, capture_schema, compare_schema
from finlabel.domain.projects import ColumnProfile


def test_structural_findings_are_deterministic_and_ordered():
    baseline = SchemaBaseline({"amount": "string", "account": "string"},
                              ("account", "amount"), {"amount": 0.1}, False)
    columns = [ColumnProfile("amount", "integer", 1, 1),
               ColumnProfile("note", "string", 0, 2)]
    assert [finding.code for finding in compare_schema(columns, baseline)] == [
        "missing_required_column", "unexpected_column", "type_mismatch", "missing_ratio_exceeded"
    ]
    assert compare_schema(columns, baseline) == compare_schema(tuple(columns), baseline)


def test_candidate_has_no_inferred_threshold_and_invalid_threshold_rejected():
    columns = (ColumnProfile("amount", "integer", 0, 1),)
    assert capture_schema(columns) == SchemaBaseline({"amount": "integer"}, ("amount",), {}, False)
    with pytest.raises(ValueError, match="between 0 and 1"):
        compare_schema(columns, SchemaBaseline({"amount": "integer"}, (), {"amount": 1.2}, False))
