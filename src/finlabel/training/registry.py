"""Append-only local registry for evaluated model adapter candidates."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

from finlabel.training.backend import _json_object, _sha256

PathLike = Union[str, Path]
_VERSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_WEIGHTS = (".safetensors", ".bin")


@dataclass(frozen=True)
class ModelVersion:
    version_id: str
    base_model_ref: str
    adapter_path: Path
    adapter_sha256: str
    bundle_manifest_path: Path
    dataset_sha256: str
    split_sha256: str
    evaluation_path: Optional[Path]
    created_at: str
    state: str


def adapter_digest(directory: Path) -> str:
    directory = Path(directory).resolve()
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Candidate adapter must be a local directory.")
    weights = sorted(path for path in directory.rglob("*") if path.is_file() and path.name.endswith(_WEIGHTS))
    if not weights:
        raise ValueError("Candidate adapter has no local weight files.")
    digest = hashlib.sha256()
    for path in weights:
        if path.is_symlink():
            raise ValueError("Candidate adapter must not contain symbolic links.")
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


class ModelRegistry:
    def __init__(self, workspace_dir: PathLike):
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.versions_dir = self.workspace_dir / "models" / "versions"
        self.active_path = self.workspace_dir / "models" / "active.json"

    def _contained(self, value: PathLike, name: str) -> Path:
        path = Path(value).expanduser()
        if path.is_symlink():
            raise ValueError("{} must not be a symbolic link.".format(name))
        resolved = path.resolve()
        try:
            resolved.relative_to(self.workspace_dir)
        except ValueError as exc:
            raise ValueError("{} must be inside the project workspace.".format(name)) from exc
        return resolved

    def _version_dir(self, version_id: str) -> Path:
        if not isinstance(version_id, str) or not _VERSION_ID.fullmatch(version_id):
            raise ValueError("Invalid model version ID.")
        return self.versions_dir / version_id

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _manifest(self, version_id: str) -> dict:
        path = self._version_dir(version_id) / "manifest.json"
        value = _json_object(path, "model version manifest")
        if value.get("version_id") != version_id:
            raise ValueError("Model version manifest ID does not match its directory.")
        return value

    def _events(self, version_id: str) -> list:
        path = self._version_dir(version_id) / "events.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError("Could not read model version events: {}".format(exc)) from exc
        events = []
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError("Model version event log is malformed.") from exc
            if not isinstance(event, dict) or event.get("version_id") != version_id:
                raise ValueError("Model version event does not match its log.")
            events.append(event)
        if not events or events[0].get("type") != "registered":
            raise ValueError("Model version registration event is missing.")
        return events

    def _state(self, version_id: str) -> str:
        events = self._events(version_id)
        state = "awaiting_evaluation"
        for event in events[1:]:
            kind = event.get("type")
            if kind == "evaluated" and state == "awaiting_evaluation":
                state = "awaiting_approval"
            elif kind == "rejected" and state in {"awaiting_evaluation", "awaiting_approval"}:
                state = "rejected"
            elif kind == "activated":
                state = "active"
            elif kind == "superseded" and state == "active":
                state = "superseded"
            else:
                raise ValueError("Invalid model version state transition in event log.")
        return state

    def _append(self, version_id: str, event_type: str, **fields) -> None:
        path = self._version_dir(version_id) / "events.jsonl"
        record = {"type": event_type, "version_id": version_id, "at": self._now(), **fields}
        encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        descriptor = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _version(self, version_id: str) -> ModelVersion:
        manifest = self._manifest(version_id)
        adapter = self._contained(manifest.get("adapter_path", ""), "Adapter path")
        bundle = self._contained(manifest.get("bundle_manifest_path", ""), "Bundle manifest path")
        evaluated = [event for event in self._events(version_id) if event.get("type") == "evaluated"]
        evaluation = self._contained(evaluated[-1]["evaluation_path"], "Evaluation report path") if evaluated else None
        return ModelVersion(version_id, manifest["base_model_ref"], adapter, manifest["adapter_sha256"],
                            bundle, manifest["dataset_sha256"], manifest["split_sha256"], evaluation,
                            manifest["created_at"], self._state(version_id))

    def register_candidate(self, adapter_path: PathLike, bundle_manifest_path: PathLike,
                           version_id: Optional[str] = None) -> ModelVersion:
        adapter = self._contained(adapter_path, "Adapter path")
        bundle_path = self._contained(bundle_manifest_path, "Bundle manifest path")
        metadata_path = adapter / "finlabel-training.json"
        metadata = _json_object(metadata_path, "candidate training metadata")
        bundle = _json_object(bundle_path, "bundle manifest")
        digest = adapter_digest(adapter)
        for name, value in (("adapter_sha256", digest), ("dataset_sha256", bundle.get("dataset_sha256")),
                            ("split_sha256", bundle.get("split_sha256"))):
            if not isinstance(value, str) or _HASH.fullmatch(value) is None:
                raise ValueError("Candidate {} is missing or invalid.".format(name))
        if (metadata.get("adapter_sha256") != digest
                or metadata.get("dataset_sha256") != bundle["dataset_sha256"]
                or metadata.get("split_sha256") != bundle["split_sha256"]
                or not isinstance(metadata.get("base_model_ref"), str) or not metadata["base_model_ref"].strip()):
            raise ValueError("Candidate training metadata does not match the bundle or adapter files.")
        if bundle_path.name != "manifest.json" or not (bundle_path.parent / "train.jsonl").is_file() or not (bundle_path.parent / "holdout.jsonl").is_file():
            raise ValueError("Candidate bundle is incomplete.")
        bundle_data = _json_object(bundle_path, "bundle manifest")
        for part, field in (("train.jsonl", "train_sha256"), ("holdout.jsonl", "holdout_sha256")):
            if not isinstance(bundle_data.get(field), str) or _sha256(bundle_path.parent / part) != bundle_data[field]:
                raise ValueError("Candidate bundle partition hash mismatch.")
        version_id = version_id or uuid4().hex
        destination = self._version_dir(version_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Model version already exists: {}".format(version_id))
        created_at = self._now()
        manifest = {"version_id": version_id, "base_model_ref": metadata["base_model_ref"],
                    "adapter_path": str(adapter), "adapter_sha256": digest,
                    "bundle_manifest_path": str(bundle_path), "dataset_sha256": bundle["dataset_sha256"],
                    "split_sha256": bundle["split_sha256"], "evaluation_path": None,
                    "created_at": created_at}
        destination.mkdir()
        try:
            with (destination / "manifest.json").open("x", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._append(version_id, "registered")
        except BaseException:
            # Do not erase a partially written record; it is safer to preserve evidence than reuse an ID.
            raise
        return self._version(version_id)

    def record_evaluation(self, version_id: str, report_path: PathLike) -> ModelVersion:
        current = self._version(version_id)
        if current.state != "awaiting_evaluation":
            raise ValueError("Only unevaluated candidates accept an evaluation.")
        report_file = self._contained(report_path, "Evaluation report path")
        report = _json_object(report_file, "evaluation report")
        if (report.get("adapter_sha256") != current.adapter_sha256
                or report.get("dataset_sha256") != current.dataset_sha256
                or report.get("split_sha256") != current.split_sha256
                or Path(report.get("adapter_path", "")).expanduser().resolve() != current.adapter_path):
            raise ValueError("Evaluation report hashes or adapter path do not match this candidate.")
        self._append(version_id, "evaluated", evaluation_path=str(report_file),
                     adapter_sha256=current.adapter_sha256, dataset_sha256=current.dataset_sha256,
                     split_sha256=current.split_sha256)
        return self._version(version_id)

    def reject_candidate(self, version_id: str, reason: str) -> ModelVersion:
        current = self._version(version_id)
        if current.state not in {"awaiting_evaluation", "awaiting_approval"}:
            raise ValueError("Only inactive candidates can be rejected.")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("A non-empty rejection reason is required.")
        self._append(version_id, "rejected", reason=reason.strip())
        return self._version(version_id)

    def list_versions(self) -> list:
        if not self.versions_dir.is_dir():
            return []
        return [self._version(path.name) for path in sorted(self.versions_dir.iterdir()) if path.is_dir()]

    def active(self) -> Optional[ModelVersion]:
        if not self.active_path.exists():
            return None
        pointer = _json_object(self.active_path, "active model pointer")
        version_id = pointer.get("version_id")
        current = self._version(version_id)
        if current.state != "active":
            raise ValueError("Active pointer and version event history disagree.")
        self._validate_intact(current)
        return current

    def _validate_intact(self, version: ModelVersion) -> None:
        if adapter_digest(version.adapter_path) != version.adapter_sha256:
            raise ValueError("Candidate adapter is missing or its hash has changed.")
        bundle = _json_object(version.bundle_manifest_path, "bundle manifest")
        if bundle.get("dataset_sha256") != version.dataset_sha256 or bundle.get("split_sha256") != version.split_sha256:
            raise ValueError("Candidate bundle hashes no longer match the version.")
        for part, field in (("train.jsonl", "train_sha256"), ("holdout.jsonl", "holdout_sha256")):
            part_path = version.bundle_manifest_path.parent / part
            if not part_path.is_file() or _sha256(part_path) != bundle.get(field):
                raise ValueError("Candidate bundle is missing or corrupted.")
        metadata = _json_object(version.adapter_path / "finlabel-training.json", "candidate metadata")
        if (metadata.get("adapter_sha256") != version.adapter_sha256
                or metadata.get("dataset_sha256") != version.dataset_sha256
                or metadata.get("split_sha256") != version.split_sha256
                or metadata.get("base_model_ref") != version.base_model_ref):
            raise ValueError("Candidate metadata no longer matches its registry version.")
        if version.state in {"awaiting_approval", "active", "superseded"}:
            if version.evaluation_path is None:
                raise ValueError("Candidate evaluation report is missing.")
            report = _json_object(version.evaluation_path, "evaluation report")
            if (report.get("adapter_sha256") != version.adapter_sha256
                    or report.get("dataset_sha256") != version.dataset_sha256
                    or report.get("split_sha256") != version.split_sha256
                    or Path(report.get("adapter_path", "")).expanduser().resolve() != version.adapter_path):
                raise ValueError("Candidate evaluation report no longer matches the registered artifacts.")

    def _write_pointer(self, version_id: str) -> None:
        self.active_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version_id": version_id, "updated_at": self._now()}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.active_path.parent,
                                             prefix=".active-", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.active_path)
            temporary = None
            directory_fd = os.open(str(self.active_path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def activate(self, version_id: str) -> ModelVersion:
        candidate = self._version(version_id)
        if candidate.state != "awaiting_approval":
            raise ValueError("Only an evaluated, approved-for-review candidate can be activated.")
        self._validate_intact(candidate)
        previous = self.active()
        try:
            self._append(version_id, "activated")
            self._write_pointer(version_id)
            if previous is not None:
                self._append(previous.version_id, "superseded")
        except BaseException:
            # An activation event is neutralized with a later event if publishing fails.
            try:
                if self._state(version_id) == "active":
                    self._append(version_id, "superseded", reason="activation_failed")
            except Exception:
                pass
            if previous is None:
                self.active_path.unlink(missing_ok=True)
            else:
                self._write_pointer(previous.version_id)
            raise
        return self._version(version_id)

    def rollback(self, version_id: str) -> ModelVersion:
        target = self._version(version_id)
        if target.state != "superseded":
            raise ValueError("Rollback target must be a superseded version.")
        self._validate_intact(target)
        previous = self.active()
        try:
            self._append(version_id, "activated", reason="rollback")
            self._write_pointer(version_id)
            if previous is not None:
                self._append(previous.version_id, "superseded", reason="rollback")
        except BaseException:
            try:
                if self._state(version_id) == "active":
                    self._append(version_id, "superseded", reason="rollback_failed")
            except Exception:
                pass
            if previous is None:
                self.active_path.unlink(missing_ok=True)
            else:
                self._write_pointer(previous.version_id)
            raise
        return self._version(version_id)
