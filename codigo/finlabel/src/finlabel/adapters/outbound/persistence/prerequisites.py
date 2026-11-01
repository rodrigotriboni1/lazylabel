"""Existence-only prerequisite checks for one project; creates nothing and exposes no paths."""
import json
from pathlib import Path

from finlabel.adapters.outbound.persistence.tasks import load_task, load_task_policy, task_file_path


class FilePrerequisiteChecks:
    def __init__(self, config):
        self.config = config
        self.workspace_dir = Path(config.workspace_dir).expanduser()

    def statuses(self, task_id):
        models = self.workspace_dir / "models"
        return {
            "labeling_policy": self._labeling_policy(task_id),
            "trusted_label_source": self._present(any(
                key.startswith(task_id + "::") for key in self.config.supervision_sources)),
            "training_gate": self._present((self.workspace_dir / "training-gate.json").is_file()),
            "promotion_policy": self._present((models / "promotion-policies" / (task_id + ".json")).is_file()),
            "calibrator": self._present(self._has_calibrator(models / "active-models.json", task_id)),
        }

    @staticmethod
    def _present(found):
        return "present" if found else "missing"

    def _labeling_policy(self, task_id):
        try:
            task = load_task(task_file_path(self.workspace_dir, task_id))
            return self._present(load_task_policy(task) is not None)
        except (ValueError, OSError):
            return "invalid"

    @staticmethod
    def _has_calibrator(pointer, task_id):
        try:
            return Path(json.loads(pointer.read_text(encoding="utf-8"))[task_id]["calibrator_path"]).is_file()
        except (OSError, ValueError, KeyError, TypeError):
            return False
