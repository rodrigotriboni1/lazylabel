"""Trusted-label training cycle with verified local evaluation and fail-closed promotion."""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from lazylabel.adapters.outbound.persistence.tasks import load_task, load_task_policy, task_file_path
from lazylabel.adapters.outbound.persistence.projects import load_project
from lazylabel.adapters.outbound.training.backend import TrainingConfig, train_adapter, validate_training_request
from lazylabel.adapters.outbound.persistence.datasets import (TrustedDatasetManifest, _build_trusted_dataset_artifacts,
                                      prepare_trusted_dataset)
from lazylabel.adapters.outbound.training.evaluation import labeling_policy_sha256
from lazylabel.domain.training.task_spec import task_spec_sha256
from lazylabel.adapters.outbound.training.local_evaluator import evaluate_candidate
from lazylabel.adapters.outbound.persistence.registry import ModelRegistry, PromotionPolicy
from lazylabel.adapters.outbound.sources.trusted_labels import load_trusted_labels


# Concrete filesystem/model effects for the application training lifecycle.
from lazylabel.application.ports.training import TrainingDataset, TrainedAdapter
from lazylabel.application.use_cases.training import (
    TrainingCycleSummary, _reason, _summary,
    run_training_cycle as _run_training_cycle,
    promote_if_eligible as _promote_if_eligible,
    evaluate_post_promotion_health as _evaluate_post_promotion_health,
)


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_training_gate_unchanged(gate_path, expected_digest):
    if _sha(gate_path) != expected_digest:
        raise ValueError("training_gate_changed_during_cycle")


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
    if artifact_root.name != ".lazylabel":
        artifact_root = artifact_root / ".lazylabel"
    destination = artifact_root / "trusted-datasets" / task.task_id / batch.snapshot_sha256
    manifest_path = destination / "manifest.json"
    expected = _build_trusted_dataset_artifacts(batch, task)
    if not manifest_path.exists():
        return prepare_trusted_dataset(batch, task, workspace_dir=workspace)
    manifest_bytes = manifest_path.read_bytes()
    if manifest_bytes != expected["manifest_bytes"]:
        raise ValueError("trusted_dataset_manifest_does_not_match_live_source")
    for name, expected_bytes in expected["partition_bytes"].items():
        partition_path = destination / (name + ".jsonl")
        if not partition_path.is_file() or partition_path.read_bytes() != expected_bytes:
            raise ValueError("trusted_dataset_partition_does_not_match_live_source:" + name)
    raw = expected["manifest"]
    digest = _sha(manifest_path)
    return TrustedDatasetManifest(destination, manifest_path, raw["task_id"], raw["source_name"],
        raw["provenance_id"], raw["snapshot_sha256"], raw["task_spec_sha256"],
        tuple(raw["feature_columns"]), raw["label_column"], raw["row_count"],
        raw["label_coverage"], raw["partitions"], digest)


