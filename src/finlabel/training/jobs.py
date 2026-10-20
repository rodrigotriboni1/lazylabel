"""Single in-process local worker for explicitly approved training jobs."""

import json
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional
from uuid import uuid4

from finlabel.training.backend import TrainingConfig, train_adapter, validate_training_request


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


class TrainingJobManager:
    def __init__(self, workspace_dir: Path, *, gate_path: Optional[Path] = None):
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.gate_path = Path(gate_path or self.workspace_dir / "training-gate.json").expanduser().resolve()
        self.jobs_dir = self.workspace_dir / "training" / "jobs"
        self._lock = threading.RLock()
        self._jobs = {}
        self._worker = None
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
                )
                self._persist(status)
            if status.job_id == path.stem:
                self._jobs[status.job_id] = status

    def submit(self, dataset_path: Path, config: TrainingConfig) -> str:
        dataset_path = Path(dataset_path).expanduser().resolve()
        validated = validate_training_request(dataset_path, config, gate_path=self.gate_path)
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise RuntimeError("A local training job is already active.")
            job_id = uuid4().hex
            status = TrainingJobStatus(
                job_id, "queued", "Waiting for the local training worker.", None,
                str(dataset_path), str(config.output_dir), config.model_id,
                validated["dataset_sha256"], datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), {},
            )
            self._persist(status)
            self._jobs[job_id] = status
            self._worker = threading.Thread(
                target=self._run, args=(job_id, dataset_path, config), daemon=True,
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

    def _run(self, job_id: str, dataset_path: Path, config: TrainingConfig) -> None:
        status = self._jobs[job_id]
        self._set_status(TrainingJobStatus(
            status.job_id, "running", "Loading the approved local model and training the adapter.", None,
            status.dataset_path, status.output_dir, status.model_id, status.dataset_sha256,
            status.created_at, {},
        ))
        try:
            result = train_adapter(dataset_path, config, gate_path=self.gate_path)
            current = self._jobs[job_id]
            self._set_status(TrainingJobStatus(
                current.job_id, "succeeded", "Adapter saved locally.", None,
                current.dataset_path, str(result.output_dir), current.model_id, current.dataset_sha256,
                current.created_at, dict(result.final_metrics),
            ))
        except Exception:
            current = self._jobs[job_id]
            self._set_status(TrainingJobStatus(
                current.job_id, "failed", "Training did not complete.",
                "Training failed. Inspect local process logs for details.", current.dataset_path,
                current.output_dir, current.model_id, current.dataset_sha256, current.created_at, {},
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
