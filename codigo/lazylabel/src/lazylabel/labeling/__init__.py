"""Configurable, local-first label suggestion workflows."""

from lazylabel.adapters.outbound.persistence.tasks import LabelTask, load_task, save_task, task_file_path

__all__ = ["LabelTask", "load_task", "save_task", "task_file_path"]
