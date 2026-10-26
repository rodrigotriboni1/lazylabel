"""Trusted-label training orchestration with injected effects and fail-closed gates."""
from dataclasses import dataclass

from finlabel.application.ports.analysis import RunIdentity
from finlabel.application.ports.training import (TrainingConfiguration, TrustedDatasets,
    Trainer, CandidateEvaluator, TrainingRegistry, TrainingCycles)
from finlabel.domain.training.evaluation import labeling_policy_sha256
from finlabel.domain.training.task_spec import task_spec_sha256


@dataclass(frozen=True)
class TrainingCycleSummary:
    cycle_id: str
    task_id: str
    state: str
    reason_codes: tuple
    candidate_id: str | None
    evaluation_id: str | None
    promotion_action: str | None
    active_model_ref: str | None
    manifest_path: str


def _summary(reference, payload):
    return TrainingCycleSummary(payload['cycle_id'], payload['task_id'], payload['state'],
        tuple(payload.get('reason_codes', ())), payload.get('candidate_id'), payload.get('evaluation_id'),
        payload.get('promotion_action'), payload.get('active_model_ref'), str(reference))


def _reason(exc):
    message = str(exc)
    if message and message.isascii() and message.islower() and ' ' not in message and len(message) < 100:
        return message
    return 'cycle_prerequisite_failed:' + type(exc).__name__


