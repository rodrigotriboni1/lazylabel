"""Canonical identity for every task field that can affect its inference contract."""

import hashlib
import json


def task_spec_payload(task):
    return {
        "task_id": task.task_id,
        "instructions": task.instructions,
        "input_columns": list(task.input_columns),
        "labels": list(task.labels),
        "model_id": task.model_id,
        "model_revision": task.model_revision,
    }


def task_spec_sha256(task) -> str:
    encoded = json.dumps(task_spec_payload(task), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
