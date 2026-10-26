"""Declarative label tasks with a small, validated JSON format."""

import json
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence, Union

from finlabel.domain.labeling.task import LabelTask, _TASK_ID, task_from_dict, task_to_dict, validate_label

if TYPE_CHECKING:
    from finlabel.domain.labeling.policy import LabelingPolicy


PathLike = Union[str, Path]


def task_file_path(workspace_dir: PathLike, task_id: str) -> Path:
    if not isinstance(task_id, str) or not _TASK_ID.fullmatch(task_id):
        raise ValueError("task_id must use 1-64 safe filename characters.")
    return Path(workspace_dir).expanduser() / "tasks" / (task_id + ".json")


def load_task(path: PathLike, *, available_columns: Optional[Sequence[str]] = None) -> LabelTask:
    source = Path(path).expanduser()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not load task {}: {}".format(source, exc)) from exc
    task = task_from_dict(raw, available_columns=available_columns)
    if task.policy_path is not None:
        policy_path = Path(task.policy_path).expanduser()
        if not policy_path.is_absolute():
            policy_path = source.resolve().parent / policy_path
        task = replace(task, policy_path=str(policy_path.resolve()))
        load_task_policy(task)
    return task


def load_task_policy(task: LabelTask) -> Optional["LabelingPolicy"]:
    """Return no policy when unconfigured; never invent permissive defaults."""
    if task.policy_path is None:
        return None
    from finlabel.adapters.outbound.persistence.policies import load_policy

    return load_policy(task.policy_path, task=task)


def save_task(task: LabelTask, path: PathLike) -> Path:
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("Refusing to overwrite existing label task: {}".format(destination))
    destination.write_text(json.dumps(task_to_dict(task), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination
