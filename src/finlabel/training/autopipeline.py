"""Trusted-label training cycle with fail-closed automatic promotion."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from finlabel.labeling.task import load_task, task_file_path
from finlabel.project import load_project
from finlabel.training.registry import ModelRegistry, PromotionPolicy


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


def _write_cycle(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass


def run_training_cycle(project, task_id):
    """Record a fail-closed skip until trusted calibration and holdout evaluation exists."""
    project = load_project(project.config_path if hasattr(project, "config_path") else project)
    cycle_id = uuid4().hex
    cycles_dir = project.workspace_dir / "training" / "cycles"
    cycles_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cycles_dir / (cycle_id + ".json")
    state, reasons, candidate_id, evaluation_id, action = "blocked", [], None, None, None
    registry = ModelRegistry(project.workspace_dir)
    try:
        task_path = task_file_path(project.workspace_dir, task_id)
        load_task(task_path)
        policy_path = registry.root / "promotion-policies" / (task_id + ".json")
        PromotionPolicy.load(policy_path, task_id=task_id)
        raise ValueError("verifiable_calibration_and_holdout_evaluator_unavailable")
    except Exception as exc:
        reasons.append(str(exc) if isinstance(exc, ValueError) and str(exc).islower() and " " not in str(exc)
                       else "cycle_prerequisite_failed:" + type(exc).__name__)
    active = registry.active(task_id)
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
