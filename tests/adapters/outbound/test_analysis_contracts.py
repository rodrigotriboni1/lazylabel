"""Analysis/planning adapter contracts through application ports."""
import hashlib
import json
import os
from decimal import Decimal

import pytest


def result():
    from finlabel.domain.analysis.schema import AnalysisPlan, AnalysisResult, MetricSpec
    return AnalysisResult(AnalysisPlan(1, MetricSpec('sum', 'amount'), ('category',)),
                          ({'category': 'fees', 'value': Decimal('12.30')},), 2, {},
                          ('category', 'amount'), {'group_fields': ['category']})


def payload():
    return dict(run_id='a'*32, created_at='2026-10-26T00:00:00Z', source_name='ledger',
                question='total', model_ref=None, result=result(), highlights=(), rendered_highlights=())


def test_analysis_store_publishes_complete_artifact_set_and_preserves_json_contract(tmp_path, monkeypatch):
    from finlabel.adapters.outbound.persistence.analysis_runs import FileAnalysisRunStore
    original_replace = os.replace
    destination = tmp_path / ('a'*32)
    def publish(staged, final):
        assert not destination.exists()
        assert set(path.name for path in staged.iterdir()) == {'plan.json', 'result.json', 'chart.html', 'run.json'}
        original_replace(staged, final)
    monkeypatch.setattr(os, 'replace', publish)
    receipt = FileAnalysisRunStore(output_parent=tmp_path).save_run(**payload())
    raw = json.loads((receipt.artifact_dir / 'result.json').read_text())
    assert raw == {'version': 1, 'plan': {'version': 1,
        'metric': {'operation': 'sum', 'column': 'amount', 'denominator_scope': None},
        'dimensions': ['category'], 'time_axis': None, 'filters': [], 'chart': 'bar'},
        'rows': [{'category': 'fees', 'value': '12.30'}], 'valid_row_count': 2,
        'invalid_value_counts': {}, 'selected_fields': ['category', 'amount'],
        'formula_metadata': {'group_fields': ['category']}, 'highlights': []}
    manifest = json.loads((destination / 'run.json').read_text())
    assert manifest['run_id'] == 'a'*32
    assert manifest['created_at'] == '2026-10-26T00:00:00Z'
    for stem, extension in [('plan', 'json'), ('result', 'json'), ('chart', 'html')]:
        assert manifest[stem+'_sha256'] == hashlib.sha256((destination / (stem+'.'+extension)).read_bytes()).hexdigest()
    assert set(path.name for path in tmp_path.iterdir()) == {'a'*32}
    with pytest.raises(FileExistsError):
        FileAnalysisRunStore(output_parent=tmp_path).save_run(**payload())


def test_analysis_failed_publication_cleans_staging_and_preserves_original_error(tmp_path, monkeypatch):
    from finlabel.adapters.outbound.persistence.analysis_runs import FileAnalysisRunStore
    def fail(*args):
        raise OSError('disk unavailable')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(OSError, match='disk unavailable'):
        FileAnalysisRunStore(output_parent=tmp_path).save_run(**payload())
    assert list(tmp_path.iterdir()) == []


def test_planner_adapts_generation_to_validated_plan_without_source_rows():
    from finlabel.adapters.outbound.models.analysis_planner import LocalAnalysisPlanner
    from finlabel.domain.projects import ColumnProfile
    class Generator:
        model_id = 'local/model'
        def generate(self, prompt, *, max_new_tokens):
            assert 'amount' in prompt and 'inferred_type' in prompt
            assert max_new_tokens == 700
            return '{"version":1,"metric":{"operation":"sum","column":"amount"},"dimensions":[],"chart":"bar"}'
    planner = LocalAnalysisPlanner(Generator())
    plan = planner.plan('total', [ColumnProfile('amount', 'integer', 0, 2)])
    assert plan.metric.operation == 'sum'
    assert plan.metric.column == 'amount'
    assert planner.model_ref == 'local/model'