def run_training_cycle(task_id: str, *, configuration: TrainingConfiguration,
                       datasets: TrustedDatasets, trainer: Trainer, evaluator: CandidateEvaluator,
                       registry: TrainingRegistry, cycles: TrainingCycles,
                       runtime: RunIdentity) -> TrainingCycleSummary:
    """Train trusted train rows, evaluate frozen calibration/holdout, then request gates.

    The registry port owns locked artifact validation and the domain promotion
    decision. This use case revalidates configuration immediately before calling
    it; exceptions always leave a blocked cycle and reject an existing candidate.
    """
    task = policy = manifest = None
    candidate_id = evaluation_id = action = None
    cycle_id = runtime.new_id()
    state, reasons = 'blocked', []
    snapshot = policy_sha256 = labeling_sha256 = task_digest = gate_digest = incumbent_ref = None
    try:
        task = configuration.load_task(task_id)
        policy = configuration.load_labeling_policy(task)
        if policy is None:
            raise ValueError('task_labeling_policy_missing')
        if policy.calibration_ref is None:
            raise ValueError('task_calibration_ref_missing')
        promotion_policy = configuration.load_promotion_policy(task_id)
        batch = datasets.load_trusted_batch(task)
        snapshot = batch.snapshot_sha256
        policy_sha256 = promotion_policy.policy_sha256
        labeling_sha256 = labeling_policy_sha256(policy)
        task_digest = task_spec_sha256(task)
        gate_reference = configuration.gate_reference()
        gate_digest = configuration.gate_digest()
        manifest = datasets.prepare(batch, task)
        active = registry.active(task_id)
        base_ref = task.model_id + ('@' + task.model_revision if task.model_revision else '')
        incumbent_ref = active.get('model_ref') if active else base_ref
        identity = {'task_id': task_id, 'snapshot_sha256': snapshot,
                    'task_spec_sha256': task_digest, 'labeling_policy_sha256': labeling_sha256,
                    'training_gate_sha256': gate_digest, 'policy_sha256': policy_sha256,
                    'incumbent_model_ref': incumbent_ref}
        previous_reference, previous = cycles.find_prior(identity, incumbent_ref)
        if previous:
            return _summary(previous_reference, previous)
        if manifest.holdout_count < promotion_policy.min_holdout_count:
            raise ValueError('holdout_count_below_minimum')
        incumbent_adapter = active.get('adapter_path') if active else None
        if active and not incumbent_adapter:
            raise ValueError('active_adapter_path_missing')
        if active and not incumbent_ref.startswith(base_ref + '+peft:'):
            raise ValueError('active_adapter_base_model_mismatch')

        candidate_id = runtime.new_id()
        output = registry.adapter_reference(candidate_id)
        trainer.validate(task, manifest, output, gate_reference)
        result = trainer.train(task, manifest, output, gate_reference)
        candidate_ref = '{}+peft:{}'.format(result.base_model_ref, result.artifact_sha256)
        registry.create_candidate(candidate_id, {
            'task_id': task_id, 'model_ref': candidate_ref, 'adapter_path': result.output_reference,
            'incumbent_model_ref': incumbent_ref, 'expected_active_model_ref': incumbent_ref,
            'snapshot_sha256': snapshot, 'policy_sha256': promotion_policy.policy_sha256,
            'labeling_policy_sha256': labeling_policy_sha256(policy),
            'labeling_policy_min_confidence': policy.min_calibrated_confidence,
            'task_labels': list(task.labels),
            'task_path': configuration.task_reference(task_id),
            'labeling_policy_path': task.policy_path,
            'trusted_manifest_path': manifest.manifest_reference,
            'training_gate_path': gate_reference,
            'training_gate_sha256': gate_digest,
        })
        registry.transition(candidate_id, 'training')
        evaluation = evaluator.evaluate(task, policy, manifest, result, incumbent_adapter,
            candidate_id=candidate_id, gate_reference=gate_reference, gate_sha256=gate_digest)
        if evaluation['candidate_model_ref'] != candidate_ref or evaluation['incumbent_model_ref'] != incumbent_ref:
            raise ValueError('evaluation_model_identity_mismatch')
        evaluation_id = evaluation['evaluation_id']
        registry.transition(candidate_id, 'evaluated', evaluation_id=evaluation_id)
        current_task = configuration.load_task(task_id)
        current_policy = configuration.load_labeling_policy(current_task)
        current_promotion = configuration.reload_promotion_policy(task_id)
        if (task_spec_sha256(current_task) != task_spec_sha256(task) or current_policy is None
                or labeling_policy_sha256(current_policy) != labeling_policy_sha256(policy)
                or current_promotion.policy_sha256 != promotion_policy.policy_sha256):
            raise ValueError('task_or_promotion_policy_changed_during_cycle')
        configuration.assert_gate_unchanged(gate_digest)
        decision = promote_if_eligible(candidate_id, evaluation_id, current_promotion, registry=registry)
        action = decision.action
        state = 'complete' if action == 'promote' else 'rejected'
        reasons = list(decision.reason_codes)
    except Exception as exc:
        reasons = [_reason(exc)]
        if candidate_id:
            try:
                current = registry.candidate(candidate_id)
                if current['status'] in {'training', 'evaluated'}:
                    registry.transition(candidate_id, 'rejected', rejection_reasons=reasons)
            except Exception:
                pass
    active = registry.active(task_id)
    payload = {
        'schema_version': 1, 'cycle_id': cycle_id, 'task_id': task_id, 'state': state,
        'reason_codes': reasons, 'candidate_id': candidate_id, 'evaluation_id': evaluation_id,
        'promotion_action': action, 'active_model_ref': active.get('model_ref') if active else None,
        'snapshot_sha256': snapshot, 'policy_sha256': policy_sha256,
        'labeling_policy_sha256': labeling_sha256, 'task_spec_sha256': task_digest,
        'training_gate_sha256': gate_digest, 'incumbent_model_ref': incumbent_ref,
        'resulting_active_model_ref': active.get('model_ref') if active else None,
        'dataset_manifest_sha256': datasets.manifest_digest(manifest) if manifest else None,
        'created_at': runtime.now(),
    }
    reference = cycles.save_cycle(cycle_id, payload)
    return _summary(reference, payload)


def promote_if_eligible(candidate_id, evaluation_id, policy, *, registry: TrainingRegistry):
    """One idempotent registry decision path with no confirmation override."""
    return registry.promote_if_eligible(candidate_id, evaluation_id, policy)


def evaluate_post_promotion_health(task_id, health_evaluation, *, registry: TrainingRegistry):
    """Use the same locked, verified health evidence/rollback gates for every caller."""
    return registry.rollback_if_unhealthy(task_id, health_evaluation)
