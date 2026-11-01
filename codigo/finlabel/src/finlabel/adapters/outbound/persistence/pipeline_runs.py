"""Verified privacy-safe local pipeline and label run artifacts."""
import hashlib
import json
import re
from pathlib import Path

_LABEL_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_PIPELINE_RUN_ID = re.compile(r"^[0-9a-f]{32}$")


def _canonical_digest(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _verified_label_run(workspace_dir: Path, run_id: str) -> dict:
    """Verify an autonomous run artifact and return aggregate metadata only."""
    from finlabel.domain.labeling.outcomes import LabelOutcome

    if not isinstance(run_id, str) or not _LABEL_RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a 32-character lowercase hexadecimal identifier.")
    run_dir = Path(workspace_dir) / "label-runs" / run_id
    metadata_path = run_dir / "run.json"
    outcomes_path = run_dir / "outcomes.jsonl"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        outcomes_bytes = outcomes_path.read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read autonomous label run artifact.") from exc
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise ValueError("Unsupported or malformed autonomous label run metadata.")
    if metadata.get("run_id") != run_id:
        raise ValueError("Autonomous label run metadata identity does not match its directory.")
    digest = hashlib.sha256(outcomes_bytes).hexdigest()
    if metadata.get("outcomes_sha256") != digest:
        raise ValueError("Autonomous label run integrity check failed for outcomes.jsonl.")

    outcomes = []
    try:
        for line in outcomes_bytes.decode("utf-8").splitlines():
            if not line.strip():
                raise ValueError("Autonomous label run contains an empty outcome line.")
            raw = json.loads(line)
            if not isinstance(raw, dict):
                raise ValueError("Autonomous label run contains a malformed outcome.")
            outcomes.append(LabelOutcome(**raw))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError("Autonomous label run contains invalid outcome data.") from exc

    if any(outcome.run_id != run_id for outcome in outcomes):
        raise ValueError("Autonomous label run contains an outcome with a different run ID.")
    if any(
        outcome.task_id != metadata.get("task_id")
        or outcome.policy_id != metadata.get("policy_id")
        or outcome.model_ref != metadata.get("model_ref")
        for outcome in outcomes
    ):
        raise ValueError("Autonomous label run outcome provenance does not match its metadata.")
    snapshot_material = "".join(
        "{}\0{}\n".format(outcome.record_ref, outcome.input_digest)
        for outcome in sorted(outcomes, key=lambda outcome: outcome.record_ref)
    )
    processed_batch_digest = hashlib.sha256(snapshot_material.encode("utf-8")).hexdigest()
    if metadata.get("processed_batch_sha256") != processed_batch_digest:
        raise ValueError("Autonomous label run integrity check failed for the processed batch digest.")
    applied_count = sum(outcome.state == "applied" for outcome in outcomes)
    quarantined_count = sum(outcome.state == "quarantined" for outcome in outcomes)
    reason_counts = {}
    for outcome in outcomes:
        if outcome.reason_code:
            reason_counts[outcome.reason_code] = reason_counts.get(outcome.reason_code, 0) + 1
    expected_reason_counts = dict(sorted(reason_counts.items()))
    if (
        metadata.get("outcome_count") != len(outcomes)
        or metadata.get("applied_count") != applied_count
        or metadata.get("quarantined_count") != quarantined_count
        or metadata.get("reason_counts") != expected_reason_counts
    ):
        raise ValueError("Autonomous label run aggregate metadata does not match its outcomes.")

    return {
        "run_id": run_id,
        "task_id": metadata["task_id"],
        "policy_id": metadata["policy_id"],
        "model_ref": metadata["model_ref"],
        "started_at": metadata["started_at"],
        "finished_at": metadata["finished_at"],
        "applied_count": applied_count,
        "quarantined_count": quarantined_count,
        "outcome_count": len(outcomes),
        "reason_counts": expected_reason_counts,
        "artifact_dir": str(run_dir),
        "outcomes_sha256": digest,
        "processed_batch_sha256": processed_batch_digest,
        "source_rechecked_before_publish": metadata["source_rechecked_before_publish"],
    }


def _verified_pipeline_run(workspace_dir: Path, run_id: str) -> dict:
    """Verify a combined run and return metadata only, never row-level content."""
    if not isinstance(run_id, str) or not _PIPELINE_RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a 32-character lowercase hexadecimal identifier.")
    run_dir = Path(workspace_dir) / "pipeline-runs" / run_id
    manifest_path = run_dir / "run.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read pipeline run artifact.") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported or malformed pipeline run metadata.")
    if manifest.get("run_id") != run_id:
        raise ValueError("Pipeline run metadata identity does not match its directory.")
    recorded_digest = manifest.get("integrity_sha256")
    unsigned = {key: value for key, value in manifest.items() if key != "integrity_sha256"}
    if not isinstance(recorded_digest, str) or _canonical_digest(unsigned) != recorded_digest:
        raise ValueError("Pipeline run integrity check failed for run.json.")

    label_run = _verified_label_run(workspace_dir, manifest.get("label_run_id"))
    if label_run["outcomes_sha256"] != manifest.get("label_outcomes_sha256"):
        raise ValueError("Pipeline run integrity check failed for linked label outcomes.")
    if label_run["task_id"] != manifest.get("task_id") or label_run["model_ref"] != manifest.get("label_model_ref"):
        raise ValueError("Pipeline run label provenance does not match its manifest.")

    training = manifest.get("training")
    if not isinstance(training, dict):
        raise ValueError("Pipeline run training summary is malformed.")
    cycle_id = training.get("cycle_id")
    cycle_path = None
    if cycle_id is not None:
        if not isinstance(cycle_id, str) or not _PIPELINE_RUN_ID.fullmatch(cycle_id):
            raise ValueError("Pipeline run contains an invalid training cycle identifier.")
        cycle_path = Path(workspace_dir) / "training" / "cycles" / (cycle_id + ".json")
        try:
            cycle_bytes = cycle_path.read_bytes()
            cycle = json.loads(cycle_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Could not read linked training cycle artifact.") from exc
        if hashlib.sha256(cycle_bytes).hexdigest() != training.get("cycle_sha256"):
            raise ValueError("Pipeline run integrity check failed for training cycle.")
        if not isinstance(cycle, dict) or cycle.get("cycle_id") != cycle_id:
            raise ValueError("Pipeline run training cycle identity does not match its manifest.")
        if cycle.get("task_id") != manifest.get("task_id") or cycle.get("state") != training.get("state"):
            raise ValueError("Pipeline run training provenance does not match its manifest.")
        for field in ("reason_codes", "candidate_id", "evaluation_id", "promotion_action", "active_model_ref"):
            if cycle.get(field) != training.get(field):
                raise ValueError("Pipeline run training summary does not match its cycle artifact.")

    return {
        "run_id": run_id,
        "task_id": manifest["task_id"],
        "source": manifest["source_name"],
        "started_at": manifest["started_at"],
        "finished_at": manifest["finished_at"],
        "label_run_id": label_run["run_id"],
        "label_model_ref": manifest["label_model_ref"],
        "labels": {
            "applied": label_run["applied_count"],
            "quarantined": label_run["quarantined_count"],
            "reason_counts": label_run["reason_counts"],
        },
        "training": {
            "state": training["state"],
            "reason_codes": training["reason_codes"],
            "candidate_id": training.get("candidate_id"),
            "evaluation_id": training.get("evaluation_id"),
            "promotion_action": training.get("promotion_action"),
            "active_model_ref": training.get("active_model_ref"),
        },
        "artifacts": {
            "pipeline_manifest": str(manifest_path),
            "label_run_dir": str(Path(workspace_dir) / "label-runs" / label_run["run_id"]),
            "label_outcomes": str(Path(workspace_dir) / "label-runs" / label_run["run_id"] / "outcomes.jsonl"),
            "training_cycle": str(cycle_path) if cycle_path is not None else None,
        },
        "integrity_sha256": recorded_digest,
    }


def _write_pipeline_run(workspace_dir: Path, run_id: str, payload: dict) -> Path:
    """Publish an immutable combined manifest as one atomic directory rename."""
    import os
    import tempfile

    root = Path(workspace_dir) / "pipeline-runs"
    root.mkdir(parents=True, exist_ok=True)
    final_dir = root / run_id
    if final_dir.exists():
        raise FileExistsError("Pipeline run already exists: {}".format(final_dir))
    temporary_dir = Path(tempfile.mkdtemp(prefix="." + run_id + "-", dir=str(root)))
    try:
        manifest = {**payload, "integrity_sha256": _canonical_digest(payload)}
        manifest_path = temporary_dir / "run.json"
        with manifest_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
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
    return final_dir / "run.json"



class FilePipelineRuns:
    def __init__(self, workspace):
        self.workspace = workspace

    def read_label(self, run_id):
        return _verified_label_run(self.workspace, run_id)

    def read_pipeline(self, run_id):
        return _verified_pipeline_run(self.workspace, run_id)

    def save_pipeline(self, run_id, payload):
        _write_pipeline_run(self.workspace, run_id, payload)
        return self.read_pipeline(run_id)

    def cycle_digest(self, cycle):
        return hashlib.sha256(Path(cycle.manifest_path).read_bytes()).hexdigest()
