"""Pure label-task values and validation."""

import re
from dataclasses import asdict, dataclass
from typing import Optional, Sequence

_TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

@dataclass(frozen=True)
class LabelTask:
    task_id: str
    instructions: str
    input_columns: Sequence[str]
    labels: Sequence[str]
    model_id: str
    model_revision: Optional[str] = None
    policy_path: Optional[str] = None

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

        if self.policy_path is not None and (
            not isinstance(self.policy_path, str) or not self.policy_path.strip()
        ):
            raise ValueError("policy_path must be a non-empty string when provided.")


def task_to_dict(task: LabelTask) -> dict:
    return asdict(task)


def task_from_dict(raw: dict, *, available_columns: Optional[Sequence[str]] = None) -> LabelTask:
    if not isinstance(raw, dict):
        raise ValueError("Task document must be a JSON object.")
    allowed = {"task_id", "instructions", "input_columns", "labels", "model_id", "model_revision", "policy_path"}
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


def validate_label(task: LabelTask, label: str) -> str:
    if label not in task.labels:
        raise ValueError("Label {!r} is not configured for task {!r}.".format(label, task.task_id))
    return label
