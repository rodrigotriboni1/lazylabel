"""Trusted-label training cycle with verified local evaluation and fail-closed promotion."""
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from finlabel.labeling.task import load_task, load_task_policy, task_file_path
from finlabel.project import load_project
from finlabel.training.backend import TrainingConfig, train_adapter, validate_training_request
from finlabel.training.dataset import TrustedDatasetManifest, prepare_trusted_dataset
from finlabel.training.evaluation import labeling_policy_sha256
from finlabel.training.local_evaluator import evaluate_candidate
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
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_cycle(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            unsigned = dict(payload)
            payload["integrity_sha256"] = hashlib.sha256(json.dumps(unsigned, sort_keys=True,
                ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
            handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _manifest_for(batch, task, workspace):
    artifact_root = Path(workspace).resolve()
    if artifact_root.name != ".finlabel":
        artifact_root = artifact_root / ".finlabel"
    destination = artifact_root / "trusted-datasets" / task.task_id / batch.snapshot_sha256
    manifest_path = destination / "manifest.json"
    if not manifest_path.exists():
        return prepare_trusted_dataset(batch, task, workspace_dir=workspace)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    digest = _sha(manifest_path)
    if (raw.get("schema_version") != 1 or raw.get("kind") != "trusted_reference_dataset"
            or raw.get("task_id") != task.task_id or raw.get("snapshot_sha256") != batch.snapshot_sha256
            or raw.get("provenance_id") != batch.provenance_id or raw.get("source_name") != batch.source_name
            or raw.get("task_spec_sha256") != task_spec_sha256(task)):
        raise ValueError("trusted_dataset_manifest_identity_mismatch")
    if set(raw.get("partitions", {})) != {"train", "calibration", "holdout"}:
        raise ValueError("trusted_dataset_partitions_missing")
    return TrustedDatasetManifest(destination, manifest_path, raw["task_id"], raw["source_name"],
        raw["provenance_id"], raw["snapshot_sha256"], raw["task_spec_sha256"],
        tuple(raw["feature_columns"]), raw["label_column"], raw["row_count"],
        raw["label_coverage"], raw["partitions"], digest)


def _prior_cycle(cycles_dir, task_id, snapshot, policy_sha256):
    for path in sorted(cycles_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (raw.get("task_id") == task_id and raw.get("snapshot_sha256") == snapshot
                and raw.get("policy_sha256") == policy_sha256 and raw.get("state") in {"complete", "rejected"}
                and _valid_cycle_digest(raw)):
            return path, raw
    return None, None


def _valid_cycle_digest(raw):
    unsigned = dict(raw)
    recorded = unsigned.pop("integrity_sha256", None)
    expected = hashlib.sha256(json.dumps(unsigned, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return recorded == expected


def _summary(path, payload):
    return TrainingCycleSummary(payload["cycle_id"], payload["task_id"], payload["state"],
        tuple(payload.get("reason_codes", ())), payload.get("candidate_id"), payload.get("evaluation_id"),
        payload.get("promotion_action"), payload.get("active_model_ref"), str(path))


def _reason(exc):
    message = str(exc)
    if message and message.isascii() and message.islower() and " " not in message and len(message) < 100:
        return message
    return "cycle_prerequisite_failed:" + type(exc).__name__


def run_training_cycle(project, task_id):
    """Train on trusted train rows, calibrate on calibration rows, and gate on frozen holdout."""
    project = load_project(project.config_path if hasattr(project, "config_path") else project)
    cycles_dir = project.workspace_dir / "training" / "cycles"
    cycles_dir.mkdir(parents=True, exist_ok=True)
    registry = ModelRegistry(project.workspace_dir)
    task = policy = manifest = batch = None
    candidate_id = evaluation_id = action = None
    cycle_id = uuid4().hex
    path = cycles_dir / (cycle_id + ".json")
    state, reasons = "blocked", []
    snapshot = policy_sha256 = None
    try:
        task = load_task(task_file_path(project.workspace_dir, task_id))
        policy = load_task_policy(task)
        if policy is None:
            raise ValueError("task_labeling_policy_missing")
        if policy.calibration_ref is None:
            raise ValueError("task_calibration_ref_missing")
        promotion_policy_path = registry.root / "promotion-policies" / (task_id + ".json")
        if not promotion_policy_path.is_file():
            raise ValueError("promotion_policy_missing")
        promotion_policy = PromotionPolicy.load(promotion_policy_path, task_id=task_id)
        batch = load_trusted_labels(project, task)
        snapshot = batch.snapshot_sha256
        policy_sha256 = promotion_policy.policy_sha256
        previous_path, previous = _prior_cycle(cycles_dir, task_id, snapshot, policy_sha256)
        if previous:
            return _summary(previous_path, previous)
        manifest = _manifest_for(batch, task, project.workspace_dir)
        if manifest.partitions["holdout"]["count"] < promotion_policy.min_holdout_count:
            raise ValueError("holdout_count_below_minimum")
        active = registry.active(task_id)
        base_ref = task.model_id + ("@" + task.model_revision if task.model_revision else "")
        incumbent_ref = active.get("model_ref") if active else base_ref
        incumbent_adapter = active.get("adapter_path") if active else None
        if active and not incumbent_adapter:
            raise ValueError("active_adapter_path_missing")
        if active and not incumbent_ref.startswith(base_ref + "+peft:"):
            raise ValueError("active_adapter_base_model_mismatch")

        candidate_id = uuid4().hex
        output = registry.root / "adapters" / candidate_id
        config = TrainingConfig(task.model_id, task.model_revision, output)
        train_path = manifest.path / manifest.partitions["train"]["path"]
        gate_path = project.workspace_dir / "training-gate.json"
        if not gate_path.is_file():
            raise ValueError("training_gate_missing")
        validate_training_request(train_path, config,
            gate_path=gate_path,
            trusted_dataset_manifest=manifest, expected_task_id=task.task_id)
        result = train_adapter(train_path, config, gate_path=gate_path,
            trusted_dataset_manifest=manifest, expected_task_id=task.task_id)
        candidate_ref = "{}+peft:{}".format(result.base_model_ref, result.artifact_sha256)
        registry.create_candidate(candidate_id, {
            "task_id": task_id, "model_ref": candidate_ref, "adapter_path": str(result.output_dir),
            "incumbent_model_ref": incumbent_ref, "expected_active_model_ref": incumbent_ref,
            "snapshot_sha256": snapshot, "policy_sha256": promotion_policy.policy_sha256,
            "trusted_manifest_path": str(manifest.manifest_path),
        })
        registry.transition(candidate_id, "training")
        evaluation_path = evaluate_candidate(task, policy, manifest, result.output_dir, incumbent_adapter,
            workspace_dir=project.workspace_dir, candidate_id=candidate_id)
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        if evaluation["candidate_model_ref"] != candidate_ref or evaluation["incumbent_model_ref"] != incumbent_ref:
            raise ValueError("evaluation_model_identity_mismatch")
        evaluation_id = evaluation["evaluation_id"]
        registry.transition(candidate_id, "evaluated", evaluation_id=evaluation_id)
        current_task = load_task(task_file_path(project.workspace_dir, task_id))
        current_policy = load_task_policy(current_task)
        current_promotion = PromotionPolicy.load(promotion_policy_path, task_id=task_id)
        if (task_spec_sha256(current_task) != task_spec_sha256(task) or current_policy is None
                or labeling_policy_sha256(current_policy) != labeling_policy_sha256(policy)
                or current_promotion.policy_sha256 != promotion_policy.policy_sha256):
            raise ValueError("task_or_promotion_policy_changed_during_cycle")
        decision = registry.promote_if_eligible(candidate_id, evaluation_id, current_promotion)
        action = decision.action
        state = "complete" if action == "promote" else "rejected"
        reasons = list(decision.reason_codes)
    except Exception as exc:
        reasons = [_reason(exc)]
        if candidate_id:
            try:
                current = registry.candidate(candidate_id)
                if current["status"] == "training":
                    registry.transition(candidate_id, "rejected", rejection_reasons=reasons)
            except Exception:
                pass
    active = registry.active(task_id)
    payload = {
        "schema_version": 1, "cycle_id": cycle_id, "task_id": task_id, "state": state,
        "reason_codes": reasons, "candidate_id": candidate_id, "evaluation_id": evaluation_id,
        "promotion_action": action, "active_model_ref": active.get("model_ref") if active else None,
        "snapshot_sha256": snapshot, "policy_sha256": policy_sha256,
        "dataset_manifest_sha256": _sha(manifest.manifest_path) if manifest else None,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    _write_cycle(path, payload)
    return _summary(path, payload)


def promote_if_eligible(candidate_id, evaluation_id, policy, *, registry):
    """Idempotent decision entry point; there is intentionally no confirmation override."""
    return registry.promote_if_eligible(candidate_id, evaluation_id, policy)


def evaluate_post_promotion_health(project, task_id, health_evaluation):
    """Record and apply configured automatic rollback gates."""
    return ModelRegistry(project.workspace_dir).rollback_if_unhealthy(task_id, health_evaluation)
