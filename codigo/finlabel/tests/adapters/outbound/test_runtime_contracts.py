"""Port integration against real file-backed adapters, with no model execution."""
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest


MODULE_PAIRS = [
    ('finlabel.monitor', 'finlabel.adapters.outbound.persistence.baselines'),
    ('finlabel.review', 'finlabel.adapters.outbound.persistence.reviews'),
    ('finlabel.labeling.task', 'finlabel.adapters.outbound.persistence.tasks'),
    ('finlabel.labeling.policy', 'finlabel.adapters.outbound.persistence.policies'),
    ('finlabel.labeling.outcomes', 'finlabel.adapters.outbound.persistence.label_runs'),
    ('finlabel.labeling.suggestions', 'finlabel.adapters.outbound.persistence.suggestions'),
    ('finlabel.analysis.service', 'finlabel.adapters.outbound.persistence.analysis_runs'),
    ('finlabel.analysis.planner', 'finlabel.adapters.outbound.models.analysis_planner'),
    ('finlabel.analysis.charts', 'finlabel.adapters.outbound.persistence.charts'),
    ('finlabel.labeling.service', 'finlabel.adapters.outbound.models.labeling'),
    ('finlabel.models.text_generation', 'finlabel.adapters.outbound.models.text_generation'),
    ('finlabel.training.backend', 'finlabel.adapters.outbound.training.backend'),
    ('finlabel.training.jobs', 'finlabel.adapters.outbound.training.jobs'),
    ('finlabel.training.dataset', 'finlabel.adapters.outbound.persistence.datasets'),
    ('finlabel.training.evaluation', 'finlabel.adapters.outbound.training.evaluation'),
    ('finlabel.training.registry', 'finlabel.adapters.outbound.persistence.registry'),
    ('finlabel.training.trusted_labels', 'finlabel.adapters.outbound.sources.trusted_labels'),
    ('finlabel.training.active_model', 'finlabel.adapters.outbound.models.active_model'),
    ('finlabel.training.local_evaluator', 'finlabel.adapters.outbound.training.local_evaluator'),
    ('finlabel.training.autopipeline', 'finlabel.adapters.outbound.training.lifecycle'),
]


@pytest.mark.parametrize('legacy,concrete', MODULE_PAIRS)
def test_public_module_identity_preserves_extensions_and_exception_types(legacy, concrete):
    # Losing module identity silently breaks legacy extension/patch points.
    assert importlib.import_module(legacy) is importlib.import_module(concrete)


def test_importing_all_adapters_and_legacy_entry_points_keeps_optional_libraries_lazy():
    names = [new for old, new in MODULE_PAIRS] + ['finlabel', 'finlabel.cli']
    script = ('import importlib, sys\n' +
              '\n'.join('importlib.import_module({!r})'.format(name) for name in names) +
              '\nassert not set(sys.modules).intersection({"torch", "transformers", "peft", "trl", "fastapi"})\n')
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_label_store_rechecks_after_staging_and_rewrites_only_before_publication(tmp_path):
    from finlabel.adapters.outbound.persistence.label_runs import FileLabelRunStore
    from finlabel.domain.labeling.outcomes import LabelOutcome
    outcome = LabelOutcome('a'*32, 'b'*64, 'c'*64, 'risk', 'policy', 'model', 'low',
                           'applied', None, .9, '2026-10-26T00:00:00Z')
    store = FileLabelRunStore(tmp_path)
    def freshness(staged):
        assert not (tmp_path / 'label-runs' / outcome.run_id).exists()
        assert len(list((tmp_path / 'label-runs').glob('.*-*/outcomes.jsonl'))) == 1
        return (replace(staged[0], state='quarantined', reason_code='stale_source'),)
    receipt = store.save_run(run_id=outcome.run_id, task_id='risk', policy_id='policy',
        model_ref='model', started_at=outcome.created_at, outcomes=(outcome,), before_publish=freshness)
    rows = receipt.outcomes_path.read_bytes()
    assert b'"state":"quarantined"' in rows
    assert b'"reason_code":"stale_source"' in rows
    metadata = json.loads(receipt.run_metadata_path.read_text())
    assert metadata['outcomes_sha256'] == hashlib.sha256(rows).hexdigest()
    assert metadata['applied_count'] == 0
    assert metadata['quarantined_count'] == 1
    assert metadata['source_rechecked_before_publish'] is True
    assert not list((tmp_path / 'label-runs').glob('.*-*'))


def test_label_store_callback_failure_discards_staging(tmp_path):
    from finlabel.adapters.outbound.persistence.label_runs import FileLabelRunStore
    def changed(_):
        raise OSError('freshness unavailable')
    with pytest.raises(OSError, match='freshness unavailable'):
        FileLabelRunStore(tmp_path).save_run(run_id='a'*32, task_id='risk', policy_id=None,
            model_ref='model', started_at='now', outcomes=(), before_publish=changed)
    assert list((tmp_path / 'label-runs').iterdir()) == []


def test_local_runtime_hashes_selected_fields_and_opaque_record_references():
    from finlabel.adapters.outbound.persistence.runtime import LocalRuntime
    runtime = LocalRuntime()
    assert runtime.selected_digest({'amount': '10'}) == hashlib.sha256(b'{"amount":"10"}').hexdigest()
    assert runtime.record_ref('ledger', 'a') == hashlib.sha256(b'ledger\0a').hexdigest()
    assert len(runtime.new_id()) == 32
    assert runtime.now().endswith('Z')
    assert runtime.monotonic() > 0
