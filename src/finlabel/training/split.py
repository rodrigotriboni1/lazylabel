"""Local, deterministic partitions of a reviewed dataset."""

import hashlib
import json
import math
import random
import shutil
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional, Sequence, Union

from finlabel.labeling.suggestions import verify_suggestions_file
from finlabel.labeling.task import LabelTask, load_task, task_file_path
from finlabel.project import open_source
from finlabel.review import ReviewAction, ReviewLog
from finlabel.sources.base import ProjectConfig
from finlabel.training.dataset import _prompt, _sha256, load_dataset_manifest, read_training_rows
from finlabel.training.quality import DatasetQualityReport, inspect_training_dataset


PathLike = Union[str, Path]


@dataclass(frozen=True)
class SplitConfig:
    strategy: str
    holdout_fraction: float
    seed: int
    group_column: Optional[str] = None
    time_column: Optional[str] = None

    def __post_init__(self):
        if self.strategy not in {"stratified_random", "temporal", "group"}:
            raise ValueError("Unknown split strategy.")
        if isinstance(self.holdout_fraction, bool) or not isinstance(self.holdout_fraction, (int, float)) or not math.isfinite(self.holdout_fraction) or not 0 < self.holdout_fraction < 1:
            raise ValueError("holdout_fraction must be finite and between 0 and 1.")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer.")
        if self.strategy == "temporal":
            if not isinstance(self.time_column, str) or not self.time_column.strip() or self.group_column is not None:
                raise ValueError("Temporal splitting requires only --time-column.")
        elif self.strategy == "group":
            if not isinstance(self.group_column, str) or not self.group_column.strip() or self.time_column is not None:
                raise ValueError("Group splitting requires only --group-column.")
        elif self.group_column is not None or self.time_column is not None:
            raise ValueError("Stratified splitting does not accept group/time columns.")


@dataclass(frozen=True)
class TrainingBundle:
    train_path: Path
    holdout_path: Path
    manifest_path: Path
    quality_report: DatasetQualityReport
    train_count: int
    holdout_count: int
    split_sha256: str
    warnings: Sequence[str]


def _source_digest(values: dict) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _selected_key(value, strategy: str, declared_type: Optional[str]):
    if value is None or isinstance(value, str) and not value.strip():
        raise ValueError("Selected split key contains a missing value.")
    if isinstance(value, (bool, bytes, bytearray, dict, list, tuple)):
        raise ValueError("Selected split key has an unsupported value type.")
    if strategy == "group":
        if not isinstance(value, (str, int, float)) or isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Group key must be a finite scalar string or number.")
        if isinstance(value, str):
            return ("string", value)
        number = (Decimal.from_float(value) if isinstance(value, float) else Decimal(value)).normalize()
        return ("number", Decimal(0) if number == 0 else number)
    if declared_type not in {"date", "datetime", "integer", "decimal"}:
        raise ValueError("Temporal column requires an explicit date, datetime, integer, or decimal source type.")
    try:
        if declared_type == "date":
            if not isinstance(value, str):
                raise ValueError()
            return date.fromisoformat(value)
        if declared_type == "datetime":
            if not isinstance(value, str):
                raise ValueError()
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed
        if declared_type == "integer":
            if isinstance(value, float) or isinstance(value, str) and ("." in value or "e" in value.lower()):
                raise ValueError()
            return int(value)
        numeric = Decimal(str(value))
        if not numeric.is_finite():
            raise ValueError()
        return numeric
    except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
        raise ValueError("Temporal split key does not match its declared source type.") from exc


