"""File-backed training ports preserve frozen data and fail-closed lifecycle gates."""
import hashlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def training_project(tmp_path):
    from lazylabel.project import init_project, load_project, save_project
    from lazylabel.sources.base import ProjectConfig, SourceSpec
    from lazylabel.labeling.task import LabelTask, save_task, task_file_path
    from lazylabel.training.trusted_labels import TrustedLabelSourceSpec, supervision_key
    config_path = init_project(tmp_path)
    source = tmp_path / 'reference.csv'
    source.write_text('amount,class\n' + ''.join('{},{}\n'.format(i, 'L' if i < 14 else 'H') for i in range(28)))
    workspace = config_path.parent
    policy = workspace / 'tasks' / 'risk-policy.json'
    policy.write_text(json.dumps({'policy_id': 'risk-v1', 'task_id': 'risk', 'allowed_labels': ['low', 'high'],
        'rules_version': 'r1', 'rules': [{'field': 'amount', 'operator': 'number_between', 'minimum': 0}], 'calibration_ref': 'cal-v1',
        'min_calibrated_confidence': .7, 'max_staleness_seconds': 30}))
    task = LabelTask('risk', 'classify', ('amount',), ('low', 'high'), 'local/model', policy_path=str(policy))
    save_task(task, task_file_path(workspace, task.task_id))
    trusted = TrustedLabelSourceSpec('reference', 'risk', 'class', {'L': 'low', 'H': 'high'},
                                     'reference-v1', 'provided_ground_truth')
    save_project(ProjectConfig(config_path, {'reference': SourceSpec('reference', 'csv', source)}, {}, workspace,
                              {supervision_key('risk', 'reference'): trusted.to_dict()}), config_path)
    return load_project(config_path), task, source


def test_training_ports_freeze_and_reverify_identical_dataset_bytes(training_project):
    from lazylabel.adapters.outbound.training.lifecycle import LocalTrainingEffects
    project, task, source = training_project
    before = source.read_bytes()
    effects = LocalTrainingEffects(project)
    batch = effects.load_trusted_batch(task)
    dataset = effects.prepare(batch, task)
    manifest = Path(dataset.manifest_reference)
    files = {file.name: file.read_bytes() for file in manifest.parent.iterdir()}
    assert dataset.holdout_count > 0
    assert effects.manifest_digest(dataset) == hashlib.sha256(files['manifest.json']).hexdigest()
    assert effects.prepare(batch, task) == dataset
    assert {file.name: file.read_bytes() for file in manifest.parent.iterdir()} == files
    Path(dataset.train_reference).write_bytes(files['train.jsonl'] + b'\n')
    with pytest.raises(ValueError, match='trusted_dataset_partition_does_not_match_live_source:train'):
        effects.prepare(batch, task)
    assert source.read_bytes() == before


def test_training_validation_uses_verified_train_manifest_without_loading_optional_models(training_project):
    from lazylabel.adapters.outbound.training.lifecycle import LocalTrainingEffects
    project, task, _ = training_project
    effects = LocalTrainingEffects(project)
    dataset = effects.prepare(effects.load_trusted_batch(task), task)
    gate = Path(effects.gate_reference())
    gate.write_text(json.dumps({'authorized': True, 'model_id': 'local/model', 'license': 'fixture',
        'hardware': 'cpu', 'data_policy': 'synthetic', 'evaluation_protocol': 'frozen'}))
    effects.validate(task, dataset, str(project.workspace_dir / 'new-adapter'), str(gate))
    Path(dataset.train_reference).write_text('{}\n')
    with pytest.raises(ValueError, match='prompt and completion'):
        effects.validate(task, dataset, str(project.workspace_dir / 'new-adapter'), str(gate))


def test_cycle_port_checks_integrity_and_resulting_active_identity(training_project):
    from lazylabel.adapters.outbound.training.lifecycle import LocalTrainingEffects
    project, _, _ = training_project
    effects = LocalTrainingEffects(project)
    identity = {'task_id': 'risk', 'snapshot_sha256': 'b'*64, 'incumbent_model_ref': 'base'}
    payload = dict(identity, cycle_id='a'*32, state='complete', resulting_active_model_ref='active')
    path = Path(effects.save_cycle('a'*32, payload))
    reference, prior = effects.find_prior(identity, 'active')
    assert reference == path
    assert prior['cycle_id'] == 'a'*32
    assert effects.find_prior(identity, 'different') == (None, None)
    raw = json.loads(path.read_text())
    raw['state'] = 'rejected'
    path.write_text(json.dumps(raw))
    assert effects.find_prior(identity, 'active') == (None, None)


def test_registry_port_rejects_unverified_health_and_keeps_pointer_unchanged(training_project):
    from lazylabel.adapters.outbound.training.lifecycle import LocalTrainingEffects
    from lazylabel.application.use_cases.training import evaluate_post_promotion_health
    project, _, _ = training_project
    effects = LocalTrainingEffects(project)
    pointer = effects.registry.active_path
    pointer.write_text('{"risk":{"model_ref":"active"}}\n')
    original = pointer.read_bytes()
    with pytest.raises(ValueError, match='health_evaluation_schema_invalid'):
        evaluate_post_promotion_health('risk', {}, registry=effects)
    assert pointer.read_bytes() == original


def test_training_cycle_through_real_ports_blocks_without_configured_gate(training_project):
    from lazylabel.adapters.outbound.training.lifecycle import LocalTrainingEffects
    from lazylabel.application.use_cases.training import run_training_cycle
    project, task, _ = training_project
    effects = LocalTrainingEffects(project)
    policy_path = effects.registry.root / 'promotion-policies' / 'risk.json'
    policy_path.parent.mkdir()
    policy_path.write_text(json.dumps({'task_id': 'risk', 'version': 'v1', 'required_metrics': {'macro_f1': .5},
        'minimum_coverage': .5, 'allowed_per_label_regression': {'low': .1, 'high': .1},
        'max_calibration_error': .2, 'rollback_monitor_limits': {'accuracy': .2}, 'min_holdout_count': 2}))
    summary = run_training_cycle(task.task_id, configuration=effects, datasets=effects, trainer=effects,
                                evaluator=effects, registry=effects, cycles=effects, runtime=effects)
    assert summary.state == 'blocked'
    assert summary.reason_codes == ('training_gate_missing',)
    assert effects.active(task.task_id) is None
    assert Path(summary.manifest_path).is_file()
