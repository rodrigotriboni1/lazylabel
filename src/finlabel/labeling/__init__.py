"""Configurable, local-first label suggestion workflows."""

from finlabel.labeling.task import LabelTask, load_task, save_task, task_file_path

__all__ = ["LabelTask", "load_task", "save_task", "task_file_path"]
