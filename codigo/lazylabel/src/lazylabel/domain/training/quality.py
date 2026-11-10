"""Fail-closed integrity and class coverage checks for trusted training data."""

import hashlib
import json
import re


def validate_trusted_batch(batch, task):
    if not batch.provenance_id or not batch.source_name or batch.task_id != task.task_id:
        raise ValueError("Trusted dataset requires matching task and explicit source provenance.")
    if not batch.trust_kind:
        raise ValueError("Trusted dataset requires an explicit trust kind.")
    if re.search(r"(?:model|prediction|inference|suggestion|outcome|review[ _-]?log)",
                 "{} {}".format(batch.source_name, batch.provenance_id), re.IGNORECASE):
        raise ValueError("Model outputs, outcomes, and review logs cannot be trusted training sources.")
    if not re.fullmatch(r"[0-9a-f]{64}", batch.snapshot_sha256 or ""):
        raise ValueError("Trusted source snapshot digest is missing or malformed.")
    if not batch.records:
        raise ValueError("Trusted dataset contains no reference records.")
    seen = set()
    counts = {label: 0 for label in task.labels}
    for record in batch.records:
        if not isinstance(record.record_ref, str) or not record.record_ref.strip():
            raise ValueError("Trusted record is missing its provenance ID.")
        if record.record_ref in seen:
            raise ValueError("Trusted dataset contains duplicate record IDs.")
        seen.add(record.record_ref)
        if not re.fullmatch(r"[0-9a-f]{64}", record.input_digest or ""):
            raise ValueError("Trusted record has a missing or malformed input digest.")
        if record.label not in counts:
            raise ValueError("Trusted dataset contains a label outside the task taxonomy.")
        if set(record.features) != set(task.input_columns):
            raise ValueError("Trusted record features must exactly match task input columns.")
        encoded = json.dumps(dict(record.features), ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), default=str)
        if hashlib.sha256(encoded.encode("utf-8")).hexdigest() != record.input_digest:
            raise ValueError("Trusted record input digest is stale or inconsistent with its features.")
        counts[record.label] += 1
    missing = [label for label, count in counts.items() if count < 7]
    if missing:
        raise ValueError("Insufficient trusted class coverage (at least 7 per class required for train/calibration/holdout): {}".format(
            ", ".join(missing)))
    return counts
