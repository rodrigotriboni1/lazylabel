"""Autonomous selected-field labeling with injected publication and runtime ports."""
import re
from dataclasses import replace
from typing import Optional
from lazylabel.application.ports.sources import ReadOnlySource, SourceReader
from lazylabel.application.ports.projects import ProjectLookup
from lazylabel.application.use_cases.projects import _resolve_source
from lazylabel.application.ports.labeling import LabelingRuntime, PredictionBackend, CalibrationBackend, LabelRunStore
from lazylabel.application.use_cases.errors import PersistenceError
from lazylabel.domain.labeling.outcomes import LabelOutcome
from lazylabel.domain.labeling.task import LabelTask
from lazylabel.domain.labeling.policy import LabelingPolicy, policy_matches_task
from lazylabel.domain.labeling.prediction import Prediction, PredictionError
from lazylabel.domain.labeling.decisions import choose_quarantine_reason, rules_match as _rules_match, validate_calibration


def _too_stale(reason, row_started, policy, runtime):
    return "stale_source" if runtime.monotonic() - row_started > policy.max_staleness_seconds else reason


def _persist(store, **payload):
    try:
        return store.save_run(**payload)
    except Exception as exc:
        raise PersistenceError("Could not persist labeling run.") from exc


def _model_ref_for_prediction(task: LabelTask, backend) -> str:
    explicit = getattr(backend, "model_ref", None)
    if isinstance(explicit, str) and explicit:
        return explicit
    model_id = getattr(backend, "model_id", None) or task.model_id
    revision = getattr(backend, "revision", None) or task.model_revision
    return "{}@{}".format(model_id, revision) if revision else str(model_id)


def _calibrated_confidence(calibrator, prediction: Prediction, *, task: LabelTask,
                           policy: LabelingPolicy, model_ref: str):
    """Read a strict calibration result from the future calibration backend.

    Contract: calibrator.calibrate(prediction, *, task, policy, model_ref) returns
    an object exposing task_id, policy_id, model_ref, confidence_method,
    calibration_ref, and confidence. Every identity must match this run exactly.
    """
    if calibrator is None or policy.calibration_ref is None or prediction.confidence_evidence is None:
        return None
    if set(prediction.confidence_evidence) != set(task.labels):
        return None
    try:
        result = calibrator.calibrate(
            prediction, task=task, policy=policy, model_ref=model_ref
        )
        return validate_calibration(result, prediction, task, policy, model_ref)
    except Exception:
        # Missing, malformed, mismatched, and failing calibration all abstain.
        return None


def _outcome(*, run_id: str, record_ref: str, input_digest: str, task: LabelTask,
             policy: Optional[LabelingPolicy], model_ref: str, label: Optional[str],
             reason_code: Optional[str], confidence: Optional[float] = None, runtime: LabelingRuntime) -> LabelOutcome:
    return LabelOutcome(
        run_id=run_id,
        record_ref=record_ref,
        input_digest=input_digest,
        task_id=task.task_id,
        policy_id=policy.policy_id if policy is not None else None,
        model_ref=model_ref,
        predicted_label=label,
        state="applied" if reason_code is None else "quarantined",
        reason_code=reason_code,
        confidence=confidence,
        created_at=runtime.now(),
    )


def _snapshot(source, source_name, columns, runtime):
    """Read selected columns only and return an in-memory identity/digest view."""
    snapshot = {}
    conflicting = set()
    for index, record in enumerate(source.iter_records(columns), start=1):
        selected_values = {
            name: record.values[name] for name in columns if name in record.values
        }
        digest = runtime.selected_digest(selected_values)
        key = str(record.record_id) if record.record_id is not None else "@missing:{}".format(index)
        record_ref = runtime.record_ref(source_name, key)
        previous = snapshot.get(key)
        if previous is not None and previous != digest:
            conflicting.add(record_ref)
        elif previous is None:
            snapshot[key] = digest
    return snapshot, conflicting


