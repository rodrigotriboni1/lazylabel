"""Declarative label tasks with a small, validated JSON format."""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence, Union


PathLike = Union[str, Path]
_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def task_file_path(workspace_dir: PathLike, task_id: str) -> Path:
    if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
        raise ValueError("task_id must use 1-64 safe filename characters.")
    return Path(workspace_dir).expanduser() / "tasks" / (task_id + ".json")


@dataclass(frozen=True)
class LabelTask:
    task_id: str
    instructions: str
    input_columns: Sequence[str]
    labels: Sequence[str]
    model_id: str
    model_revision: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.task_id, str) or not _TASK_ID.fullmatch(self.task_id):
            raise ValueError("task_id must use 1-64 safe filename characters.")
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise ValueError("Task instructions must be a non-empty string.")
        if not isinstance(self.input_columns, (list, tuple)) or not self.input_columns:
            raise ValueError("A task must select at least one input column.")
        if not all(isinstance(name, str) and name.strip() for name in self.input_columns):
            raise ValueError("Task input columns must be non-empty strings.")
        if len(set(self.input_columns)) != len(self.input_columns):
            raise ValueError("Task input columns must be unique.")
        if not isinstance(self.labels, (list, tuple)) or not self.labels:
            raise ValueError("A task must define at least one label.")
        if not all(isinstance(label, str) and label.strip() for label in self.labels):
            raise ValueError("Task labels must be non-empty strings.")
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("Task labels must be unique.")
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("A task requires a model_id.")
        if self.model_revision is not None and not isinstance(self.model_revision, str):
            raise ValueError("model_revision must be a string when provided.")


def task_to_dict(task: LabelTask) -> dict:
    return asdict(task)


def task_from_dict(raw: dict, *, available_columns: Optional[Sequence[str]] = None) -> LabelTask:
    if not isinstance(raw, dict):
        raise ValueError("Task document must be a JSON object.")
    allowed = {"task_id", "instructions", "input_columns", "labels", "model_id", "model_revision"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError("Unknown task field(s): {}".format(", ".join(sorted(unknown))))
    try:
        normalized = dict(raw)
        normalized["input_columns"] = tuple(normalized.get("input_columns", ()))
        normalized["labels"] = tuple(normalized.get("labels", ()))
        task = LabelTask(**normalized)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid label task: {}".format(exc)) from exc
    if available_columns is not None:
        missing = sorted(set(task.input_columns) - set(available_columns))
        if missing:
            raise ValueError("Task references unknown source column(s): {}".format(", ".join(missing)))
    return task


def load_task(path: PathLike, *, available_columns: Optional[Sequence[str]] = None) -> LabelTask:
    source = Path(path).expanduser()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not load task {}: {}".format(source, exc)) from exc
    return task_from_dict(raw, available_columns=available_columns)


def save_task(task: LabelTask, path: PathLike) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("Refusing to overwrite existing label task: {}".format(destination))
    destination.write_text(json.dumps(task_to_dict(task), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def validate_label(task: LabelTask, label: str) -> str:
    if label not in task.labels:
        raise ValueError("Label {!r} is not configured for task {!r}.".format(label, task.task_id))
    return label
