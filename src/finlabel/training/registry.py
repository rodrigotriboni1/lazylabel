"""Append-only local registry for evaluated model adapter candidates."""

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

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
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Candidate adapter must be a local directory.")
    entries = list(directory.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("Candidate adapter must not contain symbolic links.")
    weights = sorted(path for path in entries if path.is_file() and path.name.endswith(_WEIGHTS))
    if not weights:
        raise ValueError("Candidate adapter has no local weight files.")
    digest = hashlib.sha256()
    for path in weights:
        digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(_sha256_nofollow(path)))
    return digest.hexdigest()


def _read_bytes_nofollow(path: Path) -> bytes:
    descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        return handle.read()


def _sha256_nofollow(path: Path) -> str:
    return hashlib.sha256(_read_bytes_nofollow(path)).hexdigest()


class ModelRegistry:
    def __init__(self, workspace_dir: PathLike):
        raw_workspace = Path(workspace_dir).expanduser()
        self._reject_symlink_components(raw_workspace, "Registry workspace")
        self.workspace_dir = raw_workspace.resolve()
        self.versions_dir = self.workspace_dir / "models" / "versions"
        self.active_path = self.workspace_dir / "models" / "active.json"

    def _contained(self, value: PathLike, name: str) -> Path:
        path = Path(value).expanduser()
        self._reject_symlink_components(path, name)
        resolved = path.resolve()
        try:
            resolved.relative_to(self.workspace_dir)
        except ValueError as exc:
            raise ValueError("{} must be inside the project workspace.".format(name)) from exc
        return resolved

    @staticmethod
    def _reject_symlink_components(path: Path, name: str) -> None:
        path = path if path.is_absolute() else Path.cwd() / path
        if ".." in path.parts:
            raise ValueError("{} must not use parent-directory path components.".format(name))
        current = Path(path.anchor)
        for component in path.parts[1:]:
            current = current / component
            if current.is_symlink():
                raise ValueError("{} path contains a symbolic link.".format(name))

    def _version_dir(self, version_id: str) -> Path:
        if not isinstance(version_id, str) or not _VERSION_ID.fullmatch(version_id):
            raise ValueError("Invalid model version ID.")
        return self._contained(self.versions_dir / version_id, "Model registry path")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _manifest(self, version_id: str) -> dict:
        path = self._contained(self._version_dir(version_id) / "manifest.json", "Version manifest path")
        value, _ = self._read_json(path, "model version manifest")
        if value.get("version_id") != version_id:
            raise ValueError("Model version manifest ID does not match its directory.")
        return value

    def _events(self, version_id: str) -> list:
        path = self._contained(self._version_dir(version_id) / "events.jsonl", "Version event path")
        try:
            lines = _read_bytes_nofollow(path).decode("utf-8").splitlines()
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
                if not isinstance(event.get("evaluation_sha256"), str) or _HASH.fullmatch(event["evaluation_sha256"]) is None:
                    raise ValueError("Evaluation event hash is missing or invalid.")
                state = "awaiting_approval"
            elif kind == "rejected" and state in {"awaiting_evaluation", "awaiting_approval"}:
                state = "rejected"
            elif kind == "activated" and event.get("reason") == "rollback" and state == "superseded":
                state = "active"
            elif kind == "activated" and event.get("reason") != "rollback" and state == "awaiting_approval":
                state = "active"
            elif kind == "superseded" and state == "active":
                state = "superseded"
            elif kind == "activation_failed" and state == "active" and event.get("reason") == "rollback_failed":
                state = "superseded"
            elif kind == "activation_failed" and state == "active":
                state = "awaiting_approval"
            else:
                raise ValueError("Invalid model version state transition in event log.")
        return state

    def _append(self, version_id: str, event_type: str, **fields) -> None:
        path = self._contained(self._version_dir(version_id) / "events.jsonl", "Version event path")
        record = {"type": event_type, "version_id": version_id, "at": self._now(), **fields}
        encoded = (json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        descriptor = os.open(str(path), os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written == 0:
                    raise OSError("Could not append complete model registry event.")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _read_json(path: Path, description: str) -> tuple[dict, bytes]:
        try:
            data = _read_bytes_nofollow(path)
            value = json.loads(data.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Could not read {}: {}".format(description, exc)) from exc
        if not isinstance(value, dict):
            raise ValueError("{} must be a JSON object.".format(description))
        return value, data

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
        self._contained(metadata_path, "Candidate metadata path")
        metadata, _ = self._read_json(metadata_path, "candidate training metadata")
        bundle, _ = self._read_json(bundle_path, "bundle manifest")
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
        train_path = self._contained(bundle_path.parent / "train.jsonl", "Bundle train path")
        holdout_path = self._contained(bundle_path.parent / "holdout.jsonl", "Bundle holdout path")
        if bundle_path.name != "manifest.json" or not train_path.is_file() or not holdout_path.is_file():
            raise ValueError("Candidate bundle is incomplete.")
        bundle_data, _ = self._read_json(bundle_path, "bundle manifest")
        for part, field in (("train.jsonl", "train_sha256"), ("holdout.jsonl", "holdout_sha256")):
            part_path = train_path if part == "train.jsonl" else holdout_path
            if not isinstance(bundle_data.get(field), str) or _sha256_nofollow(part_path) != bundle_data[field]:
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
        report, report_bytes = self._read_json(report_file, "evaluation report")
        if (report.get("adapter_sha256") != current.adapter_sha256
                or report.get("dataset_sha256") != current.dataset_sha256
                or report.get("split_sha256") != current.split_sha256
                or Path(report.get("adapter_path", "")).expanduser().resolve() != current.adapter_path):
            raise ValueError("Evaluation report hashes or adapter path do not match this candidate.")
        evaluation_sha256 = hashlib.sha256(report_bytes).hexdigest()
        snapshot = self._contained(self._version_dir(version_id) / ("evaluation-" + evaluation_sha256 + ".json"),
                                   "Registry evaluation snapshot path")
        if snapshot.exists():
            if _read_bytes_nofollow(snapshot) != report_bytes:
                raise ValueError("Existing evaluation snapshot does not match its content hash.")
        else:
            descriptor = os.open(str(snapshot), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o400)
            try:
                view = memoryview(report_bytes)
                while view:
                    written = os.write(descriptor, view)
                    if written == 0:
                        raise OSError("Could not write complete evaluation snapshot.")
                    view = view[written:]
                os.fsync(descriptor)
                os.fchmod(descriptor, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            finally:
                os.close(descriptor)
        self._append(version_id, "evaluated", evaluation_path=str(snapshot),
                     adapter_sha256=current.adapter_sha256, dataset_sha256=current.dataset_sha256,
                     split_sha256=current.split_sha256, evaluation_sha256=evaluation_sha256)
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
        versions_dir = self._contained(self.versions_dir, "Model versions directory")
        if not versions_dir.is_dir():
            return []
        return [self._version(path.name) for path in sorted(versions_dir.iterdir()) if path.is_dir()]

    def version(self, version_id: str) -> ModelVersion:
        """Read one version record without asserting that its adapter is intact."""
        return self._version(version_id)

    def inspect_history(self) -> dict:
        """Return readable version history plus integrity diagnostics without trusting a bad active pointer."""
        active_id = None
        active = None
        active_error = None
        try:
            active = self.active()
            active_id = active.version_id if active else None
        except (OSError, ValueError, KeyError) as exc:
            active_error = str(exc)
            try:
                pointer_path = self._contained(self.active_path, "Active pointer path")
                pointer, _ = self._read_json(pointer_path, "active model pointer")
                candidate_id = pointer.get("version_id")
                if isinstance(candidate_id, str) and _VERSION_ID.fullmatch(candidate_id):
                    active_id = candidate_id
            except (OSError, ValueError):
                pass

        records = []
        diagnostics = []
        versions_dir = self._contained(self.versions_dir, "Model versions directory")
        if versions_dir.is_dir():
            for path in sorted(versions_dir.iterdir()):
                if path.is_symlink() or not path.is_dir():
                    diagnostics.append({"version_id": path.name, "error": "Version entry is not a regular directory."})
                    continue
                try:
                    item = self._version(path.name)
                except (OSError, ValueError, KeyError) as exc:
                    diagnostics.append({"version_id": path.name, "error": str(exc)})
                    records.append({"version": None, "version_id": path.name, "state": "invalid",
                                    "integrity_valid": False, "integrity_error": str(exc)})
                    continue
                try:
                    self._validate_intact(item)
                    integrity_error = None
                except (OSError, ValueError, KeyError) as exc:
                    integrity_error = str(exc)
                    diagnostics.append({"version_id": item.version_id, "error": integrity_error})
                records.append({"version": item, "version_id": item.version_id, "state": item.state,
                                "integrity_valid": integrity_error is None, "integrity_error": integrity_error})

        if active is None and active_error is None and any(item["state"] == "active" for item in records):
            active_error = "An active version exists in history, but the active pointer is missing."
            for item in records:
                if item["state"] == "active":
                    item["integrity_valid"] = False
                    item["integrity_error"] = active_error
        if active_id is not None:
            active_record = next((item for item in records if item["version_id"] == active_id), None)
            if active_record is None and active_error is None:
                active_error = "The active pointer references a version missing from registry history."
            elif active_record is not None and not active_record["integrity_valid"] and active_error is None:
                active_error = active_record["integrity_error"] or "The active version failed integrity validation."
        return {"active": active, "active_pointer_id": active_id, "active_error": active_error,
                "versions": records, "diagnostics": diagnostics}

    def recover_active(self, version_id: str) -> ModelVersion:
        """Point to a verified superseded version only when the current active state is unusable."""
        try:
            current = self.active()
        except (OSError, ValueError, KeyError):
            current = None
        if current is not None:
            raise ValueError("The active version is healthy; use normal rollback instead.")
        inspection = self.inspect_history()
        if not inspection["active_error"]:
            raise ValueError("No invalid active pointer or artifact requires recovery.")
        target = self._version(version_id)
        if target.state != "superseded":
            raise ValueError("Recovery target must be a superseded version.")
        self._validate_intact(target)
        previous = None
        if inspection["active_pointer_id"]:
            try:
                previous = self._version(inspection["active_pointer_id"])
            except (OSError, ValueError, KeyError):
                previous = None
        self._append(version_id, "activated", reason="rollback")
        try:
            self._write_pointer(version_id)
        except BaseException:
            try:
                self._append(version_id, "activation_failed", reason="rollback_failed")
            except Exception:
                pass
            raise
        if previous is not None and previous.state == "active":
            try:
                self._append(previous.version_id, "superseded", reason="recovery")
            except (OSError, ValueError, KeyError):
                # The selected target and pointer are valid; inspection will continue to report
                # the damaged prior history entry rather than treating it as active.
                pass
        return self._version(version_id)

    def active(self) -> Optional[ModelVersion]:
        active_path = self._contained(self.active_path, "Active pointer path")
        if not active_path.exists():
            return None
        pointer, _ = self._read_json(active_path, "active model pointer")
        version_id = pointer.get("version_id")
        current = self._version(version_id)
        if current.state != "active":
            raise ValueError("Active pointer and version event history disagree.")
        self._validate_intact(current)
        return current

    def _validate_intact(self, version: ModelVersion) -> None:
        if adapter_digest(version.adapter_path) != version.adapter_sha256:
            raise ValueError("Candidate adapter is missing or its hash has changed.")
        bundle, _ = self._read_json(version.bundle_manifest_path, "bundle manifest")
        stable = {key: value for key, value in bundle.items()
                  if key not in {"dataset_path", "dataset_manifest_path", "split_sha256"}}
        split_digest = hashlib.sha256(json.dumps(
            stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        if (bundle.get("dataset_sha256") != version.dataset_sha256
                or bundle.get("split_sha256") != version.split_sha256
                or split_digest != version.split_sha256):
            raise ValueError("Candidate bundle hashes no longer match the version.")
        for part, field in (("train.jsonl", "train_sha256"), ("holdout.jsonl", "holdout_sha256")):
            part_path = self._contained(version.bundle_manifest_path.parent / part, "Bundle partition path")
            if not part_path.is_file() or _sha256_nofollow(part_path) != bundle.get(field):
                raise ValueError("Candidate bundle is missing or corrupted.")
        metadata_path = self._contained(version.adapter_path / "finlabel-training.json", "Candidate metadata path")
        metadata, _ = self._read_json(metadata_path, "candidate metadata")
        if (metadata.get("adapter_sha256") != version.adapter_sha256
                or metadata.get("dataset_sha256") != version.dataset_sha256
                or metadata.get("split_sha256") != version.split_sha256
                or metadata.get("base_model_ref") != version.base_model_ref):
            raise ValueError("Candidate metadata no longer matches its registry version.")
        if version.state in {"awaiting_approval", "active", "superseded"}:
            if version.evaluation_path is None:
                raise ValueError("Candidate evaluation report is missing.")
            report, _ = self._read_json(version.evaluation_path, "evaluation report")
            evaluated = [event for event in self._events(version.version_id) if event.get("type") == "evaluated"]
            if not evaluated or _sha256_nofollow(version.evaluation_path) != evaluated[-1].get("evaluation_sha256"):
                raise ValueError("Candidate evaluation report has changed since it was recorded.")
            if (report.get("adapter_sha256") != version.adapter_sha256
                    or report.get("dataset_sha256") != version.dataset_sha256
                    or report.get("split_sha256") != version.split_sha256
                    or Path(report.get("adapter_path", "")).expanduser().resolve() != version.adapter_path):
                raise ValueError("Candidate evaluation report no longer matches the registered artifacts.")

    def _write_pointer(self, version_id: str) -> None:
        active_path = self._contained(self.active_path, "Active pointer path")
        active_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version_id": version_id, "updated_at": self._now()}
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=active_path.parent,
                                             prefix=".active-", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, active_path)
            temporary = None
            directory_fd = os.open(str(active_path.parent), os.O_RDONLY)
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
            # Neutralize a published event while preserving an evaluated retryable candidate.
            try:
                if self._state(version_id) == "active":
                    self._append(version_id, "activation_failed")
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
                    self._append(version_id, "activation_failed", reason="rollback_failed")
            except Exception:
                pass
            if previous is None:
                self.active_path.unlink(missing_ok=True)
            else:
                self._write_pointer(previous.version_id)
            raise
        return self._version(version_id)