def _prior_cycle(cycles_dir, identity, current_active_ref):
    for path in sorted(cycles_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (all(raw.get(key) == value for key, value in identity.items())
                and raw.get("state") in {"complete", "rejected"} and _valid_cycle_digest(raw)
                and (raw.get("resulting_active_model_ref") == current_active_ref
                     or raw.get("state") == "rejected"
                     and raw.get("incumbent_model_ref") == current_active_ref)):
            return path, raw
    return None, None


def _valid_cycle_digest(raw):
    unsigned = dict(raw)
    recorded = unsigned.pop("integrity_sha256", None)
    expected = hashlib.sha256(json.dumps(unsigned, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return recorded == expected


class LocalTrainingEffects:
    """Local implementations of training configuration, datasets, trainer,
    evaluator, registry, cycle persistence, and runtime ports; no lifecycle decisions.

    A per-cycle manifest map retains the exact verified frozen object supplied to
    both backend and evaluator. References crossing the application are strings.
    """
    def __init__(self, project):
        self.project = project
        self.cycles_dir = project.workspace_dir / "training" / "cycles"
        self.cycles_dir.mkdir(parents=True, exist_ok=True)
        self.registry = ModelRegistry(project.workspace_dir)
        self.manifests = {}

    def new_id(self):
        return uuid4().hex

    def now(self):
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def load_task(self, task_id):
        return load_task(task_file_path(self.project.workspace_dir, task_id))

    def load_labeling_policy(self, task):
        return load_task_policy(task)

    def load_promotion_policy(self, task_id):
        path = self.registry.root / "promotion-policies" / (task_id + ".json")
        if not path.is_file():
            raise ValueError("promotion_policy_missing")
        return PromotionPolicy.load(path, task_id=task_id)

    def reload_promotion_policy(self, task_id):
        # Initial absence has a configuration reason; mid-cycle deletion retains
        # the loader I/O failure recorded by the original lifecycle.
        path = self.registry.root / "promotion-policies" / (task_id + ".json")
        return PromotionPolicy.load(path, task_id=task_id)

    def task_reference(self, task_id):
        return str(task_file_path(self.project.workspace_dir, task_id))

    def gate_reference(self):
        return str((self.project.workspace_dir / "training-gate.json").resolve())

    def gate_digest(self):
        path = Path(self.gate_reference())
        if not path.is_file():
            raise ValueError("training_gate_missing")
        return _sha(path)

    def assert_gate_unchanged(self, expected_digest):
        _assert_training_gate_unchanged(self.gate_reference(), expected_digest)

    def load_trusted_batch(self, task):
        return load_trusted_labels(self.project, task)

    def prepare(self, batch, task):
        manifest = _manifest_for(batch, task, self.project.workspace_dir)
        reference = str(manifest.manifest_path)
        self.manifests[reference] = manifest
        return TrainingDataset(reference,
            str(manifest.path / manifest.partitions["train"]["path"]),
            manifest.snapshot_sha256, manifest.manifest_sha256, manifest.partitions["holdout"]["count"])

    def manifest_digest(self, dataset):
        return _sha(dataset.manifest_reference)

    def _training_args(self, task, dataset, output_reference, gate_reference):
        config = TrainingConfig(task.model_id, task.model_revision, Path(output_reference))
        return (Path(dataset.train_reference), config), {
            "gate_path": Path(gate_reference),
            "trusted_dataset_manifest": self.manifests[dataset.manifest_reference],
            "expected_task_id": task.task_id,
        }

    def validate(self, task, dataset, output_reference, gate_reference):
        args, kwargs = self._training_args(task, dataset, output_reference, gate_reference)
        validate_training_request(*args, **kwargs)

    def train(self, task, dataset, output_reference, gate_reference):
        args, kwargs = self._training_args(task, dataset, output_reference, gate_reference)
        result = train_adapter(*args, **kwargs)
        return TrainedAdapter(str(result.output_dir), result.base_model_ref, result.artifact_sha256)

    def evaluate(self, task, policy, dataset, adapter, incumbent_adapter, *, candidate_id,
                 gate_reference, gate_sha256):
        path = evaluate_candidate(task, policy, self.manifests[dataset.manifest_reference],
            Path(adapter.output_reference), incumbent_adapter,
            workspace_dir=self.project.workspace_dir, candidate_id=candidate_id,
            training_gate_path=Path(gate_reference), training_gate_sha256=gate_sha256)
        return json.loads(path.read_text(encoding="utf-8"))

    def active(self, task_id):
        return self.registry.active(task_id)

    def adapter_reference(self, candidate_id):
        return str(self.registry.root / "adapters" / candidate_id)

    def create_candidate(self, candidate_id, payload):
        return self.registry.create_candidate(candidate_id, payload)

    def candidate(self, candidate_id):
        return self.registry.candidate(candidate_id)

    def transition(self, candidate_id, status, **changes):
        return self.registry.transition(candidate_id, status, **changes)

    def promote_if_eligible(self, candidate_id, evaluation_id, policy):
        return self.registry.promote_if_eligible(candidate_id, evaluation_id, policy)

    def rollback_if_unhealthy(self, task_id, health_evaluation):
        return self.registry.rollback_if_unhealthy(task_id, health_evaluation)

    def find_prior(self, identity, current_active_ref):
        return _prior_cycle(self.cycles_dir, identity, current_active_ref)

    def save_cycle(self, cycle_id, payload):
        path = self.cycles_dir / (cycle_id + ".json")
        _write_cycle(path, payload)
        return str(path)


# Historical private extension point retained until composition migration.
_LocalTrainingPorts = LocalTrainingEffects


def run_training_cycle(project, task_id):
    """Compatibility entry point for the injected trusted-label training use case."""
    project = load_project(project.config_path if hasattr(project, "config_path") else project)
    ports = _LocalTrainingPorts(project)
    return _run_training_cycle(task_id, configuration=ports, datasets=ports, trainer=ports,
        evaluator=ports, registry=ports, cycles=ports, runtime=ports)


def promote_if_eligible(candidate_id, evaluation_id, policy, *, registry):
    """Idempotent decision entry point; there is intentionally no confirmation override."""
    return _promote_if_eligible(candidate_id, evaluation_id, policy, registry=registry)


def evaluate_post_promotion_health(project, task_id, health_evaluation):
    """Apply verified trusted health evidence through the shared registry gates."""
    return _evaluate_post_promotion_health(task_id, health_evaluation,
        registry=ModelRegistry(project.workspace_dir))
