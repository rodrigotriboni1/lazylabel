"""Trusted-label training cycle with fail-closed automatic promotion."""

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from finlabel.labeling.task import load_task, task_file_path
from finlabel.project import load_project
from finlabel.training.backend import TrainingConfig
from finlabel.training.dataset import prepare_trusted_dataset
from finlabel.training.jobs import TrainingJobManager
from finlabel.training.registry import ModelRegistry, PromotionPolicy
from finlabel.training.task_spec import task_spec_sha256
from finlabel.training.trusted_labels import load_trusted_labels


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


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_manifest(manifest):
    if _sha(manifest.manifest_path) != manifest.manifest_sha256:
        raise ValueError("trusted_manifest_changed")
    raw = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
    if raw.get("task_spec_sha256") != manifest.task_spec_sha256:
        raise ValueError("task_spec_changed")
    return raw


def _write_cycle(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def run_training_cycle(project, task_id, *, backend_factory):
    """Run a task's configured trusted cycle. The callback contract is explicit and provenance bound.

    backend_factory(stage, **kwargs) returns a callable evaluator for ``calibration``
    or ``holdout``. A holdout evaluator receives the immutable partition path and must
    return the registry evaluation schema. Calibration additionally requires exact
    reference-aligned predictions. This makes model score provenance auditable and
    prevents opaque callback claims from being treated as proof.
    """
    project = load_project(project.config_path if hasattr(project, "config_path") else project)
    cycle_id = uuid4().hex
    cycles_dir = project.workspace_dir / "training" / "cycles"
    cycles_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cycles_dir / (cycle_id + ".json")
    state, reasons, candidate_id, evaluation_id, action = "rejected", [], None, None, None
    task = None
    registry = ModelRegistry(project.workspace_dir)
    try:
        task_path = task_file_path(project.workspace_dir, task_id)
        task = load_task(task_path)
        policy_path = registry.root / "promotion-policies" / (task_id + ".json")
        policy = PromotionPolicy.load(policy_path, task_id=task_id)
        batch = load_trusted_labels(project, task)
        dataset = prepare_trusted_dataset(batch, task, workspace_dir=project.workspace_dir)
        raw = _read_manifest(dataset)
        train = raw["partitions"]["train"]
        calibration = raw["partitions"]["calibration"]
        holdout = raw["partitions"]["holdout"]
        calibration_entries = calibration.get("records")
        holdout_entries = holdout.get("records")
        if not isinstance(calibration_entries, list) or not isinstance(holdout_entries, list):
            raise ValueError("frozen_partition_record_provenance_missing")
        if train["count"] < len(task.labels) or calibration["count"] < len(task.labels) or holdout["count"] < policy.min_holdout_count:
            raise ValueError("minimum_partition_counts_not_met")
        candidate_id = uuid4().hex
        candidate_root = registry.root / "candidates" / task_id / candidate_id
        config = TrainingConfig(task.model_id, task.model_revision, candidate_root / "adapter")
        backend = backend_factory("training", task=task, dataset=dataset, candidate_id=candidate_id)
        manager = TrainingJobManager(project.workspace_dir)
        baseline = registry.active(task_id)
        if baseline is None:
            raise ValueError("incumbent_model_not_registered")
        registry.create_candidate(candidate_id, {"task_id": task_id, "model_ref": str(config.output_dir),
                                                 "task_spec_sha256": task_spec_sha256(task),
                                                 "dataset_manifest_sha256": dataset.manifest_sha256,
                                                 "incumbent_model_ref": baseline["model_ref"]})
        registry.transition(candidate_id, "training")
        trained = manager.run_isolated(dataset.path / "train.jsonl", config,
                                       train_dataset_path=dataset.path / train["path"])
        adapter_files = [path for path in trained.adapter_files if path.is_file()]
        adapter_digest = hashlib.sha256("".join(sorted(_sha(path) for path in adapter_files)).encode()).hexdigest()
        model_ref = str(config.output_dir) + "#" + adapter_digest

        # Calibration evidence must be generated by the declared model-scoring backend,
        # bound to the exact train candidate or incumbent. Never trust free-form scores.
        calibration_runner = backend_factory("calibration", task=task, dataset=dataset,
                                             model_ref=model_ref, candidate_id=candidate_id)
        calibration_evidence = calibration_runner(partition_path=dataset.path / calibration["path"],
                                                  partition_sha256=calibration["dataset_sha256"],
                                                  record_refs=[row["record_ref"] for row in calibration_entries])
        if (not isinstance(calibration_evidence, dict) or calibration_evidence.get("model_ref") != model_ref
                or calibration_evidence.get("method") != "label_json_mean_log_likelihood_v2"
                or calibration_evidence.get("partition_sha256") != calibration["dataset_sha256"]
                or calibration_evidence.get("dataset_manifest_sha256") != dataset.manifest_sha256
                or calibration_evidence.get("task_spec_sha256") != task_spec_sha256(task)):
            raise ValueError("calibration_model_provenance_unverified")

        holdout_runner = backend_factory("holdout", task=task, dataset=dataset,
                                         candidate_id=candidate_id, model_ref=model_ref)
        result = holdout_runner(partition_path=dataset.path / holdout["path"],
                                partition_sha256=holdout["dataset_sha256"],
                                dataset_manifest_sha256=dataset.manifest_sha256,
                                candidate_model_ref=model_ref, incumbent_model_ref=baseline["model_ref"],
                                trusted_record_refs=[row["record_ref"] for row in holdout_entries])
        if not isinstance(result, dict):
            raise ValueError("evaluation_result_invalid")
        if (result.get("dataset_manifest_sha256") != dataset.manifest_sha256
                or result.get("holdout_sha256") != holdout["dataset_sha256"]
                or result.get("candidate_model_ref") != model_ref
                or result.get("incumbent_model_ref") != baseline["model_ref"]):
            raise ValueError("evaluation_model_or_partition_provenance_unverified")
        evaluation_id = uuid4().hex
        result.update({"schema_version": 1, "task_id": task_id, "candidate_id": candidate_id,
                       "policy_sha256": policy.policy_sha256, "same_frozen_holdout": True,
                       "candidate_model_ref": model_ref, "incumbent_model_ref": baseline["model_ref"],
                       "holdout_sha256": holdout["sha256"], "holdout_dataset_sha256": holdout["dataset_sha256"],
                       "dataset_manifest_sha256": dataset.manifest_sha256, "holdout_count": holdout["count"],
                       "trusted_label_provenance": {"source_name": batch.source_name,
                           "provenance_id": batch.provenance_id, "trust_kind": batch.trust_kind,
                           "snapshot_sha256": batch.snapshot_sha256},
                       "calibration_sha256": _sha(dataset.path / calibration["path"]),
                       "calibration_model_ref": calibration_evidence["model_ref"],
                       "calibration_evidence_sha256": hashlib.sha256(json.dumps(calibration_evidence, sort_keys=True).encode()).hexdigest()})
        evaluation_dir = registry.root / "evaluations"
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        evaluation_path = evaluation_dir / (evaluation_id + ".json")
        _write_cycle(evaluation_path, result)
        registry.transition(candidate_id, "evaluated", model_ref=model_ref)
        decision = registry.promote_if_eligible(candidate_id, evaluation_id, policy)
        action = decision.action
        state = "promoted" if action == "promote" else "rejected"
        reasons = list(decision.reason_codes)
    except Exception as exc:
        reasons.append(str(exc) if isinstance(exc, ValueError) and str(exc).islower() and " " not in str(exc)
                       else "cycle_prerequisite_failed:" + type(exc).__name__)
        if candidate_id:
            try:
                value = registry.candidate(candidate_id)
                if value["status"] in {"queued", "training", "evaluated"}:
                    registry.transition(candidate_id, "rejected", rejection_reasons=reasons)
            except Exception:
                pass
    active = registry.active(task_id) if task else None
    payload = {"schema_version": 1, "cycle_id": cycle_id, "task_id": task_id, "state": state,
               "reason_codes": reasons, "candidate_id": candidate_id, "evaluation_id": evaluation_id,
               "promotion_action": action, "active_model_ref": active.get("model_ref") if active else None,
               "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
    _write_cycle(manifest_path, payload)
    return TrainingCycleSummary(cycle_id, task_id, state, tuple(reasons), candidate_id,
                                evaluation_id, action, payload["active_model_ref"], str(manifest_path))


def promote_if_eligible(candidate_id, evaluation_id, policy, *, registry):
    """Idempotent decision entry point; there is intentionally no confirmation override."""
    return registry.promote_if_eligible(candidate_id, evaluation_id, policy)


def evaluate_post_promotion_health(project, task_id, health_evaluation):
    """Record and apply configured automatic rollback gates."""
    return ModelRegistry(project.workspace_dir).rollback_if_unhealthy(task_id, health_evaluation)
