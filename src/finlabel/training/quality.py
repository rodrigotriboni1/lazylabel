"""Deterministic integrity and coverage checks for reviewed training data."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence, Union

from finlabel.labeling.task import load_task, task_file_path
from finlabel.project import open_source
from finlabel.sources.base import ProjectConfig
from finlabel.training.dataset import dataset_manifest_path, load_dataset_manifest


PathLike = Union[str, Path]


@dataclass(frozen=True)
class DatasetQualityReport:
    total: int
    label_counts: Mapping[str, int]
    duplicate_suggestion_ids: int
    duplicate_event_ids: int
    duplicate_examples: int
    excluded_counts: Mapping[str, int]
    source_snapshot_matches: bool
    warnings: Sequence[str]
    blockers: Sequence[str]
    ready: bool


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_object(path: Path, description: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read {}: {}".format(description, exc)) from exc
    if not isinstance(value, dict):
        raise ValueError("{} must be a JSON object.".format(description))
    return value


def _snapshot(source, task) -> str:
    if source.spec.kind == "csv":
        return "csv:" + _sha256(source.path)
    digest = hashlib.sha256()
    for record in source.iter_records(task.input_columns):
        if record.record_id is None:
            raise ValueError("SQLite snapshot requires stable record IDs.")
        digest.update(record.record_id.encode("utf-8"))
        digest.update(record.input_digest.encode("ascii"))
    return "sqlite:" + hashlib.sha256((str(source.spec.path.resolve()) + digest.hexdigest()).encode("utf-8")).hexdigest()


def inspect_training_dataset(project: ProjectConfig, dataset_path: PathLike) -> DatasetQualityReport:
    """Inspect a dataset and its current source without importing ML packages."""
    dataset = Path(dataset_path).expanduser().resolve()
    manifest_path = dataset_manifest_path(dataset)
    blockers, warnings = [], []
    counts: Counter = Counter()
    suggestion_ids, event_ids, examples = [], [], []
    excluded: Mapping[str, int] = {}
    snapshot_matches = False
    total = 0
    try:
        manifest = load_dataset_manifest(dataset)
        required = {"run_id", "task_id", "source_name", "row_count", "selected_columns", "included_event_ids",
                    "included_suggestion_ids", "source_snapshot_ref", "excluded_counts", "dataset_sha256"}
        missing = required - set(manifest)
        if missing:
            raise ValueError("Dataset manifest is missing fields: {}".format(", ".join(sorted(missing))))
        if _sha256(dataset) != manifest.get("dataset_sha256"):
            blockers.append("Dataset hash does not match its manifest.")
        workspace = Path(project.workspace_dir).expanduser()
        run_id, task_id, source_name = manifest["run_id"], manifest["task_id"], manifest["source_name"]
        if not all(isinstance(value, str) and value for value in (run_id, task_id, source_name)):
            raise ValueError("Dataset manifest has invalid run, task, or source identity.")
        run_dir = workspace / "runs" / run_id
        run_metadata = _json_object(run_dir / "run.json", "suggestion run metadata")
        if run_metadata.get("run_id") != run_id or run_metadata.get("task_id") != task_id or run_metadata.get("source_name") != source_name:
            raise ValueError("Dataset manifest does not match its suggestion run.")
        source = open_source(project, source_name)
        task = load_task(task_file_path(workspace, task_id), available_columns=tuple(c.name for c in source.columns()))
        if list(manifest["selected_columns"]) != list(task.input_columns):
            blockers.append("Dataset schema does not match the configured task input columns.")
        actual_snapshot = _snapshot(source, task)
        snapshot_matches = actual_snapshot == manifest.get("source_snapshot_ref")
        if not snapshot_matches:
            blockers.append("Current source snapshot cannot be verified against the dataset.")
        excluded_raw = manifest.get("excluded_counts")
        if not isinstance(excluded_raw, dict) or any(
            not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, int) or value < 0
            for key, value in excluded_raw.items()
        ):
            blockers.append("Manifest excluded_counts must map names to non-negative integers.")
            excluded = {}
        else:
            excluded = excluded_raw
        stale = excluded.get("stale", 0)
        if isinstance(stale, bool) or not isinstance(stale, int) or stale < 0:
            blockers.append("Manifest stale exclusion count is malformed.")
        elif stale:
            blockers.append("Dataset manifest records stale-source exclusions.")
        for key in ("included_event_ids", "included_suggestion_ids"):
            if not isinstance(manifest.get(key), list) or not all(isinstance(item, str) and item for item in manifest[key]):
                raise ValueError("Dataset manifest {} must be a list of non-empty IDs.".format(key))
        event_ids = manifest["included_event_ids"]
        suggestion_ids = manifest["included_suggestion_ids"]
        row_count = manifest.get("row_count")
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
            blockers.append("Manifest row_count must be a non-negative integer.")
            row_count = -1
        if len(event_ids) != row_count or len(suggestion_ids) != row_count:
            blockers.append("Manifest provenance counts do not match row_count.")
        try:
            with dataset.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        blockers.append("Dataset contains a blank line at line {}.".format(line_number))
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        blockers.append("Dataset contains malformed JSON at line {}.".format(line_number))
                        continue
                    if not isinstance(row, dict) or set(row) != {"prompt", "completion"} or not isinstance(row.get("prompt"), str) or not row["prompt"].strip() or not isinstance(row.get("completion"), str) or not row["completion"].strip():
                        blockers.append("Dataset row schema is invalid at line {}.".format(line_number))
                        continue
                    total += 1
                    try:
                        completion = json.loads(row["completion"])
                    except json.JSONDecodeError:
                        blockers.append("Dataset completion schema is invalid at line {}.".format(line_number))
                        continue
                    if not isinstance(completion, dict) or not isinstance(completion.get("label"), str):
                        blockers.append("Dataset completion schema is invalid at line {}.".format(line_number))
                        continue
                    label = completion["label"]
                    if label not in task.labels:
                        blockers.append("Dataset contains a label not configured for the task.")
                    else:
                        counts[label] += 1
                    examples.append((row["prompt"], row["completion"]))
        except (OSError, UnicodeDecodeError) as exc:
            blockers.append("Could not read dataset: {}".format(exc))
        if total == 0:
            blockers.append("Dataset is empty.")
        if total != row_count:
            blockers.append("Dataset row count does not match its manifest.")
        for key, values in (("suggestion", suggestion_ids), ("event", event_ids)):
            duplicates = len(values) - len(set(values))
            if duplicates:
                blockers.append("Dataset manifest contains duplicate {} IDs.".format(key))
        if len(examples) != len(set(examples)):
            warnings.append("Identical prompt/completion examples are repeated; review them manually.")
        for label, minimum in task.min_examples_per_label.items():
            if counts[label] < minimum:
                warnings.append("Label {!r} has {} examples; configured minimum is {}.".format(label, counts[label], minimum))
        all_counts = [counts[label] for label in task.labels]
        if all_counts and max(all_counts) > 3 * min(all_counts):
            warnings.append("Label distribution is imbalanced; review coverage before training.")
    except (ValueError, KeyError, OSError, TypeError) as exc:
        blockers.append(str(exc))
    duplicate_suggestions = len(suggestion_ids) - len(set(suggestion_ids)) if suggestion_ids else 0
    duplicate_events = len(event_ids) - len(set(event_ids)) if event_ids else 0
    duplicate_examples = len(examples) - len(set(examples)) if examples else 0
    unique_blockers = tuple(dict.fromkeys(blockers))
    label_counts = {label: counts.get(label, 0) for label in task.labels} if "task" in locals() else dict(counts)
    return DatasetQualityReport(total, label_counts, duplicate_suggestions, duplicate_events, duplicate_examples,
                                dict(excluded), snapshot_matches, tuple(warnings), unique_blockers, not unique_blockers)
