"""Single in-process local worker for explicitly approved training jobs."""

import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional
from uuid import uuid4

from finlabel.training.backend import TrainingConfig, train_adapter, validate_training_request
from finlabel.training.registry import ModelRegistry


@dataclass(frozen=True)
class TrainingJobStatus:
    job_id: str
    state: str
    progress: str
    error: Optional[str]
    dataset_path: str
    output_dir: str
    model_id: str
    dataset_sha256: str
    created_at: str
    final_metrics: Mapping[str, float]
    bundle_dir: str = ""
    version_id: Optional[str] = None


@dataclass(frozen=True)
class EvaluationJobStatus:
    job_id: str
    state: str
    progress: str
    error: Optional[str]
    version_id: str
    created_at: str


class TrainingJobManager:
    def __init__(self, workspace_dir: Path, *, gate_path: Optional[Path] = None):
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.gate_path = Path(gate_path or self.workspace_dir / "training-gate.json").expanduser().resolve()
        self.jobs_dir = self.workspace_dir / "training" / "jobs"
        self._lock = threading.RLock()
        self._jobs = {}
        self._evaluation_jobs = {}
        self._worker = None
        self._evaluation_worker = None
        self._recover_completed_status_only()

    def _recover_completed_status_only(self):
        """Mark interrupted jobs as failed; never resume work after restart."""
        if not self.jobs_dir.is_dir():
            return
        for path in self.jobs_dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                status = TrainingJobStatus(**raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
                continue
            if status.state in {"queued", "running"}:
                status = TrainingJobStatus(
                    status.job_id, "failed", "The local process ended before this job completed.",
                    "No job was resumed after the process stopped.", status.dataset_path, status.output_dir,
                    status.model_id, status.dataset_sha256, status.created_at, {},
                    status.bundle_dir, status.version_id,
                )
                self._persist(status)
            if status.job_id == path.stem:
                self._jobs[status.job_id] = status
        for path in self.jobs_dir.glob("evaluation-*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                status = EvaluationJobStatus(**raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError):
                continue
            if status.state in {"queued", "running"}:
                status = EvaluationJobStatus(
                    status.job_id, "failed", "The local process ended before evaluation completed.",
                    "No evaluation was resumed after the process stopped.", status.version_id, status.created_at,
                )
                self._persist_evaluation(status)
            if status.job_id == path.stem.removeprefix("evaluation-"):
                self._evaluation_jobs[status.job_id] = status

    def submit(self, bundle, config: TrainingConfig, *, exploratory_confirmed: bool = False) -> str:
        validated = validate_training_request(bundle, config, gate_path=self.gate_path,
                                              exploratory_confirmed=exploratory_confirmed)
        with self._lock:
            if ((self._worker is not None and self._worker.is_alive())
                    or (self._evaluation_worker is not None and self._evaluation_worker.is_alive())):
                raise RuntimeError("Another local model operation is already active.")
            job_id = uuid4().hex
            status = TrainingJobStatus(
                job_id, "queued", "Waiting for the local training worker.", None,
                str(validated["manifest"]["dataset_path"]), str(config.output_dir), config.model_id,
                validated["dataset_sha256"], datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), {},
                str(bundle.manifest_path.parent), None,
            )
            self._persist(status)
            self._jobs[job_id] = status
            self._worker = threading.Thread(
                target=self._run, args=(job_id, bundle, config, exploratory_confirmed), daemon=True,
                name="finlabel-train-{}".format(job_id[:8]),
            )
            self._worker.start()
            return job_id

    def _persist(self, status: TrainingJobStatus) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        destination = self.jobs_dir / (status.job_id + ".json")
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(status), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, destination)

    def _set_status(self, status: TrainingJobStatus) -> None:
        with self._lock:
            self._jobs[status.job_id] = status
            self._persist(status)

    def _run(self, job_id: str, bundle, config: TrainingConfig, exploratory_confirmed: bool) -> None:
        status = self._jobs[job_id]
        self._set_status(TrainingJobStatus(
            status.job_id, "running", "Loading the approved local model and training the adapter.", None,
            status.dataset_path, status.output_dir, status.model_id, status.dataset_sha256,
            status.created_at, {}, status.bundle_dir, status.version_id,
        ))
        try:
            result = train_adapter(bundle, config, gate_path=self.gate_path,
                                   exploratory_confirmed=exploratory_confirmed)
            candidate = ModelRegistry(self.workspace_dir).register_candidate(
                result.output_dir, bundle.manifest_path)
            current = self._jobs[job_id]
            self._set_status(TrainingJobStatus(
                current.job_id, "succeeded", "Candidate adapter saved and registered locally; evaluation is pending.", None,
                current.dataset_path, str(result.output_dir), current.model_id, current.dataset_sha256,
                current.created_at, dict(result.final_metrics), current.bundle_dir, candidate.version_id,
            ))
        except Exception:
            current = self._jobs[job_id]
            self._set_status(TrainingJobStatus(
                current.job_id, "failed", "Training did not complete.",
                "Training failed. Inspect local process logs for details.", current.dataset_path,
                current.output_dir, current.model_id, current.dataset_sha256, current.created_at, {},
                current.bundle_dir, None,
            ))

    def get(self, job_id: str) -> TrainingJobStatus:
        if not isinstance(job_id, str) or len(job_id) != 32 or any(character not in "0123456789abcdef" for character in job_id):
            raise ValueError("Invalid training job ID.")
        with self._lock:
            status = self._jobs.get(job_id)
            if status is not None:
                return status
            path = self.jobs_dir / (job_id + ".json")
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                status = TrainingJobStatus(**raw)
            except FileNotFoundError as exc:
                raise KeyError("Training job was not found.") from exc
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
                raise ValueError("Training job status is invalid: {}".format(exc)) from exc
            if status.job_id != job_id:
                raise ValueError("Training job ID does not match its status file.")
            return status

    def recent(self, limit: int = 10):
        """Return a bounded list of local job statuses, newest first."""
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Job history limit must be between 1 and 100.")
        with self._lock:
            values = sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)
            return values[:limit]

    def submit_evaluation(self, version_id: str) -> str:
        """Queue one confirmed evaluation without blocking the local API event loop."""
        from finlabel.training.registry import ModelRegistry

        registry = ModelRegistry(self.workspace_dir)
        try:
            candidate = registry.version(version_id)
        except (OSError, ValueError, KeyError) as exc:
            raise KeyError("Model candidate was not found or is invalid.") from exc
        if candidate is None:
            raise KeyError("Model candidate was not found.")
        if candidate.state != "awaiting_evaluation":
            raise ValueError("Only a candidate awaiting evaluation can be evaluated.")
        # Pin the queue decision to the registry's immutable artifact hashes.
        # The worker repeats this after dequeue to catch changes made while queued.
        registry._validate_intact(candidate)
        with self._lock:
            if ((self._worker is not None and self._worker.is_alive())
                    or (self._evaluation_worker is not None and self._evaluation_worker.is_alive())):
                raise RuntimeError("Another local model operation is already active.")
            job_id = uuid4().hex
            status = EvaluationJobStatus(
                job_id, "queued", "Waiting for the local evaluation worker.", None,
                version_id, datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            self._persist_evaluation(status)
            self._evaluation_jobs[job_id] = status
            self._evaluation_worker = threading.Thread(
                target=self._run_evaluation, args=(job_id,), daemon=True,
                name="finlabel-evaluate-{}".format(job_id[:8]),
            )
            self._evaluation_worker.start()
            return job_id

    def _persist_evaluation(self, status: EvaluationJobStatus) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        destination = self.jobs_dir / ("evaluation-" + status.job_id + ".json")
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(status), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, destination)

    def _set_evaluation_status(self, status: EvaluationJobStatus) -> None:
        with self._lock:
            self._evaluation_jobs[status.job_id] = status
            self._persist_evaluation(status)

    def _run_evaluation(self, job_id: str) -> None:
        queued = self._evaluation_jobs[job_id]
        try:
            self._set_evaluation_status(EvaluationJobStatus(
                queued.job_id, "running", "Evaluating base and adapter on the reserved local holdout.", None,
                queued.version_id, queued.created_at,
            ))
            from finlabel.training.backend import load_training_bundle
            from finlabel.training.evaluation import evaluate_candidate
            from finlabel.training.registry import ModelRegistry
            from finlabel.labeling.task import load_task, task_file_path

            registry = ModelRegistry(self.workspace_dir)
            candidate = registry.version(queued.version_id)
            if candidate.state != "awaiting_evaluation":
                raise ValueError("Candidate is no longer awaiting evaluation.")
            bundle = load_training_bundle(candidate.bundle_manifest_path.parent)
            manifest = json.loads(candidate.bundle_manifest_path.read_text(encoding="utf-8"))
            task = load_task(task_file_path(self.workspace_dir, manifest["task_id"]))
            output = self.workspace_dir / "training" / "evaluations" / (candidate.version_id + "-" + secrets.token_hex(8) + ".json")
            # Recheck immediately before entering the evaluator: it is the first
            # point that may load adapter weights or consume holdout rows.
            candidate = registry.version(queued.version_id)
            if candidate.state != "awaiting_evaluation":
                raise ValueError("Candidate is no longer awaiting evaluation.")
            registry._validate_intact(candidate)
            evaluate_candidate(bundle, task, candidate.adapter_path, output_path=output)
            registry.record_evaluation(candidate.version_id, output)
            self._set_evaluation_status(EvaluationJobStatus(
                queued.job_id, "succeeded", "Holdout evaluation saved to the local model registry.", None,
                queued.version_id, queued.created_at,
            ))
        except Exception:
            self._set_evaluation_status(EvaluationJobStatus(
                queued.job_id, "failed", "Holdout evaluation did not complete.",
                "Evaluation failed. Inspect local process logs; the candidate was not marked evaluated.",
                queued.version_id, queued.created_at,
            ))

    def get_evaluation(self, job_id: str) -> EvaluationJobStatus:
        if not isinstance(job_id, str) or len(job_id) != 32 or any(character not in "0123456789abcdef" for character in job_id):
            raise ValueError("Invalid evaluation job ID.")
        with self._lock:
            status = self._evaluation_jobs.get(job_id)
            if status is not None:
                return status
            path = self.jobs_dir / ("evaluation-" + job_id + ".json")
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                status = EvaluationJobStatus(**raw)
            except FileNotFoundError as exc:
                raise KeyError("Evaluation job was not found.") from exc
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
                raise ValueError("Evaluation job status is invalid: {}".format(exc)) from exc
            if status.job_id != job_id:
                raise ValueError("Evaluation job ID does not match its status file.")
            return status

    def recent_evaluations(self, limit: int = 10):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("Evaluation history limit must be between 1 and 100.")
        with self._lock:
            values = sorted(self._evaluation_jobs.values(), key=lambda item: item.created_at, reverse=True)
            return values[:limit]
