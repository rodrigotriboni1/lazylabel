"""Command-line interface for local dataset inspection."""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Optional, Sequence

from finlabel.profile import inspect_csv
from finlabel.project import init_project, load_project, open_source, save_project
from finlabel.sources.base import ProjectConfig, SourceSpec
from finlabel.monitor import capture_schema, load_schema_baseline, monitor_source, save_schema_baseline
from finlabel.analysis.schema import plan_from_dict
from finlabel.analysis.service import analyze_source


_LABEL_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_PIPELINE_RUN_ID = re.compile(r"^[0-9a-f]{32}$")


def _canonical_digest(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _verified_label_run(workspace_dir: Path, run_id: str) -> dict:
    """Verify an autonomous run artifact and return aggregate metadata only."""
    from finlabel.labeling.outcomes import LabelOutcome

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


def run_autonomous_pipeline(project_path, source_name: str, task_id: str, *, device: str = "auto") -> dict:
    """Run the same autonomous label-and-train cycle used by the CLI and web panel."""
    from datetime import datetime, timezone
    from uuid import uuid4
    from finlabel.labeling.service import run_labeling
    from finlabel.labeling.task import load_task, load_task_policy, task_file_path
    from finlabel.training.autopipeline import run_training_cycle

    config = load_project(project_path)
    source = open_source(config, source_name)
    task = load_task(
        task_file_path(config.workspace_dir, task_id),
        available_columns=tuple(column.name for column in source.columns()),
    )
    policy = load_task_policy(task)
    backend = None
    calibrator = None
    if policy is not None:
        from finlabel.training.active_model import active_inference
        backend, calibrator = active_inference(config, task, policy, device=device)
    run_started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    label_run = run_labeling(
        source, task, policy, backend, workspace_dir=config.workspace_dir, calibrator=calibrator
    )
    label_metadata = _verified_label_run(config.workspace_dir, label_run.run_id)
    try:
        cycle = run_training_cycle(config.path, task.task_id)
        training = {
            "cycle_id": cycle.cycle_id,
            "cycle_sha256": hashlib.sha256(Path(cycle.manifest_path).read_bytes()).hexdigest(),
            "state": cycle.state,
            "reason_codes": list(cycle.reason_codes),
            "candidate_id": cycle.candidate_id,
            "evaluation_id": cycle.evaluation_id,
            "promotion_action": cycle.promotion_action,
            "active_model_ref": cycle.active_model_ref,
        }
    except Exception as exc:
        training = {
            "cycle_id": None,
            "cycle_sha256": None,
            "state": "blocked",
            "reason_codes": ["training_cycle_failed:" + type(exc).__name__],
            "candidate_id": None,
            "evaluation_id": None,
            "promotion_action": None,
            "active_model_ref": None,
        }
    run_id = uuid4().hex
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "task_id": task.task_id,
        "source_name": source_name,
        "started_at": run_started,
        "finished_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "label_run_id": label_run.run_id,
        "label_model_ref": label_metadata["model_ref"],
        "label_outcomes_sha256": label_metadata["outcomes_sha256"],
        "training": training,
    }
    _write_pipeline_run(config.workspace_dir, run_id, payload)
    result = _verified_pipeline_run(config.workspace_dir, run_id)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="finlabel")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="inspect a local CSV without printing rows")
    inspect.add_argument("csv_path", help="path to a UTF-8 CSV file")
    inspect.add_argument("--target", help="optional target column for class counts")
    project = commands.add_parser("project", help="manage a local FinLabel project")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    project_init = project_commands.add_parser("init", help="initialize a local project workspace")
    project_init.add_argument("path", help="project directory")
    source = commands.add_parser("source", help="configure read-only local data sources")
    source_commands = source.add_subparsers(dest="source_command", required=True)
    add_csv = source_commands.add_parser("add-csv", help="add a CSV source to a project")
    add_csv.add_argument("name")
    add_csv.add_argument("path")
    add_csv.add_argument("--project", default=".")
    add_sqlite = source_commands.add_parser("add-sqlite", help="add a read-only SQLite table")
    add_sqlite.add_argument("name")
    add_sqlite.add_argument("path")
    add_sqlite.add_argument("--table", required=True)
    add_sqlite.add_argument("--id-column")
    add_sqlite.add_argument("--project", default=".")
    set_type = source_commands.add_parser("set-type", help="explicitly map a source column type")
    set_type.add_argument("name")
    set_type.add_argument("column")
    set_type.add_argument("type", choices=("string", "integer", "decimal", "date", "datetime", "boolean"))
    set_type.add_argument("--project", default=".")
    schema = commands.add_parser("schema", help="capture an editable source schema")
    schema_commands = schema.add_subparsers(dest="schema_command", required=True)
    capture = schema_commands.add_parser("capture", help="write a candidate schema file")
    capture.add_argument("source")
    capture.add_argument("--output", required=True)
    capture.add_argument("--project", default=".")
    monitor = commands.add_parser("monitor", help="compare a source with a confirmed schema")
    monitor.add_argument("source")
    monitor.add_argument("--baseline", required=True)
    monitor.add_argument("--project", default=".")
    analyze = commands.add_parser("analyze", help="run a validated local analysis and save a chart")
    analyze.add_argument("source")
    analyze.add_argument("--question", required=True)
    analyze.add_argument("--model-id")
    analyze.add_argument("--revision")
    analyze.add_argument("--device", default="auto")
    analyze.add_argument("--plan", help="explicit JSON analysis plan; skips model planning")
    analyze.add_argument("--output", help="new output directory; existing paths are never overwritten")
    analyze.add_argument("--project", default=".")
    serve = commands.add_parser("serve", help="start the local web panel")
    serve.add_argument("--project", default=".")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    task = commands.add_parser("task", help="manage configurable label tasks")
    task_commands = task.add_subparsers(dest="task_command", required=True)
    task_add = task_commands.add_parser("add", help="add a declarative task JSON file")
    task_add.add_argument("file")
    task_add.add_argument("--project", default=".")
    label = commands.add_parser("label", help="run autonomous local labeling for a configured task")
    label.add_argument("source")
    label.add_argument("--task", required=True)
    label.add_argument("--project", default=".")
    label.add_argument("--device", default="auto")
    pipeline = commands.add_parser("run", help="run autonomous labeling followed by a trusted training eligibility cycle")
    pipeline.add_argument("--task", required=True)
    pipeline.add_argument("--source", required=True)
    pipeline.add_argument("--project", default=".")
    pipeline.add_argument("--device", default="auto")
    pipeline_status = commands.add_parser("run-status", help="show a privacy-safe pipeline run summary")
    pipeline_status.add_argument("run_id")
    pipeline_status.add_argument("--project", default=".")
    label_run = commands.add_parser("label-run", help="show privacy-safe summary of an autonomous labeling run")
    label_run.add_argument("run_id")
    label_run.add_argument("--project", default=".")
    model_status = commands.add_parser("model-status", help="show active model and promotion/rollback history")
    model_status.add_argument("task_id")
    model_status.add_argument("--project", default=".")
    dataset = commands.add_parser("dataset", help="prepare an explicit local training dataset")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_prepare = dataset_commands.add_parser("prepare", help="export reviewed examples as JSONL")
    dataset_prepare.add_argument("run_id")
    dataset_prepare.add_argument("--output", required=True)
    dataset_prepare.add_argument("--project", default=".")
    train = commands.add_parser("train", help="explicitly fine-tune a local PEFT/LoRA adapter")
    train.add_argument("dataset")
    train.add_argument("--model-id", required=True)
    train.add_argument("--revision")
    train.add_argument("--output", required=True)
    train.add_argument("--epochs", type=int, default=1)
    train.add_argument("--batch-size", type=int, default=1)
    train.add_argument("--learning-rate", type=float, default=0.0002)
    train.add_argument("--lora-rank", type=int, default=8)
    train.add_argument("--seed", type=int, default=42)
    train.add_argument("--project", default=".")
    supervision = commands.add_parser("supervision", help="register trusted labels from a read-only source")
    supervision_commands = supervision.add_subparsers(dest="supervision_command", required=True)
    supervision_add = supervision_commands.add_parser("add", help="register a trusted label column for a task")
    supervision_add.add_argument("source")
    supervision_add.add_argument("--task", required=True)
    supervision_add.add_argument("--label-column", required=True)
    supervision_add.add_argument("--provenance", required=True)
    supervision_add.add_argument("--trust-kind", required=True, choices=("provided_ground_truth", "validated_rule"))
    supervision_add.add_argument("--label-map", help="JSON object mapping source label values to task labels")
    supervision_add.add_argument("--refresh", action="store_true", help="explicitly bind the same provenance to the current source snapshot")
    supervision_add.add_argument("--project", default=".")
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect":
            profile = inspect_csv(args.csv_path, target=args.target)
            print(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))
            return 0
        if args.command == "project" and args.project_command == "init":
            print(str(init_project(args.path)))
            return 0
        if args.command == "source":
            config = load_project(args.project)
            if args.source_command == "set-type":
                try:
                    existing = config.sources[args.name]
                except KeyError as exc:
                    raise ValueError("Unknown source: {}".format(args.name)) from exc
                available = {column.name for column in open_source(config, args.name).columns()}
                if args.column not in available:
                    raise ValueError("Unknown source column: {}".format(args.column))
                updated_spec = replace(existing, schema={**existing.schema, args.column: args.type})
                updated = ProjectConfig(
                    config.path,
                    {**config.sources, args.name: updated_spec},
                    config.model_roles,
                    config.workspace_dir,
                    config.supervision_sources,
                )
                save_project(updated, config.path)
                print(json.dumps({"source": args.name, "column": args.column, "type": args.type}))
                return 0
            if args.name in config.sources:
                raise ValueError("Source name already exists: {}".format(args.name))
            kind = "csv" if args.source_command == "add-csv" else "sqlite"
            spec = SourceSpec(
                name=args.name,
                kind=kind,
                path=Path(args.path).expanduser().resolve(),
                table=getattr(args, "table", None),
                id_column=getattr(args, "id_column", None),
            )
            if kind == "csv":
                from finlabel.sources.csv_source import CsvSource

                CsvSource(spec).columns()
            else:
                from finlabel.sources.sqlite_source import SqliteSource

                SqliteSource(spec).columns()
            updated = ProjectConfig(
                config.path,
                {**config.sources, args.name: spec},
                config.model_roles,
                config.workspace_dir,
                config.supervision_sources,
            )
            save_project(updated, config.path)
            print(json.dumps({"name": args.name, "kind": kind, "path": str(spec.path)}, ensure_ascii=False))
            return 0
        if args.command == "supervision" and args.supervision_command == "add":
            from finlabel.labeling.task import load_task, task_file_path
            from finlabel.training.trusted_labels import (
                TrustedLabelSourceSpec,
                load_trusted_labels,
                supervision_key,
            )

            config = load_project(args.project)
            if args.source not in config.sources:
                raise ValueError("Unknown project source: {}".format(args.source))
            source = open_source(config, args.source)
            available_columns = tuple(column.name for column in source.columns())
            task = load_task(
                task_file_path(config.workspace_dir, args.task),
                available_columns=available_columns,
            )
            if args.label_column in task.input_columns:
                raise ValueError("The trusted label column cannot be a task inference input column.")
            if args.label_column not in available_columns:
                raise ValueError("Unknown trusted label column: {}".format(args.label_column))
            if args.label_map:
                try:
                    label_mapping = json.loads(args.label_map)
                except json.JSONDecodeError as exc:
                    raise ValueError("--label-map must be a JSON object.") from exc
                if not isinstance(label_mapping, dict):
                    raise ValueError("--label-map must be a JSON object.")
            else:
                label_mapping = {label: label for label in task.labels}
            spec = TrustedLabelSourceSpec(
                source_name=args.source,
                task_id=task.task_id,
                label_column=args.label_column,
                label_mapping=label_mapping,
                provenance_id=args.provenance,
                trust_kind=args.trust_kind,
            )
            key = supervision_key(task.task_id, args.source)
            if key in config.supervision_sources:
                existing_spec = TrustedLabelSourceSpec.from_dict(config.supervision_sources[key])
                if existing_spec != spec:
                    raise ValueError("A different trusted-label configuration is already registered for this task and source.")
                if not args.refresh:
                    batch = load_trusted_labels(config, task)
                    print(json.dumps({
                        "source": args.source,
                        "task_id": task.task_id,
                        "trust_kind": args.trust_kind,
                        "rows": batch.row_count,
                        "feature_columns": list(batch.feature_columns),
                        "label_column": batch.label_column,
                        "snapshot_sha256": batch.snapshot_sha256,
                        "project_config": str(config.path),
                        "already_registered": True,
                    }, ensure_ascii=False, indent=2))
                    return 0
            provisional_sources = {**config.supervision_sources, key: spec.to_dict()}
            batch = load_trusted_labels(
                ProjectConfig(config.path, config.sources, config.model_roles, config.workspace_dir,
                              provisional_sources),
                task,
            )
            persisted_spec = {
                **spec.to_dict(),
                "snapshot_sha256": batch.snapshot_sha256,
                "row_count": batch.row_count,
            }
            updated = ProjectConfig(
                config.path, config.sources, config.model_roles, config.workspace_dir,
                {**config.supervision_sources, key: persisted_spec},
            )
            # project.json is the single atomic authority for both the source spec and snapshot digest.
            save_project(updated, config.path)
            print(json.dumps({
                "source": args.source,
                "task_id": task.task_id,
                "trust_kind": args.trust_kind,
                "rows": batch.row_count,
                "feature_columns": list(batch.feature_columns),
                "label_column": batch.label_column,
                "snapshot_sha256": batch.snapshot_sha256,
                "project_config": str(config.path),
                "registry_key": key,
                "refreshed": bool(args.refresh),
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "schema" and args.schema_command == "capture":
            config = load_project(args.project)
            candidate = capture_schema(open_source(config, args.source))
            save_schema_baseline(candidate, args.output)
            print(json.dumps(asdict(candidate), ensure_ascii=False, indent=2))
            return 0
        if args.command == "monitor":
            config = load_project(args.project)
            findings = monitor_source(open_source(config, args.source), load_schema_baseline(args.baseline))
            print(json.dumps([asdict(finding) for finding in findings], ensure_ascii=False, indent=2))
            return 1 if any(finding.severity == "error" for finding in findings) else 0
        if args.command == "analyze":
            if not args.plan and not args.model_id:
                raise ValueError("Provide --plan or explicitly select a local --model-id.")
            config = load_project(args.project)
            source = open_source(config, args.source)
            plan_override = None
            if args.plan:
                plan_path = Path(args.plan).expanduser()
                plan_override = plan_from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
            backend = None
            if args.model_id:
                from finlabel.models.text_generation import TransformersTextGenerationBackend

                backend = TransformersTextGenerationBackend(args.model_id, args.revision, args.device)
            run = analyze_source(
                source,
                args.question,
                backend,
                plan_override,
                output_path=args.output,
                output_parent=config.workspace_dir / "analyses",
            )
            print(json.dumps({
                "run_id": run.run_id,
                "artifact_dir": str(run.artifact_dir),
                "rows": len(run.result.rows),
                "valid_row_count": run.result.valid_row_count,
                "highlights": list(run.rendered_highlights),
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "serve":
            from finlabel.web.app import create_app

            app = create_app(args.project, host=args.host, port=args.port)
            try:
                import uvicorn
            except ImportError as exc:
                raise RuntimeError("Install finlabel-local[web] to run the local panel.") from exc
            uvicorn.run(app, host=args.host, port=args.port, access_log=False)
            return 0
        if args.command == "task" and args.task_command == "add":
            from finlabel.labeling.task import load_task, save_task, task_file_path

            config = load_project(args.project)
            task = load_task(args.file)
            destination = task_file_path(config.workspace_dir, task.task_id)
            save_task(task, destination)
            print(str(destination))
            return 0
        if args.command == "label":
            from finlabel.labeling.service import run_labeling
            from finlabel.labeling.task import load_task, load_task_policy, task_file_path

            config = load_project(args.project)
            source = open_source(config, args.source)
            task_path = task_file_path(config.workspace_dir, args.task)
            task = load_task(task_path, available_columns=tuple(column.name for column in source.columns()))
            policy = load_task_policy(task)
            if policy is None:
                # No model call is needed: the service persists a terminal
                # missing_policy outcome for every source record.
                backend = None
                calibrator = None
            else:
                from finlabel.training.active_model import active_inference
                backend, calibrator = active_inference(config, task, policy, device=args.device)
            run = run_labeling(source, task, policy, backend, workspace_dir=config.workspace_dir,
                               calibrator=calibrator)
            result = _verified_label_run(config.workspace_dir, run.run_id)
            if result["policy_id"] is None:
                result["notice"] = (
                    "No labeling policy is configured. All records were quarantined without model inference; "
                    "configure task policy_path and rerun."
                )
            elif result["reason_counts"].get("uncalibrated"):
                result["notice"] = (
                    "Predictions are uncalibrated and remain quarantined. A fitted calibrator matching the "
                    "task, model, policy, and score method is required before labels can be applied."
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "run":
            result = run_autonomous_pipeline(args.project, args.source, args.task, device=args.device)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "run-status":
            config = load_project(args.project)
            print(json.dumps(_verified_pipeline_run(config.workspace_dir, args.run_id), ensure_ascii=False, indent=2))
            return 0
        if args.command == "label-run":
            config = load_project(args.project)
            print(json.dumps(_verified_label_run(config.workspace_dir, args.run_id), ensure_ascii=False, indent=2))
            return 0
        if args.command == "model-status":
            from finlabel.training.registry import ModelRegistry

            config = load_project(args.project)
            registry = ModelRegistry(config.workspace_dir)
            active = registry.active(args.task_id)
            safe_active = None
            if active is not None:
                safe_active = {
                    key: active.get(key)
                    for key in ("model_ref", "candidate_id", "evaluation_id", "previous_model_ref", "rollback_from")
                    if active.get(key) is not None
                }
            events = [
                {
                    key: event.get(key)
                    for key in ("event_id", "candidate_id", "evaluation_id", "task_id", "action",
                                "reason_codes", "previous_model_ref", "active_model_ref", "rollback_from", "created_at")
                    if event.get(key) is not None
                }
                for event in registry.history(args.task_id)
            ]
            print(json.dumps({"task_id": args.task_id, "active_model": safe_active, "events": events},
                             ensure_ascii=False, indent=2))
            return 0
        if args.command == "dataset" and args.dataset_command == "prepare":
            from finlabel.training.dataset import prepare_training_dataset

            config = load_project(args.project)
            manifest = prepare_training_dataset(config, args.run_id, args.output)
            print(json.dumps({
                "path": str(manifest.path), "rows": manifest.row_count,
                "manifest": str(manifest.path.with_suffix(manifest.path.suffix + ".manifest.json")),
                "dataset_sha256": manifest.dataset_sha256,
                "excluded_counts": manifest.excluded_counts,
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "train":
            from finlabel.training.backend import TrainingConfig, train_adapter

            config = TrainingConfig(
                args.model_id, args.revision, Path(args.output), args.epochs, args.batch_size,
                args.learning_rate, args.lora_rank, args.seed,
            )
            project_config = load_project(args.project)
            result = train_adapter(args.dataset, config, gate_path=project_config.workspace_dir / "training-gate.json")
            print(json.dumps({
                "output_dir": str(result.output_dir), "base_model_ref": result.base_model_ref,
                "dataset_sha256": result.dataset_sha256, "adapter_files": [str(path) for path in result.adapter_files],
                "final_metrics": dict(result.final_metrics),
            }, ensure_ascii=False, indent=2))
            return 0
        raise ValueError("Unsupported command.")
    except (FileNotFoundError, PermissionError, ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as exc:
        print("finlabel: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
