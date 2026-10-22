"""Resolve a task's promoted local adapter and matching calibrator."""
import json
from pathlib import Path

from finlabel.models.text_generation import TransformersTextGenerationBackend
from finlabel.training.backend import _artifact_tree_sha256
from finlabel.training.evaluation import CalibrationArtifact


def active_inference(project, task, policy, *, device="auto"):
    """Return base or promoted adapter backend plus its model-bound calibrator.

    A broken pointer or stale calibrator raises and causes the labeling caller to
    quarantine/block; it never falls back silently to the base model.
    """
    models_dir = Path(project.workspace_dir).expanduser().resolve() / "models"
    pointer_path = models_dir / "active-models.json"
    try:
        active = json.loads(pointer_path.read_text(encoding="utf-8")).get(task.task_id)
    except FileNotFoundError:
        active = None
    if not active:
        return TransformersTextGenerationBackend(task.model_id, task.model_revision, device), None
    if not policy or not policy.calibration_ref:
        raise ValueError("active_adapter_requires_task_policy_calibration")
    adapter = Path(active.get("adapter_path", "")).resolve()
    calibrator_path = Path(active.get("calibrator_path", "")).resolve()
    if not adapter.is_dir() or not calibrator_path.is_file():
        raise ValueError("active_adapter_artifact_missing")
    metadata = json.loads((adapter / "finlabel-training.json").read_text(encoding="utf-8"))
    base_ref = task.model_id + ("@" + task.model_revision if task.model_revision else "")
    adapter_digest = _artifact_tree_sha256(adapter)
    if (metadata.get("base_model_ref") != base_ref
            or metadata.get("adapter_artifacts_sha256") != adapter_digest
            or active.get("model_ref") != "{}+peft:{}".format(base_ref, adapter_digest)):
        raise ValueError("active_adapter_digest_or_base_model_mismatch")
    calibrator = CalibrationArtifact.load(calibrator_path)
    model_ref = active.get("model_ref")
    if calibrator.model_ref != model_ref or calibrator.task_id != task.task_id:
        raise ValueError("active_adapter_calibrator_identity_mismatch")
    backend = TransformersTextGenerationBackend(task.model_id, task.model_revision, device,
                                                 adapter_path=str(adapter), model_ref=model_ref)
    return backend, calibrator