def _provenance(project, manifest, task, source, key_column):
    workspace = Path(project.workspace_dir).expanduser()
    run_id = manifest["run_id"]
    run_dir = workspace / "runs" / run_id
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    suggestions_path = run_dir / "suggestions.jsonl"
    verify_suggestions_file(suggestions_path, run_metadata.get("suggestions_sha256"))
    suggestions = {}
    with suggestions_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                item = json.loads(line)
                suggestion_id = item.get("suggestion_id")
                if suggestion_id in suggestions:
                    raise ValueError("Suggestion run contains duplicate IDs.")
                suggestions[suggestion_id] = item
    events = {event.event_id: event for event in ReviewLog(workspace / "review.jsonl").read()}
    expected = {}
    for index, (suggestion_id, event_id) in enumerate(zip(manifest["included_suggestion_ids"], manifest["included_event_ids"])):
        suggestion = suggestions.get(suggestion_id)
        event = events.get(event_id)
        if not suggestion or not event or event.suggestion_id != suggestion_id or event.run_id != run_id or event.action not in (ReviewAction.ACCEPTED, ReviewAction.CORRECTED):
            raise ValueError("Dataset provenance does not match the suggestion run and review log.")
        if any((suggestion.get("run_id") != run_id, suggestion.get("source_name") != manifest["source_name"], suggestion.get("task_id") != task.task_id,
                event.source_name != manifest["source_name"], event.task_id != task.task_id, event.record_id != suggestion.get("record_id"), event.input_digest != suggestion.get("input_digest"),
                event.suggested_label != suggestion.get("label"))):
            raise ValueError("Dataset provenance has a mismatched source, task, or digest.")
        record_id = suggestion.get("record_id")
        if not isinstance(record_id, str) or record_id in expected:
            raise ValueError("Dataset provenance contains duplicate or invalid source record IDs.")
        expected[record_id] = (index, suggestion["input_digest"], event.final_label)
    keys = [None] * len(expected)
    prompts = [None] * len(expected)
    observed_order = []
    columns = list(task.input_columns)
    if key_column and key_column not in columns:
        columns.append(key_column)
    for record in source.iter_records(columns):
        matched = expected.get(record.record_id)
        if matched is None:
            continue
        index, expected_digest, _ = matched
        selected = {name: record.values[name] for name in task.input_columns}
        if _source_digest(selected) != expected_digest:
            raise ValueError("Source row digest changed after dataset preparation.")
        observed_order.append(index)
        prompts[index] = _prompt(task, selected)
        keys[index] = record.values[key_column] if key_column else None
    if observed_order != list(range(len(expected))):
        raise ValueError("Source rows no longer match dataset provenance order.")
    labels = [None] * len(expected)
    for _, (index, _, label) in expected.items():
        labels[index] = label
    return keys, labels, prompts


def _partition(labels, keys, ids, task, config, declared_type):
    count = len(labels)
    if count < 2:
        raise ValueError("At least two rows are required for a train/holdout split.")
    target = max(1, min(count - 1, round(count * config.holdout_fraction)))
    if config.strategy == "stratified_random":
        by_label = {label: [] for label in task.labels}
        for index, label in enumerate(labels):
            by_label[label].append(index)
        if any(len(indices) < 2 for indices in by_label.values()):
            raise ValueError("Every configured class needs at least two examples for stratified train/holdout support.")
        held = set()
        for label, indices in by_label.items():
            random.Random("{}:{}".format(config.seed, label)).shuffle(indices)
            amount = max(1, min(len(indices) - 1, round(len(indices) * config.holdout_fraction)))
            held.update(indices[:amount])
    elif config.strategy == "temporal":
        typed = [_selected_key(key, "temporal", declared_type) for key in keys]
        try:
            ordered = sorted(range(count), key=lambda i: (typed[i], ids[i]))
        except TypeError as exc:
            raise ValueError("Temporal values mix incompatible timestamp types.") from exc
        held = set(ordered[-target:])
    else:
        groups = {}
        for index, key in enumerate(keys):
            groups.setdefault(_selected_key(key, "group", None), []).append(index)
        if len(groups) < 2:
            raise ValueError("Group splitting needs at least two distinct groups.")
        ordered_groups = sorted(groups, key=lambda value: (value[0], str(value[1])))
        random.Random(config.seed).shuffle(ordered_groups)
        options = []
        for boundary in range(1, len(ordered_groups)):
            chosen = ordered_groups[:boundary]
            amount = sum(len(groups[key]) for key in chosen)
            options.append((abs(amount - target), boundary))
        boundary = min(options)[1]
        held = {index for key in ordered_groups[:boundary] for index in groups[key]}
    train = set(range(count)) - held
    warnings = []
    if config.strategy != "stratified_random":
        for label in task.labels:
            if not any(labels[i] == label for i in held) or not any(labels[i] == label for i in train):
                warnings.append("Class {!r} lacks support in one partition under the selected {} strategy.".format(label, config.strategy))
    return train, held, warnings


