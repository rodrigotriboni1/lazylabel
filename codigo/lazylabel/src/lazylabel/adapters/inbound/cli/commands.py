"""CLI argument parsing and presentation over injected application entry points."""
import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from lazylabel.domain.analysis.schema import plan_from_dict


def _dominant(reason_counts):
    """Reasons tied for the highest count."""
    top = max(reason_counts.values(), default=0)
    return {reason for reason, count in reason_counts.items() if count == top and top}


def _needs_prerequisites(result):
    if "policy_id" in result:
        return result["policy_id"] is None or "uncalibrated" in _dominant(result["reason_counts"])
    return (result["training"]["state"] == "blocked"
        or bool(_dominant(result["labels"]["reason_counts"]) & {"uncalibrated", "missing_policy"}))


def _with_prerequisites(app, result):
    if _needs_prerequisites(result):
        result["prerequisites"] = app.prerequisites(result["task_id"])
    return result


def main(argv=None, *, application=None, application_factory=None, serve=None):
    parser = argparse.ArgumentParser(prog="lazylabel")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="inspect a local CSV without printing rows")
    inspect.add_argument("csv_path", help="path to a UTF-8 CSV file")
    inspect.add_argument("--target", help="optional target column for class counts")
    project = commands.add_parser("project", help="manage a local LazyLabel project")
    project_commands = project.add_subparsers(dest="project_command", required=True)
    project_init = project_commands.add_parser("init", help="initialize a local project workspace")
    project_init.add_argument("path", help="project directory")
    quickstart = commands.add_parser("quickstart",
        help="scaffold a sample project with synthetic data and starter task files; downloads no model")
    quickstart.add_argument("dir", help="new or empty project directory")
    quickstart.add_argument("--model-id", required=True, help="model reference recorded in task.json; nothing is downloaded")
    quickstart.add_argument("--model-revision")
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
    serve_command = commands.add_parser("serve", help="start the local web panel")
    serve_command.add_argument("--project", default=".")
    serve_command.add_argument("--host", default="127.0.0.1")
    serve_command.add_argument("--port", type=int, default=8765)
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
        app = application if application is not None else application_factory(getattr(args, "project", "."))
        if args.command == "inspect":
            print(json.dumps(app.inspect(args.csv_path, target=args.target), ensure_ascii=False, indent=2))
            return 0
        if args.command == "project" and args.project_command == "init":
            print(str(app.initialize(args.path)))
            return 0
        if args.command == "quickstart":
            result = app.quickstart(args.dir, args.model_id, args.model_revision)
            print("\n".join([
                "Sample project created at {} (source: {}, task: {}).".format(args.dir, result["source"], result["task_id"]),
                "Next steps:",
                "  lazylabel label sample --task sample --project {}".format(args.dir),
                "  lazylabel serve --project {}".format(args.dir),
                "The labels in reference_label are synthetic and registered as trusted labels with provenance "
                "synthetic-sample; provenance is an operator declaration.",
                "The policy values in policy.json are illustrative and must be validated for the task.",
                "Labeling will quarantine every prediction as uncalibrated until calibration evidence exists."]))
            return 0
        if args.command == "source":
            result = app.configure_source(args.source_command, args.name, getattr(args, "path", None),
                column=getattr(args, "column", None), type=getattr(args, "type", None),
                table=getattr(args, "table", None), id_column=getattr(args, "id_column", None))
            print(json.dumps(result, ensure_ascii=args.source_command == "set-type"))
            return 0
        if args.command == "supervision" and args.supervision_command == "add":
            result = app.register_supervision(args.source, args.task, args.label_column,
                args.provenance, args.trust_kind, args.label_map, args.refresh)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "schema" and args.schema_command == "capture":
            print(json.dumps(asdict(app.capture_schema(args.source, args.output)), ensure_ascii=False, indent=2))
            return 0
        if args.command == "monitor":
            findings = app.monitor(args.source, args.baseline)
            print(json.dumps([asdict(item) for item in findings], ensure_ascii=False, indent=2))
            return 1 if any(item.severity == "error" for item in findings) else 0
        if args.command == "analyze":
            if not args.plan and not args.model_id:
                raise ValueError("Provide --plan or explicitly select a local --model-id.")
            plan = None
            if args.plan:
                plan = plan_from_dict(json.loads(Path(args.plan).expanduser().read_text(encoding="utf-8")))
            run = app.analyze(args.source, args.question, plan, model_id=args.model_id,
                              revision=args.revision, device=args.device, output=args.output, use_configured_model=False)
            print(json.dumps({"run_id": run.run_id, "artifact_dir": str(run.artifact_dir),
                "rows": len(run.result.rows), "valid_row_count": run.result.valid_row_count,
                "highlights": list(run.rendered_highlights)}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "serve":
            serve(args.project, host=args.host, port=args.port)
            return 0
        if args.command == "task" and args.task_command == "add":
            print(str(app.add_task(args.file)))
            return 0
        if args.command == "label":
            result = app.label(args.source, args.task, device=args.device)
            if result["policy_id"] is None:
                result["notice"] = (
                    "No labeling policy is configured. All records were quarantined without model inference; "
                    "configure task policy_path and rerun.")
            elif result["reason_counts"].get("uncalibrated"):
                result["notice"] = (
                    "Predictions are uncalibrated and remain quarantined. A fitted calibrator matching the "
                    "task, model, policy, and score method is required before labels can be applied.")
            print(json.dumps(_with_prerequisites(app, result), ensure_ascii=False, indent=2))
            return 0
        if args.command == "run":
            result = _with_prerequisites(app, app.pipeline(args.source, args.task, device=args.device))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "run-status":
            print(json.dumps(_with_prerequisites(app, app.pipeline_status(args.run_id)), ensure_ascii=False, indent=2))
            return 0
        if args.command == "label-run":
            print(json.dumps(app.label_status(args.run_id), ensure_ascii=False, indent=2))
            return 0
        if args.command == "model-status":
            print(json.dumps(app.model_status(args.task_id), ensure_ascii=False, indent=2))
            return 0
        if args.command == "dataset" and args.dataset_command == "prepare":
            manifest = app.prepare_dataset(args.run_id, args.output)
            print(json.dumps({"path": str(manifest.path), "rows": manifest.row_count,
                "manifest": str(manifest.path.with_suffix(manifest.path.suffix + ".manifest.json")),
                "dataset_sha256": manifest.dataset_sha256, "excluded_counts": manifest.excluded_counts},
                ensure_ascii=False, indent=2))
            return 0
        if args.command == "train":
            result = app.train(args.dataset, model_id=args.model_id, revision=args.revision, output=args.output,
                epochs=args.epochs, batch_size=args.batch_size, learning_rate=args.learning_rate,
                lora_rank=args.lora_rank, seed=args.seed)
            print(json.dumps({"output_dir": str(result.output_dir), "base_model_ref": result.base_model_ref,
                "dataset_sha256": result.dataset_sha256, "adapter_files": [str(path) for path in result.adapter_files],
                "final_metrics": dict(result.final_metrics)}, ensure_ascii=False, indent=2))
            return 0
        raise ValueError("Unsupported command.")
    except (FileNotFoundError, PermissionError, ValueError, OSError, KeyError, RuntimeError, sqlite3.Error) as exc:
        print("lazylabel: {}".format(exc), file=sys.stderr)
        return 2