def run_labeling(source: ReadOnlySource, source_name: str, task: LabelTask,
                 policy: Optional[LabelingPolicy], backend: PredictionBackend,
                 store: LabelRunStore, runtime: LabelingRuntime, *,
                 calibrator: Optional[CalibrationBackend] = None) -> object:
    """Run local labeling and atomically persist one terminal outcome per source ID.

    The input source is checked as read-only and is never modified. Outcomes
    contain only digests, opaque references, task/model provenance, and labels;
    raw values, prompts, and free-form model rationales are intentionally dropped.
    """
    capabilities = source.capabilities()
    if not capabilities.read_only:
        raise ValueError("Autonomous labeling requires a read-only source.")
    if not capabilities.stable_record_ids:
        raise ValueError("Autonomous labeling requires stable source record IDs.")
    if not capabilities.selected_columns:
        raise ValueError("Autonomous labeling requires selected-column reads.")
    run_id = runtime.new_id()
    started_at = runtime.now()
    model_ref = _model_ref_for_prediction(task, backend)
    policy_is_valid = policy is not None and policy_matches_task(policy, task)
    outcomes = []
    keys_to_positions = {}
    outcome_keys = []
    first_snapshot = {}
    conflicting_refs = set()

    for row_number, record in enumerate(source.iter_records(task.input_columns), start=1):
        selected_values = {
            name: record.values[name] for name in task.input_columns if name in record.values
        }
        input_digest = runtime.selected_digest(selected_values)
        row_key = str(record.record_id) if record.record_id is not None else "@missing:{}".format(row_number)
        opaque_ref = runtime.record_ref(source_name, row_key)

        # Duplicate source IDs are one logical result. Conflicting duplicate
        # contents invalidate that result rather than allowing either label.
        previous_digest = first_snapshot.get(row_key)
        if previous_digest is not None:
            if previous_digest != input_digest:
                conflicting_refs.add(opaque_ref)
                position = keys_to_positions[row_key]
                outcomes[position] = replace(
                    outcomes[position], state="quarantined", reason_code="stale_source",
                    predicted_label=None, confidence=None, created_at=runtime.now(),
                )
            continue
        first_snapshot[row_key] = input_digest
        keys_to_positions[row_key] = len(outcomes)
        outcome_keys.append(row_key)

        invalid_selected_columns = set(selected_values) != set(task.input_columns)
        reported_digest = getattr(record, "input_digest", None)
        digest_mismatch = (
            not isinstance(reported_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", reported_digest)
            or reported_digest != input_digest
        )
        if record.record_id is None or invalid_selected_columns or digest_mismatch:
            outcomes.append(_outcome(
                runtime=runtime,
                run_id=run_id, record_ref=opaque_ref, input_digest=input_digest,
                task=task, policy=policy, model_ref=model_ref, label=None,
                reason_code="stale_source",
            ))
            continue

        if policy is None:
            outcomes.append(_outcome(
                runtime=runtime,
                run_id=run_id, record_ref=opaque_ref, input_digest=input_digest,
                task=task, policy=None, model_ref=model_ref, label=None,
                reason_code="missing_policy",
            ))
            continue
        if not policy_is_valid:
            outcomes.append(_outcome(
                runtime=runtime,
                run_id=run_id, record_ref=opaque_ref, input_digest=input_digest,
                task=task, policy=policy, model_ref=model_ref, label=None,
                reason_code="rule_conflict",
            ))
            continue

        if not _rules_match(policy.rules, selected_values):
            outcomes.append(_outcome(
                runtime=runtime,
                run_id=run_id, record_ref=opaque_ref, input_digest=input_digest,
                task=task, policy=policy, model_ref=model_ref, label=None,
                reason_code="rule_conflict",
            ))
            continue

        row_started = runtime.monotonic()
        try:
            if not callable(getattr(backend, "predict", None)):
                raise RuntimeError("Backend does not implement structured prediction.")
            prediction = backend.predict(
                selected_values, task=task, max_new_tokens=256
            )
        except PredictionError as exc:
            reason = exc.reason_code if exc.reason_code in {"unknown_label", "invalid_output"} else "invalid_output"
            reason = _too_stale(reason, row_started, policy, runtime)
            outcomes.append(_outcome(
                runtime=runtime,
                run_id=run_id, record_ref=opaque_ref, input_digest=input_digest,
                task=task, policy=policy, model_ref=model_ref, label=None,
                reason_code=reason,
            ))
            continue
        except Exception:
            reason = _too_stale("backend_error", row_started, policy, runtime)
            outcomes.append(_outcome(
                runtime=runtime,
                run_id=run_id, record_ref=opaque_ref, input_digest=input_digest,
                task=task, policy=policy, model_ref=model_ref, label=None,
                reason_code=reason,
            ))
            continue

        if not isinstance(prediction, Prediction):
            reason = _too_stale("invalid_output", row_started, policy, runtime)
            outcomes.append(_outcome(
                runtime=runtime,
                run_id=run_id, record_ref=opaque_ref, input_digest=input_digest,
                task=task, policy=policy, model_ref=model_ref, label=None,
                reason_code=reason,
            ))
            continue
        if prediction.label is None or prediction.label not in task.labels or prediction.label not in policy.allowed_labels:
            reason = choose_quarantine_reason(
                task, policy, prediction.label, None, runtime.monotonic() - row_started
            )
            outcomes.append(_outcome(
                runtime=runtime,
                run_id=run_id, record_ref=opaque_ref, input_digest=input_digest,
                task=task, policy=policy, model_ref=model_ref, label=None,
                reason_code=reason,
            ))
            continue
        confidence = _calibrated_confidence(
            calibrator, prediction, task=task, policy=policy, model_ref=model_ref
        )
        reason = choose_quarantine_reason(
            task, policy, prediction.label, confidence, runtime.monotonic() - row_started
        )
        outcomes.append(_outcome(
            runtime=runtime,
            run_id=run_id, record_ref=opaque_ref, input_digest=input_digest,
            task=task, policy=policy, model_ref=model_ref,
            label=prediction.label if reason is None else prediction.label,
            reason_code=reason, confidence=confidence,
        ))

    def revalidate_before_publish(staged_outcomes):
        # Re-read selected values after artifacts are staged and directly
        # before metadata/atomic publication. No source lock is available.
        current_snapshot, current_conflicts = _snapshot(source, source_name, task.input_columns, runtime)
        checked = []
        for index, outcome in enumerate(staged_outcomes):
            key = outcome_keys[index]
            source_ref = runtime.record_ref(source_name, key)
            changed = (
                current_snapshot.get(key) != first_snapshot.get(key)
                or source_ref in current_conflicts
                or source_ref in conflicting_refs
            )
            if changed:
                outcome = replace(
                    outcome, state="quarantined", reason_code="stale_source",
                    predicted_label=None, confidence=None, created_at=runtime.now(),
                )
            checked.append(outcome)
        return tuple(checked)

    return _persist(store,
        run_id=run_id,
        task_id=task.task_id,
        policy_id=policy.policy_id if policy is not None else None,
        model_ref=model_ref,
        started_at=started_at,
        outcomes=outcomes,
        before_publish=revalidate_before_publish,
    )


def label_project(projects: ProjectLookup, sources: SourceReader, project_reference: str,
                  source_name: str, task: LabelTask, policy: Optional[LabelingPolicy],
                  backend: PredictionBackend, store: LabelRunStore, runtime: LabelingRuntime, *,
                  calibrator: Optional[CalibrationBackend] = None) -> object:
    source = _resolve_source(projects, sources, project_reference, source_name)
    return run_labeling(source, source_name, task, policy, backend, store, runtime, calibrator=calibrator)
