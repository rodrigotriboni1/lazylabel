"""Training orchestration contracts: in-memory ports, no model or filesystem."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from finlabel.domain.labeling.task import LabelTask
from finlabel.domain.labeling.policy import LabelingPolicy
from finlabel.domain.training.promotion import PromotionPolicy
from finlabel.application.ports.training import TrainingDataset, TrainedAdapter
from finlabel.application.use_cases.training import run_training_cycle, evaluate_post_promotion_health


class MemoryLifecycle:
    def __init__(self):
        self.task = LabelTask('risk', 'Risk', ('amount',), ('low', 'high'), 'local/model', policy_path='policy')
        self.policy = LabelingPolicy('risk-v1', 'risk', ('low', 'high'), 'r1', 'cal-v1', .7, 30, ())
        self.promotion = PromotionPolicy('risk', 'v1', {'accuracy': .5}, .5,
            {'low': .1, 'high': .1}, .2, {'accuracy': .2}, 2)
        self.dataset = TrainingDataset('frozen/manifest', 'frozen/train', 'a'*64, 'b'*64, 3)
        self.calls = []
        self.candidates = {}
        self.cycles = []
        self.active_record = None
        self.failure = None
        self.gate = 'c'*64
        self.action = 'promote'
        self.next_id = 0
        self.evaluation_override = {}

    def new_id(self):
        self.next_id += 1
        return str(self.next_id)

    def now(self): return '2026-10-26T00:00:00Z'
    def load_task(self, task_id):
        if self.failure == 'task': raise ValueError('task_missing')
        return self.task
    def load_labeling_policy(self, task): return self.policy
    def load_promotion_policy(self, task_id):
        if self.failure == 'config': raise ValueError('promotion_policy_missing')
        return self.promotion
    def reload_promotion_policy(self, task_id):
        if self.failure == 'config': raise FileNotFoundError('promotion policy deleted')
        return self.promotion
    def task_reference(self, task_id): return 'tasks/' + task_id
    def gate_reference(self): return 'gate'
    def gate_digest(self):
        if self.failure == 'gate': raise ValueError('training_gate_missing')
        return self.gate
    def assert_gate_unchanged(self, expected_digest):
        if self.gate != expected_digest:
            raise ValueError('training_gate_changed_during_cycle')
    def load_trusted_batch(self, task):
        if self.failure == 'trusted': raise ValueError('trusted_labels_stale')
        return SimpleNamespace(snapshot_sha256='a'*64)
    def prepare(self, batch, task):
        if self.failure == 'prepare': raise ValueError('trusted_dataset_manifest_does_not_match_live_source')
        self.calls.append(('prepare', batch, task))
        return self.dataset
    def manifest_digest(self, dataset): return dataset.manifest_sha256
    def active(self, task_id): return self.active_record
    def adapter_reference(self, candidate_id): return 'adapters/' + candidate_id
    def validate(self, task, dataset, output_reference, gate_reference):
        self.calls.append(('validate', dataset, gate_reference))
        if self.failure == 'validate': raise ValueError('training_gate_invalid')
    def train(self, task, dataset, output_reference, gate_reference):
        self.calls.append(('train', dataset, gate_reference))
        if self.failure == 'train': raise RuntimeError('training_failed')
        return TrainedAdapter(output_reference, 'local/model', 'd'*64)
    def create_candidate(self, candidate_id, payload):
        self.candidates[candidate_id] = dict(payload)
    def transition(self, candidate_id, status, **changes):
        self.candidates[candidate_id].update(status=status, **changes)
    def candidate(self, candidate_id): return self.candidates[candidate_id]
    def evaluate(self, task, policy, dataset, adapter, incumbent_adapter, *, candidate_id,
                 gate_reference, gate_sha256):
        self.calls.append(('evaluate', dataset, incumbent_adapter, gate_sha256))
        if self.failure == 'evaluate': raise RuntimeError('evaluation_failed')
        if self.failure == 'deleted_promotion': self.failure = 'config'
        if self.failure == 'changed_gate': self.gate = 'e'*64
        if self.failure == 'changed_policy': self.policy = replace(policy, rules_version='changed')
        return {'evaluation_id': 'evaluation-1', 'candidate_model_ref': 'local/model+peft:' + 'd'*64,
            'incumbent_model_ref': 'local/model', **self.evaluation_override}
    def promote_if_eligible(self, candidate_id, evaluation_id, policy):
        self.calls.append(('promote', candidate_id, evaluation_id, policy))
        if self.action == 'promote':
            self.active_record = {'model_ref': self.candidates[candidate_id]['model_ref']}
        return SimpleNamespace(action=self.action, reason_codes=() if self.action == 'promote' else ('coverage_gate_failed',))
    def find_prior(self, identity, active_ref):
        for reference, payload in self.cycles:
            if all(payload.get(k) == v for k, v in identity.items()) and (
                payload['resulting_active_model_ref'] == active_ref or
                payload['state'] == 'rejected' and payload['incumbent_model_ref'] == active_ref):
                return reference, payload
        return None, None
    def save_cycle(self, cycle_id, payload):
        reference = 'cycles/' + cycle_id
        self.cycles.append((reference, payload))
        return reference
    def rollback_if_unhealthy(self, task_id, health):
        self.calls.append(('rollback', task_id, health))
        if self.failure: raise ValueError(self.failure)
        return SimpleNamespace(action='rollback')


def run(ports):
    return run_training_cycle('risk', configuration=ports, datasets=ports, trainer=ports,
        evaluator=ports, registry=ports, cycles=ports, runtime=ports)


def test_promotes_only_after_validation_frozen_evaluation_and_gate():
    ports = MemoryLifecycle()
    result = run(ports)
    assert result.state == 'complete'
    assert result.active_model_ref == 'local/model+peft:' + 'd'*64
    assert [call[0] for call in ports.calls] == ['prepare', 'validate', 'train', 'evaluate', 'promote']
    assert ports.calls[2][1] is ports.dataset
    assert ports.calls[3][1] is ports.dataset
    candidate = ports.candidates[result.candidate_id]
    assert candidate['trusted_manifest_path'] == 'frozen/manifest'
    assert candidate['training_gate_sha256'] == 'c'*64
    assert ports.cycles[0][1]['dataset_manifest_sha256'] == 'b'*64


def test_gate_rejection_is_recorded_and_replayed_without_training_again():
    ports = MemoryLifecycle()
    ports.action = 'reject'
    first = run(ports)
    calls = list(ports.calls)
    second = run(ports)
    assert first == second
    assert first.state == 'rejected'
    assert first.reason_codes == ('coverage_gate_failed',)
    assert len(ports.calls) == len(calls) + 1
    assert ports.calls[-1][0] == 'prepare'
    assert len(ports.cycles) == 1


@pytest.mark.parametrize('failure,reason', [
    ('train', 'training_failed'), ('evaluate', 'evaluation_failed'),
    ('task', 'task_missing'), ('trusted', 'trusted_labels_stale'),
    ('prepare', 'trusted_dataset_manifest_does_not_match_live_source'),
    ('validate', 'training_gate_invalid'),
    ('config', 'promotion_policy_missing'), ('gate', 'training_gate_missing'),
    ('changed_gate', 'training_gate_changed_during_cycle'),
    ('changed_policy', 'task_or_promotion_policy_changed_during_cycle'),
])
def test_failures_never_promote(failure, reason):
    ports = MemoryLifecycle()
    ports.failure = failure
    result = run(ports)
    assert result.state == 'blocked'
    assert result.reason_codes == (reason,)
    assert not any(call[0] == 'promote' for call in ports.calls)
    assert ports.active_record is None
    assert len(ports.cycles) == 1
    if failure in {'evaluate', 'changed_gate', 'changed_policy'}:
        assert ports.candidates[result.candidate_id]['status'] == 'rejected'


@pytest.mark.parametrize('missing', ['policy', 'calibration'])
def test_missing_labeling_configuration_never_trains(missing):
    ports = MemoryLifecycle()
    ports.policy = None if missing == 'policy' else replace(ports.policy, calibration_ref=None)
    result = run(ports)
    assert result.reason_codes == (('task_labeling_policy_missing' if missing == 'policy' else 'task_calibration_ref_missing'),)
    assert ports.calls == []


@pytest.mark.parametrize('field', ['candidate_model_ref', 'incumbent_model_ref'])
def test_evaluation_identity_mismatch_rejects_candidate(field):
    ports = MemoryLifecycle()
    ports.evaluation_override[field] = 'wrong'
    result = run(ports)
    assert result.reason_codes == ('evaluation_model_identity_mismatch',)
    assert ports.candidates[result.candidate_id]['status'] == 'rejected'
    assert not any(call[0] == 'promote' for call in ports.calls)


def test_insufficient_frozen_holdout_stops_before_trainer():
    ports = MemoryLifecycle()
    ports.dataset = replace(ports.dataset, holdout_count=1)
    result = run(ports)
    assert result.reason_codes == ('holdout_count_below_minimum',)
    assert [call[0] for call in ports.calls] == ['prepare']


def test_health_rollback_uses_same_verified_registry_port_and_propagates_rejection():
    ports = MemoryLifecycle()
    evidence = {'evaluation_id': 'health-frozen'}
    assert evaluate_post_promotion_health('risk', evidence, registry=ports).action == 'rollback'
    assert ports.calls == [('rollback', 'risk', evidence)]
    ports.failure = 'health_evaluation_identity_mismatch'
    with pytest.raises(ValueError, match=ports.failure):
        evaluate_post_promotion_health('risk', evidence, registry=ports)


@pytest.mark.parametrize('active,reason', [
    ({'model_ref': 'local/model+peft:' + 'f'*64}, 'active_adapter_path_missing'),
    ({'model_ref': 'other/model+peft:' + 'f'*64, 'adapter_path': 'other'}, 'active_adapter_base_model_mismatch'),
])
def test_invalid_active_adapter_stops_before_training_and_preserves_pointer(active, reason):
    ports = MemoryLifecycle()
    ports.active_record = active
    result = run(ports)
    assert result.reason_codes == (reason,)
    assert ports.active_record is active
    assert [call[0] for call in ports.calls] == ['prepare']


def test_promotion_policy_deleted_after_evaluation_retains_io_failure_reason():
    ports = MemoryLifecycle()
    ports.failure = 'deleted_promotion'
    result = run(ports)
    expected = 'cycle_prerequisite_failed:FileNotFoundError'
    assert result.state == 'blocked'
    assert result.reason_codes == (expected,)
    assert ports.candidates[result.candidate_id]['status'] == 'rejected'
    assert ports.candidates[result.candidate_id]['rejection_reasons'] == [expected]
    assert ports.cycles[0][1]['reason_codes'] == [expected]
    assert not any(call[0] == 'promote' for call in ports.calls)
