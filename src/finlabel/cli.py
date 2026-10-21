"""Command-line interface for local dataset inspection."""

import argparse
import json
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
    label = commands.add_parser("label", help="generate local suggestions for a configured task")
    label.add_argument("source")
    label.add_argument("--task", required=True)
    label.add_argument("--project", default=".")
    label.add_argument("--device", default="auto")
    review = commands.add_parser("review", help="interactively review suggestions in a local run")
    review.add_argument("run_id")
    review.add_argument("--project", default=".")
    dataset = commands.add_parser("dataset", help="prepare an explicit local training dataset")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_check = dataset_commands.add_parser("check", help="check integrity and coverage of a training dataset")
    dataset_check.add_argument("dataset", help="JSONL dataset path")
    dataset_check.add_argument("--project", default=".")
    dataset_prepare = dataset_commands.add_parser("prepare", help="export reviewed examples as JSONL")
    dataset_prepare.add_argument("run_id")
    dataset_prepare.add_argument("--output", required=True)
    dataset_prepare.add_argument("--project", default=".")
    dataset_split = dataset_commands.add_parser("split", help="create deterministic train and holdout files")
    dataset_split.add_argument("dataset", help="reviewed JSONL dataset path")
    dataset_split.add_argument("--strategy", required=True, choices=("stratified_random", "temporal", "group"))
    dataset_split.add_argument("--holdout-fraction", required=True, type=float)
    dataset_split.add_argument("--seed", required=True, type=int)
    dataset_split.add_argument("--output", required=True)
    dataset_split.add_argument("--time-column")
    dataset_split.add_argument("--group-column")
    dataset_split.add_argument("--project", default=".")
    train = commands.add_parser("train", help="explicitly fine-tune a local PEFT/LoRA adapter")
    train.add_argument("bundle_dir", help="directory containing train.jsonl, holdout.jsonl and manifest.json; raw dataset paths are not accepted")
    train.add_argument("--model-id", required=True)
    train.add_argument("--revision")
    train.add_argument("--output", required=True)
    train.add_argument("--epochs", type=int, default=1)
    train.add_argument("--batch-size", type=int, default=1)
    train.add_argument("--learning-rate", type=float, default=0.0002)
    train.add_argument("--lora-rank", type=int, default=8)
    train.add_argument("--seed", type=int, default=42)
    train.add_argument("--confirm-exploratory", action="store_true", help="explicitly accept the bundle's quality and split warnings")
    train.add_argument("--project", default=".")
    model = commands.add_parser("model", help="inspect and manage local model versions")
    model_commands = model.add_subparsers(dest="model_command", required=True)
    model_versions = model_commands.add_parser("versions", help="list locally registered model versions")
    model_versions.add_argument("--project", default=".")
    model_active = model_commands.add_parser("active", help="show the active local model version")
    model_active.add_argument("--project", default=".")
    model_register = model_commands.add_parser("register", help="register a completed local adapter candidate")
    model_register.add_argument("adapter_dir")
    model_register.add_argument("--bundle-manifest", required=True)
    model_register.add_argument("--version-id")
    model_register.add_argument("--project", default=".")
    model_evaluate = model_commands.add_parser("evaluate", help="evaluate a registered candidate on its holdout")
    model_evaluate.add_argument("version_id")
    model_evaluate.add_argument("--output", required=True)
    model_evaluate.add_argument("--project", default=".")
    model_activate = model_commands.add_parser("activate", help="explicitly activate an evaluated candidate")
    model_activate.add_argument("version_id")
    model_activate.add_argument("--confirm", action="store_true", required=True)
    model_activate.add_argument("--project", default=".")
    model_reject = model_commands.add_parser("reject", help="reject an inactive candidate")
    model_reject.add_argument("version_id")
    model_reject.add_argument("--reason", required=True)
    model_reject.add_argument("--confirm", action="store_true", required=True)
    model_reject.add_argument("--project", default=".")
    model_rollback = model_commands.add_parser("rollback", help="explicitly restore a superseded version")
    model_rollback.add_argument("version_id")
    model_rollback.add_argument("--confirm", action="store_true", required=True)
    model_rollback.add_argument("--project", default=".")
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
            )
            save_project(updated, config.path)
            print(json.dumps({"name": args.name, "kind": kind, "path": str(spec.path)}, ensure_ascii=False))
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
            from finlabel.labeling.service import suggest_labels
            from finlabel.labeling.task import load_task, task_file_path
            from finlabel.models.text_generation import TransformersTextGenerationBackend

            config = load_project(args.project)
            source = open_source(config, args.source)
            task_path = task_file_path(config.workspace_dir, args.task)
            task = load_task(task_path, available_columns=tuple(column.name for column in source.columns()))
            backend = TransformersTextGenerationBackend(task.model_id, task.model_revision, args.device)
            run = suggest_labels(source, task, backend, workspace_dir=config.workspace_dir)
            print(json.dumps({
                "run_id": run.run_id, "source": run.source_name, "task": run.task_id,
                "model_ref": run.model_ref, "suggestions": run.row_count, "invalid": run.invalid_count,
                "suggestion_file": str(run.suggestion_path),
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "review":
            from finlabel.labeling.task import load_task, task_file_path, validate_label
            from finlabel.labeling.suggestions import verify_suggestions_file
            from finlabel.review import ReviewAction, ReviewLog

            config = load_project(args.project)
            run_dir = config.workspace_dir / "runs" / args.run_id
            metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            verify_suggestions_file(run_dir / "suggestions.jsonl", metadata.get("suggestions_sha256"))
            source = open_source(config, metadata["source_name"])
            task = load_task(task_file_path(config.workspace_dir, metadata["task_id"]),
                             available_columns=tuple(column.name for column in source.columns()))
            suggestions = [json.loads(line) for line in (run_dir / "suggestions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            source_records = iter(source.iter_records(task.input_columns))
            log = ReviewLog(config.workspace_dir / "review.jsonl")
            for suggestion in suggestions:
                record = next(source_records, None)
                while record is not None and record.record_id != suggestion["record_id"]:
                    record = next(source_records, None)
                print(json.dumps({"suggested_label": suggestion["label"],
                                  "stale": record is None or record.input_digest != suggestion["input_digest"]}, ensure_ascii=False))
                action_text = input("accept / edit LABEL / reject / skip> ").strip()
                if action_text == "skip":
                    continue
                if not record or record.input_digest != suggestion["input_digest"]:
                    print("Source row changed; this suggestion cannot be reviewed.", file=sys.stderr)
                    continue
                parts = action_text.split(maxsplit=1)
                if parts == ["accept"]:
                    action, final_label = ReviewAction.ACCEPTED, suggestion["label"]
                elif len(parts) == 2 and parts[0] == "edit":
                    action, final_label = ReviewAction.CORRECTED, validate_label(task, parts[1])
                elif parts == ["reject"]:
                    action, final_label = ReviewAction.REJECTED, None
                else:
                    raise ValueError("Review action must be accept, edit LABEL, reject, or skip.")
                log.record(
                    suggestion["record_id"], suggestion["label"], action, final_label, suggestion["model_ref"],
                    run_id=args.run_id, source_name=metadata["source_name"], task_id=task.task_id,
                    input_digest=suggestion["input_digest"], suggestion_id=suggestion["suggestion_id"],
                )
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
        if args.command == "dataset" and args.dataset_command == "check":
            from finlabel.training.quality import inspect_training_dataset

            report = inspect_training_dataset(load_project(args.project), args.dataset)
            print(json.dumps({
                "ready": report.ready,
                "total": report.total,
                "label_counts": report.label_counts,
                "duplicate_suggestion_ids": report.duplicate_suggestion_ids,
                "duplicate_event_ids": report.duplicate_event_ids,
                "duplicate_examples": report.duplicate_examples,
                "excluded_counts": report.excluded_counts,
                "source_snapshot_matches": report.source_snapshot_matches,
                "blockers": list(report.blockers),
                "warnings": list(report.warnings),
                "next_action": "Use the explicit train command only after reviewing this report and confirming warnings." if report.ready
                    else "Resolve every blocker, then check the dataset again.",
            }, ensure_ascii=False, indent=2))
            return 0 if report.ready else 1
        if args.command == "dataset" and args.dataset_command == "split":
            from finlabel.labeling.task import load_task, task_file_path
            from finlabel.training.dataset import load_dataset_manifest
            from finlabel.training.split import SplitConfig, create_training_bundle

            project_config = load_project(args.project)
            dataset_manifest = load_dataset_manifest(args.dataset)
            selected_task = load_task(task_file_path(project_config.workspace_dir, dataset_manifest["task_id"]))
            split_config = SplitConfig(args.strategy, args.holdout_fraction, args.seed,
                                       group_column=args.group_column, time_column=args.time_column)
            bundle = create_training_bundle(project_config, args.dataset, selected_task, split_config, args.output)
            print(json.dumps({
                "train_path": str(bundle.train_path), "holdout_path": str(bundle.holdout_path),
                "manifest_path": str(bundle.manifest_path), "train_count": bundle.train_count,
                "holdout_count": bundle.holdout_count, "split_sha256": bundle.split_sha256,
                "warnings": list(bundle.warnings),
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "train":
            from finlabel.training.backend import TrainingConfig, load_training_bundle, train_adapter
            from finlabel.training.registry import ModelRegistry

            config = TrainingConfig(
                args.model_id, args.revision, Path(args.output), args.epochs, args.batch_size,
                args.learning_rate, args.lora_rank, args.seed,
            )
            project_config = load_project(args.project)
            bundle_path = Path(args.bundle_dir).expanduser()
            if bundle_path.is_file() or bundle_path.suffix.lower() in {".jsonl", ".json", ".csv"}:
                raise ValueError(
                    "train requires a split bundle directory, not a raw dataset. Run "
                    "finlabel dataset check DATASET, then finlabel dataset split DATASET "
                    "--strategy STRATEGY --holdout-fraction FRACTION --seed SEED --output BUNDLE."
                )
            bundle = load_training_bundle(bundle_path)
            result = train_adapter(bundle, config, gate_path=project_config.workspace_dir / "training-gate.json",
                                   exploratory_confirmed=args.confirm_exploratory)
            registry = ModelRegistry(project_config.workspace_dir)
            version = registry.register_candidate(result.output_dir, bundle.manifest_path)
            print(json.dumps({
                "output_dir": str(result.output_dir), "base_model_ref": result.base_model_ref,
                "dataset_sha256": result.dataset_sha256, "train_count": bundle.train_count,
                "holdout_count": bundle.holdout_count, "split_sha256": result.split_sha256,
                "adapter_sha256": result.adapter_sha256, "final_metrics": dict(result.final_metrics),
                "registered_version": version.version_id, "state": version.state,
                "next_action": "Run finlabel model evaluate VERSION --output REPORT after confirming local model availability.",
            }, ensure_ascii=False, indent=2))
            return 0
        if args.command == "model":
            from dataclasses import asdict
            from finlabel.training.registry import ModelRegistry

            project_config = load_project(args.project)
            registry = ModelRegistry(project_config.workspace_dir)
            if args.model_command == "versions":
                active = registry.active()
                print(json.dumps({"versions": [asdict(item) for item in registry.list_versions()],
                                  "active": asdict(active) if active else None},
                                 ensure_ascii=False, indent=2, default=str))
                return 0
            if args.model_command == "active":
                current = registry.active()
                print(json.dumps(asdict(current) if current else None, ensure_ascii=False, indent=2, default=str))
                return 0
            if args.model_command == "register":
                version = registry.register_candidate(args.adapter_dir, args.bundle_manifest, args.version_id)
                print(json.dumps(asdict(version), ensure_ascii=False, indent=2, default=str))
                return 0
            if args.model_command == "evaluate":
                from finlabel.labeling.task import load_task, task_file_path
                from finlabel.training.backend import load_training_bundle
                from finlabel.training.evaluation import evaluate_candidate

                version = next((item for item in registry.list_versions() if item.version_id == args.version_id), None)
                if version is None:
                    raise KeyError("Model version was not found: {}".format(args.version_id))
                output_path = registry._contained(args.output, "Evaluation report path")
                bundle = load_training_bundle(version.bundle_manifest_path.parent)
                manifest = json.loads(version.bundle_manifest_path.read_text(encoding="utf-8"))
                task = load_task(task_file_path(project_config.workspace_dir, manifest["task_id"]))
                report = evaluate_candidate(bundle, task, version.adapter_path, output_path=output_path)
                updated = registry.record_evaluation(args.version_id, output_path)
                active = registry.active()
                print(json.dumps({"version": asdict(updated), "report_path": str(output_path),
                                  "overall": report.overall, "per_label": [asdict(item) for item in report.per_label],
                                  "warnings": list(report.warnings), "active_version": active.version_id if active else None,
                                  "next_action": "Review metrics and warnings; activate only with --confirm, or reject with a reason."},
                                 ensure_ascii=False, indent=2, default=str))
                return 0
            if args.model_command == "activate":
                version = registry.activate(args.version_id)
                print(json.dumps({"version": asdict(version), "active_version": version.version_id},
                                 ensure_ascii=False, indent=2, default=str))
                return 0
            if args.model_command == "reject":
                version = registry.reject_candidate(args.version_id, args.reason)
                print(json.dumps(asdict(version), ensure_ascii=False, indent=2, default=str))
                return 0
            if args.model_command == "rollback":
                version = registry.rollback(args.version_id)
                print(json.dumps({"version": asdict(version), "active_version": version.version_id},
                                 ensure_ascii=False, indent=2, default=str))
                return 0
        raise ValueError("Unsupported command.")
    except (FileNotFoundError, PermissionError, ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as exc:
        print("finlabel: {}".format(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
