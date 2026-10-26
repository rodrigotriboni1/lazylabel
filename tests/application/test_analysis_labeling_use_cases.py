"""Behavior at injected boundaries, including privacy and fail-closed outcomes."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from finlabel.application.use_cases.analysis import analyze_source
from finlabel.application.use_cases.labeling import run_labeling
from finlabel.application.use_cases.errors import PlannerUnavailable, PersistenceError
from finlabel.application.ports.sources import SourceCapabilities, SourceRecord
from finlabel.domain.projects import ColumnProfile
from finlabel.domain.analysis.schema import AnalysisPlan, MetricSpec
from finlabel.domain.labeling.task import LabelTask
from finlabel.domain.labeling.policy import LabelingPolicy
from finlabel.domain.labeling.prediction import Prediction


class Runtime:
    def new_id(self): return '1' * 32
    def now(self): return '2026-10-26T12:00:00Z'
    def monotonic(self): return 0.0
    def selected_digest(self, values):
        return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    def record_ref(self, source_name, record_id):
        return hashlib.sha256(f'{source_name}\0{record_id}'.encode()).hexdigest()


class Source:
    def __init__(self): self.requests = []
    def capabilities(self): return SourceCapabilities(stable_record_ids=True)
    def columns(self): return (ColumnProfile('amount', 'number', 0, 1), ColumnProfile('secret', 'string', 0, 1))
    def iter_records(self, columns, *, batch_size=1000):
        self.requests.append(tuple(columns))
        values = {key: {'amount': 10, 'secret': 'PRIVATE'}[key] for key in columns}
        yield SourceRecord('row-1', values, Runtime().selected_digest(values))


class Store:
    def __init__(self, fail=False): self.fail = fail; self.saved = None
    def save_run(self, **payload):
        if self.fail: raise OSError('private storage detail')
        if 'before_publish' in payload:
            payload['outcomes'] = payload['before_publish'](payload['outcomes'])
        self.saved = payload
        return payload


def test_analysis_computes_selected_fields_and_persists():
    source, store = Source(), Store()
    result = analyze_source(source, 'Total', None, store, Runtime(),
                            plan_override=AnalysisPlan(1, MetricSpec('sum', 'amount'), [], None, [], 'bar'), explicit_types={'amount': 'decimal'})
    assert str(result['result'].rows[0]['value']) == '10'
    assert source.requests == [('amount',)]
    assert result['highlights'] == ()
    assert result['run_id'] == '1' * 32


def test_analysis_requires_planner_or_explicit_plan():
    with pytest.raises(PlannerUnavailable): analyze_source(Source(), 'Total', None, Store(), Runtime())


def test_analysis_validation_precedes_read_and_persistence():
    source, store = Source(), Store()
    with pytest.raises(ValueError):
        analyze_source(source, 'Total', None, store, Runtime(),
                       plan_override=AnalysisPlan(1, MetricSpec('sum', 'unknown'), [], None, [], 'bar'))
    assert source.requests == [] and store.saved is None


def test_analysis_maps_persistence_failure():
    with pytest.raises(PersistenceError, match='persist analysis'):
        analyze_source(Source(), 'Total', None, Store(True), Runtime(),
                       plan_override=AnalysisPlan(1, MetricSpec('count_rows'), [], None, [], 'bar'))


class Backend:
    model_id = 'local-model'
    revision = 'rev1'
    def __init__(self): self.calls = []
    def predict(self, values, *, task, max_new_tokens):
        self.calls.append(dict(values))
        return Prediction('low', 'PRIVATE rationale', {'low': .8, 'high': .2}, None, None, 'logits', 'a' * 64)


class Calibrator:
    def calibrate(self, prediction, *, task, policy, model_ref):
        return SimpleNamespace(task_id=task.task_id, policy_id=policy.policy_id, model_ref=model_ref,
                               confidence_method='logits', calibration_ref='cal-v1', confidence=.91)


def label_run(store=None, calibrator=None, policy=True):
    source, backend = Source(), Backend()
    task = LabelTask('risk', 'Classify', ('amount',), ('low', 'high'), 'local-model')
    configured = LabelingPolicy('policy', 'risk', ('low', 'high'), 'v1', 'cal-v1', .8, 120,
                               ({'field': 'amount', 'operator': 'number_between', 'minimum': 0},)) if policy else None
    result = run_labeling(source, 'ledger', task, configured, backend, store or Store(), Runtime(), calibrator=calibrator)
    return result, source, backend


def test_labeling_applies_calibrated_labels_without_persisting_raw_values():
    result, source, backend = label_run(calibrator=Calibrator())
    assert backend.calls == [{'amount': 10}]
    assert source.requests == [('amount',), ('amount',)]
    assert result['outcomes'][0].state == 'applied'
    assert 'PRIVATE' not in repr(result['outcomes'])
    assert result['outcomes'][0].record_ref == Runtime().record_ref('ledger', 'row-1')


@pytest.mark.parametrize('policy,reason', [(True, 'uncalibrated'), (False, 'missing_policy')])
def test_labeling_quarantines_uncertainty(policy, reason):
    result, _, backend = label_run(policy=policy)
    assert result['outcomes'][0].reason_code == reason
    if not policy: assert backend.calls == []


def test_labeling_maps_persistence_failure():
    with pytest.raises(PersistenceError, match='persist labeling'): label_run(Store(True))


def test_planner_receives_only_schema_and_highlights_are_grounded():
    from finlabel.domain.analysis.highlights import HighlightRef
    class Planner:
        model_ref = 'local-model@rev1'
        def plan(self, question, columns):
            assert question == 'Total'
            assert all(isinstance(column, ColumnProfile) for column in columns)
            assert 'PRIVATE' not in repr(columns)
            return AnalysisPlan(1, MetricSpec('sum', 'amount'), [], None, [], 'bar')
        def highlights(self, question, result):
            return [HighlightRef((), 'highest')]
    saved = analyze_source(Source(), 'Total', Planner(), Store(), Runtime(), explicit_types={'amount': 'decimal'})
    assert saved['rendered_highlights'] == ('Maior valor calculado de amount: 10 no recorte configurado.',)
    assert saved['model_ref'] == 'local-model@rev1'


def test_labeling_projects_unrequested_values_before_predicting():
    class LeakySource(Source):
        def iter_records(self, columns, *, batch_size=1000):
            yield SourceRecord('row-1', {'amount': 10, 'secret': 'PRIVATE'}, Runtime().selected_digest({'amount': 10}))
    source, backend = LeakySource(), Backend()
    task = LabelTask('risk', 'Classify', ('amount',), ('low', 'high'), 'local-model')
    policy = LabelingPolicy('policy', 'risk', ('low', 'high'), 'v1', 'cal-v1', .8, 120,
                           ({'field': 'amount', 'operator': 'not_empty'},))
    saved = run_labeling(source, 'ledger', task, policy, backend, Store(), Runtime(), calibrator=Calibrator())
    assert backend.calls == [{'amount': 10}]
    assert 'PRIVATE' not in repr(saved['outcomes'])


def test_store_rechecks_source_at_publication_and_quarantines_change():
    class ChangingSource(Source):
        def iter_records(self, columns, *, batch_size=1000):
            self.requests.append(tuple(columns))
            values = {'amount': 10 if len(self.requests) == 1 else 20}
            yield SourceRecord('row-1', values, Runtime().selected_digest(values))
    task = LabelTask('risk', 'Classify', ('amount',), ('low', 'high'), 'local-model')
    policy = LabelingPolicy('policy', 'risk', ('low', 'high'), 'v1', 'cal-v1', .8, 120,
                           ({'field': 'amount', 'operator': 'not_empty'},))
    saved = run_labeling(ChangingSource(), 'ledger', task, policy, Backend(), Store(), Runtime(), calibrator=Calibrator())
    assert saved['outcomes'][0].reason_code == 'stale_source'
    assert saved['outcomes'][0].predicted_label is None


def test_project_analysis_resolves_named_read_only_source():
    from finlabel.application.ports.projects import ProjectDescriptor
    from finlabel.application.use_cases.analysis import analyze_project
    class Projects:
        def get_project(self, reference): return ProjectDescriptor(reference, ('ledger',))
    class Sources:
        def open_source(self, reference, source_name):
            assert (reference, source_name) == ('project', 'ledger')
            return Source()
    saved = analyze_project(Projects(), Sources(), 'project', 'ledger', 'Rows', None, Store(), Runtime(),
                            AnalysisPlan(1, MetricSpec('count_rows'), [], None, [], 'bar'))
    assert saved['source_name'] == 'ledger'
    assert saved['result'].valid_row_count == 1