def create_training_bundle(project: ProjectConfig, dataset_path: PathLike, task: LabelTask, config: SplitConfig, output_dir: PathLike) -> TrainingBundle:
    """Revalidate provenance and write a local train/holdout bundle."""
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing bundle directory.")
    dataset = Path(dataset_path).expanduser().resolve()
    report = inspect_training_dataset(project, dataset)
    if not report.ready:
        raise ValueError("Dataset quality gate blocked the split: {}".format("; ".join(report.blockers)))
    manifest = load_dataset_manifest(dataset)
    source = open_source(project, manifest["source_name"])
    saved_task = load_task(task_file_path(project.workspace_dir, manifest["task_id"]), available_columns=tuple(c.name for c in source.columns()))
    if task != saved_task:
        raise ValueError("Selected task does not match the dataset task manifest.")
    key_column = config.time_column if config.strategy == "temporal" else config.group_column
    if key_column and key_column not in {column.name for column in source.columns()}:
        raise ValueError("Selected split column is absent from the source.")
    rows = read_training_rows(dataset, manifest)
    keys, labels, prompts = _provenance(project, manifest, task, source, key_column)
    for index, row in enumerate(rows):
        try:
            completion = json.loads(row["completion"])
        except json.JSONDecodeError as exc:
            raise ValueError("Dataset completion is invalid.") from exc
        if completion.get("label") != labels[index]:
            raise ValueError("Dataset label differs from its reviewed provenance.")
        if row["prompt"] != prompts[index]:
            raise ValueError("Dataset prompt differs from its source provenance.")
    train, held, split_warnings = _partition(labels, keys, manifest["included_suggestion_ids"], task, config, source.spec.schema.get(key_column) if key_column else None)
    warnings = tuple(dict.fromkeys(tuple(report.warnings) + tuple(split_warnings)))
    # Recheck source and dataset after the provenance read, before publishing files.
    final_report = inspect_training_dataset(project, dataset)
    if not final_report.ready or final_report != report or _sha256(dataset) != manifest["dataset_sha256"]:
        raise ValueError("Dataset or source changed while preparing the split.")
    output.mkdir(parents=True)
    try:
        paths = {"train": output / "train.jsonl", "holdout": output / "holdout.jsonl"}
        partitions = {"train": train, "holdout": held}
        distributions = {}
        provenance = {}
        file_hashes = {}
        for name, indices in partitions.items():
            selected = [i for i in range(len(rows)) if i in indices]
            with paths[name].open("w", encoding="utf-8", newline="\n") as handle:
                for index in selected:
                    handle.write(json.dumps(rows[index], ensure_ascii=False, separators=(",", ":")) + "\n")
            distributions[name] = {label: sum(labels[i] == label for i in selected) for label in task.labels}
            provenance[name] = {
                "suggestion_ids": [manifest["included_suggestion_ids"][i] for i in selected],
                "event_ids": [manifest["included_event_ids"][i] for i in selected],
            }
            file_hashes[name + "_sha256"] = _sha256(paths[name])
        if set(provenance["train"]["suggestion_ids"]) & set(provenance["holdout"]["suggestion_ids"]) or set(provenance["train"]["event_ids"]) & set(provenance["holdout"]["event_ids"]):
            raise ValueError("Provenance ID crosses train and holdout partitions.")
        content = {
            "dataset_path": str(dataset), "dataset_manifest_path": str(dataset.with_suffix(dataset.suffix + ".manifest.json")),
            "dataset_sha256": manifest["dataset_sha256"], "task_id": task.task_id, "run_id": manifest["run_id"],
            "strategy": config.strategy, "holdout_fraction": config.holdout_fraction, "seed": config.seed,
            "train_count": len(train), "holdout_count": len(held), "label_distributions": distributions,
            "provenance": provenance, "quality_report": asdict(report), "warnings": list(warnings), **file_hashes,
        }
        stable = {key: value for key, value in content.items() if key not in {"dataset_path", "dataset_manifest_path"}}
        split_sha256 = hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        content["split_sha256"] = split_sha256
        manifest_path = output / "manifest.json"
        manifest_path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(output)
        raise
    return TrainingBundle(paths["train"], paths["holdout"], manifest_path, report, len(train), len(held), split_sha256, warnings)
