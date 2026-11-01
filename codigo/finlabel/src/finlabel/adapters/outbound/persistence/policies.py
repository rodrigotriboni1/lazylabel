"""Task-scoped configuration for autonomous labeling; not calibration evidence."""

import json
from pathlib import Path

from finlabel.domain.labeling.policy import LabelingPolicy, policy_from_dict
from finlabel.domain.labeling.task import LabelTask
from finlabel.adapters.outbound.persistence.tasks import PathLike


def load_policy(path: PathLike, *, task: LabelTask) -> LabelingPolicy:
    source = Path(path).expanduser()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not load labeling policy {}: {}".format(source, exc)) from exc
    return policy_from_dict(raw, task=task)
