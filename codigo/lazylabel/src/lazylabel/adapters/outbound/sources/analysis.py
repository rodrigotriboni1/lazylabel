"""Adapt a read-only source to the pure streaming analysis engine."""

from lazylabel.domain.analysis.engine import (
    DATE_TYPES, NUMERIC_TYPES, Decimal, asdict_filter, required_fields,
    run_analysis as calculate_analysis,
)
from lazylabel.domain.analysis.schema import AnalysisPlan, AnalysisResult


def run_analysis(source, plan: AnalysisPlan) -> AnalysisResult:
    profiles = source.columns()

    def records():
        for record in source.iter_records(required_fields(plan)):
            yield record.values

    return calculate_analysis(plan, profiles, source.spec.schema, records())
