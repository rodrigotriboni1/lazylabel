"""Privacy-safe, immutable outcomes for autonomous labeling runs."""

import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence


_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REASON_CODES = {
    "invalid_output", "unknown_label", "rule_conflict", "uncalibrated",
    "below_threshold", "stale_source", "backend_error", "missing_policy",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class LabelOutcome:
    run_id: str
    record_ref: str
    input_digest: str
    task_id: str
    policy_id: Optional[str]
    model_ref: str
    predicted_label: Optional[str]
    state: str
    reason_code: Optional[str]
    confidence: Optional[float]
    created_at: str

    def __post_init__(self):
        if not isinstance(self.run_id, str) or not _RUN_ID.fullmatch(self.run_id):
            raise ValueError("run_id must be a 32-character lowercase hex identifier.")
        if not isinstance(self.record_ref, str) or not _DIGEST.fullmatch(self.record_ref):
            raise ValueError("record_ref must be a SHA-256 digest.")
        if not isinstance(self.input_digest, str) or not _DIGEST.fullmatch(self.input_digest):
            raise ValueError("input_digest must be a SHA-256 digest.")
        for name in ("task_id", "model_ref"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError("{} must be a non-empty string.".format(name))
        if self.policy_id is not None and (
            not isinstance(self.policy_id, str) or not self.policy_id.strip()
        ):
            raise ValueError("policy_id must be a non-empty string or null.")
        if self.predicted_label is not None and (
            not isinstance(self.predicted_label, str) or not self.predicted_label.strip()
        ):
            raise ValueError("predicted_label must be a non-empty string or null.")
        if self.state not in {"applied", "quarantined"}:
            raise ValueError("state must be 'applied' or 'quarantined'.")
        if self.state == "applied" and self.reason_code is not None:
            raise ValueError("Applied outcomes cannot have a quarantine reason.")
        if self.state == "quarantined" and self.reason_code not in _REASON_CODES:
            raise ValueError("Quarantined outcomes require a known reason_code.")
        if self.confidence is not None and (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("confidence must be finite and between 0 and 1 or null.")
        if not isinstance(self.created_at, str) or not self.created_at.endswith("Z"):
            raise ValueError("created_at must be an ISO-8601 UTC timestamp ending in Z.")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class LabelRunSummary:
    run_id: str
    task_id: str
    policy_id: Optional[str]
    model_ref: str
    run_dir: Path
    outcomes_path: Path
    run_metadata_path: Path
    applied_count: int
    quarantined_count: int
    reason_counts: Mapping[str, int]

    @property
    def outcome_count(self) -> int:
        return self.applied_count + self.quarantined_count

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "policy_id": self.policy_id,
            "model_ref": self.model_ref,
            "run_dir": str(self.run_dir),
            "outcomes_path": str(self.outcomes_path),
            "run_metadata_path": str(self.run_metadata_path),
            "applied_count": self.applied_count,
            "quarantined_count": self.quarantined_count,
            "outcome_count": self.outcome_count,
            "reason_counts": dict(self.reason_counts),
        }


def write_label_run(
    workspace_dir,
    *,
    run_id: str,
    task_id: str,
    policy_id: Optional[str],
    model_ref: str,
    started_at: str,
    outcomes: Sequence[LabelOutcome],
    before_publish: Optional[Callable[[Sequence[LabelOutcome]], Sequence[LabelOutcome]]] = None,
) -> LabelRunSummary:
    """Persist a complete run by atomically renaming a fully synced directory.

    Outcomes intentionally contain no selected row values, model prompts, or
    free-form rationales. The directory rename keeps outcomes and metadata as
    one visible artifact set, rather than exposing a partial run.
    """
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a 32-character lowercase hex identifier.")
    outcomes = tuple(outcomes)
    if any(item.run_id != run_id for item in outcomes):
        raise ValueError("Every outcome must belong to the run being written.")
    record_refs = [item.record_ref for item in outcomes]
    if len(record_refs) != len(set(record_refs)):
        raise ValueError("A run cannot contain duplicate record outcomes.")

    root = Path(workspace_dir).expanduser() / "label-runs"
    root.mkdir(parents=True, exist_ok=True)
    final_dir = root / run_id
    if final_dir.exists():
        raise FileExistsError("Label run already exists: {}".format(final_dir))
    temporary_dir = Path(tempfile.mkdtemp(prefix=".{}-".format(run_id), dir=str(root)))
    try:
        outcomes_path = temporary_dir / "outcomes.jsonl"
        with outcomes_path.open("w", encoding="utf-8", newline="\n") as handle:
            for outcome in outcomes:
                handle.write(json.dumps(outcome.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

        # The caller can re-read its read-only source after staging the rows,
        # immediately before metadata and the atomic directory publication.
        if before_publish is not None:
            checked_outcomes = tuple(before_publish(outcomes))
            if (
                len(checked_outcomes) != len(outcomes)
                or any(not isinstance(item, LabelOutcome) or item.run_id != run_id
                       for item in checked_outcomes)
                or [item.record_ref for item in checked_outcomes] != record_refs
            ):
                raise ValueError("Pre-publication freshness check changed the run's outcome identities.")
            if checked_outcomes != outcomes:
                with outcomes_path.open("w", encoding="utf-8", newline="\n") as handle:
                    for outcome in checked_outcomes:
                        handle.write(json.dumps(outcome.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                outcomes = checked_outcomes

        applied_count = sum(item.state == "applied" for item in outcomes)
        quarantined_count = len(outcomes) - applied_count
        reason_counts = {}
        for item in outcomes:
            if item.reason_code:
                reason_counts[item.reason_code] = reason_counts.get(item.reason_code, 0) + 1

        outcomes_sha256 = hashlib.sha256(outcomes_path.read_bytes()).hexdigest()
        snapshot_material = "".join(
            "{}\0{}\n".format(item.record_ref, item.input_digest)
            for item in sorted(outcomes, key=lambda item: item.record_ref)
        )
        source_snapshot_sha256 = hashlib.sha256(snapshot_material.encode("utf-8")).hexdigest()
        metadata = {
            "schema_version": 1,
            "run_id": run_id,
            "task_id": task_id,
            "policy_id": policy_id,
            "model_ref": model_ref,
            "started_at": started_at,
            "finished_at": utc_now(),
            "outcome_count": len(outcomes),
            "applied_count": applied_count,
            "quarantined_count": quarantined_count,
            "reason_counts": dict(sorted(reason_counts.items())),
            "outcomes_sha256": outcomes_sha256,
            "source_snapshot_sha256": source_snapshot_sha256,
            "source_rechecked_before_publish": before_publish is not None,
            "source_lock_acquired": False,
        }
        metadata_path = temporary_dir / "run.json"
        with metadata_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

        # Sync directory entries before publishing the completed artifact set.
        directory_fd = os.open(str(temporary_dir), os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        os.replace(str(temporary_dir), str(final_dir))
        root_fd = os.open(str(root), os.O_RDONLY)
        try:
            os.fsync(root_fd)
        finally:
            os.close(root_fd)
    except BaseException:
        import shutil

        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise

    return LabelRunSummary(
        run_id=run_id,
        task_id=task_id,
        policy_id=policy_id,
        model_ref=model_ref,
        run_dir=final_dir,
        outcomes_path=final_dir / "outcomes.jsonl",
        run_metadata_path=final_dir / "run.json",
        applied_count=applied_count,
        quarantined_count=quarantined_count,
        reason_counts=dict(sorted(reason_counts.items())),
    )
