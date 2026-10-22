"""Deterministic, stratified partitions for trusted examples."""

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence


def _canonical_hash(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TrustedSplit:
    train: Sequence[object]
    calibration: Sequence[object]
    holdout: Sequence[object]
    manifest: Mapping[str, object]


def split_trusted_records(records, labels, *, seed=42, fractions=(0.7, 0.15, 0.15)) -> TrustedSplit:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("Split seed must be a non-negative integer.")
    if len(fractions) != 3 or any(not isinstance(x, (int, float)) or x <= 0 for x in fractions):
        raise ValueError("Split fractions must be three positive values.")
    if abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError("Train, calibration, and holdout fractions must sum to 1.")
    records = tuple(records)
    if not records:
        raise ValueError("Cannot split an empty trusted dataset.")
    if len({row.record_ref for row in records}) != len(records):
        raise ValueError("Cannot split trusted data with duplicate record IDs.")
    buckets = {label: [] for label in labels}
    for row in records:
        if row.label not in buckets:
            raise ValueError("Trusted record label is outside the configured taxonomy.")
        buckets[row.label].append(row)

    partitions = {"train": [], "calibration": [], "holdout": []}
    names = tuple(partitions)
    for label in labels:
        group = sorted(buckets[label], key=lambda row: hashlib.sha256(
            (str(seed) + "\0" + (row.split_key or row.record_ref)).encode("utf-8")).hexdigest())
        if len(group) < 7:
            raise ValueError("Every class needs at least 7 examples for train, calibration, and holdout coverage.")
        raw = [len(group) * fraction for fraction in fractions]
        sizes = [max(1, int(value)) for value in raw]
        while sum(sizes) > len(group):
            candidates = [i for i in range(3) if sizes[i] > 1]
            if not candidates:
                raise ValueError("Insufficient class coverage for three non-empty partitions.")
            index = max(candidates, key=lambda i: (sizes[i] - raw[i], -i))
            sizes[index] -= 1
        while sum(sizes) < len(group):
            index = max(range(3), key=lambda i: (raw[i] - int(raw[i]), -i))
            sizes[index] += 1
            raw[index] = int(raw[index])
        if sizes[1] < 3:
            transfer = 3 - sizes[1]
            if sizes[0] - transfer < 1:
                transfer = sizes[0] - 1
            sizes[0] -= transfer
            sizes[1] += transfer
        if sizes[1] < 3 or sizes[0] < 1 or sizes[2] < 1:
            raise ValueError("Insufficient class coverage for a 3-example calibration partition.")
        cursor = 0
        for name, size in zip(names, sizes):
            partitions[name].extend(group[cursor:cursor + size])
            cursor += size

    for values in partitions.values():
        values.sort(key=lambda row: row.split_key or row.record_ref)
    sets = {name: {row.record_ref for row in rows} for name, rows in partitions.items()}
    if sets["train"] & sets["calibration"] or sets["train"] & sets["holdout"] or sets["calibration"] & sets["holdout"]:
        raise ValueError("Trusted split contains record leakage between partitions.")
    summaries = {}
    for name, rows in partitions.items():
        summaries[name] = {
            "count": len(rows),
            "sha256": _canonical_hash([{"input_digest": row.input_digest, "label": row.label}
                                        for row in rows]),
            "label_counts": {label: sum(row.label == label for row in rows) for label in labels},
        }
    return TrustedSplit(partitions["train"], partitions["calibration"], partitions["holdout"], {
        "strategy": "stratified_hash_v1", "seed": seed, "fractions": list(fractions),
        "partitions": summaries,
    })
