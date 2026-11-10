"""Privacy-safe, immutable outcomes for autonomous labeling runs."""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

from lazylabel.domain.labeling.outcomes import LabelOutcome, _RUN_ID


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        processed_batch_sha256 = hashlib.sha256(snapshot_material.encode("utf-8")).hexdigest()
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
            "processed_batch_sha256": processed_batch_sha256,
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


class FileLabelRunStore:
    """Atomic label outcome publication implementing the application store port."""

    def __init__(self, workspace_dir):
        self.workspace_dir = Path(workspace_dir).expanduser()

    def save_run(self, **payload):
        return write_label_run(self.workspace_dir, **payload)
