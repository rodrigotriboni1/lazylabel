"""Local CSV inspection with bounded-memory type estimation."""

import csv
import math
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union


PathLike = Union[str, Path]
_TYPE_SAMPLE_LIMIT = 1000
_MISSING = {"", "null", "none"}


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    inferred_type: str
    missing_count: int
    non_missing_count: int


@dataclass(frozen=True)
class DatasetProfile:
    source_name: str
    row_count: int
    columns: List[ColumnProfile]
    target_name: Optional[str] = None
    target_counts: Optional[Dict[str, int]] = None

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON-serializable summary without source records."""
        result = asdict(self)
        return result


def inspect_csv(path: PathLike, target: Optional[str] = None) -> DatasetProfile:
    """Inspect a local UTF-8 CSV and return a summary, never row contents.

    Type inference uses at most the first 1,000 non-empty values per column.
    Counts of rows, missing values, and target classes cover the full file.
    Empty strings, `null`, and `none` (case-insensitive) count as missing.
    """
    source = Path(path).expanduser()
    if not source.is_file():
        raise FileNotFoundError("CSV file not found: {}".format(source))

    missing_counts: Counter = Counter()
    non_missing_counts: Counter = Counter()
    type_samples: Dict[str, List[str]] = {}
    target_counts: Counter = Counter()
    row_count = 0

    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            headers = reader.fieldnames
            if not headers:
                raise ValueError("CSV must contain a header row.")
            if any(name is None or not name.strip() for name in headers):
                raise ValueError("CSV contains an empty column name.")
            if len(headers) != len(set(headers)):
                raise ValueError("CSV contains duplicate column names.")
            if target is not None and target not in headers:
                raise ValueError("Target column {!r} is not in the CSV header.".format(target))

            type_samples = {name: [] for name in headers}
            for row in reader:
                row_count += 1
                if None in row:
                    raise ValueError("CSV row {} has more fields than the header.".format(row_count + 1))
                for name in headers:
                    value = row.get(name)
                    normalized = value.strip() if value is not None else ""
                    if normalized.lower() in _MISSING:
                        missing_counts[name] += 1
                        continue
                    non_missing_counts[name] += 1
                    if len(type_samples[name]) < _TYPE_SAMPLE_LIMIT:
                        type_samples[name].append(normalized)
                if target is not None:
                    value = row.get(target)
                    normalized = value.strip() if value is not None else ""
                    if normalized.lower() not in _MISSING:
                        target_counts[normalized] += 1
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded (UTF-8 with BOM is supported).") from exc
    except csv.Error as exc:
        raise ValueError("Malformed CSV: {}".format(exc)) from exc

    columns = [
        ColumnProfile(
            name=name,
            inferred_type=_infer_type(type_samples[name]),
            missing_count=missing_counts[name],
            non_missing_count=non_missing_counts[name],
        )
        for name in headers
    ]
    ordered_target_counts = dict(sorted(target_counts.items())) if target is not None else None
    return DatasetProfile(
        source_name=source.name,
        row_count=row_count,
        columns=columns,
        target_name=target,
        target_counts=ordered_target_counts,
    )


def _infer_type(values: List[str]) -> str:
    if not values:
        return "unknown"
    lowered = {value.lower() for value in values}
    if lowered.issubset({"true", "false", "yes", "no"}):
        return "boolean"
    if all(_is_integer(value) for value in values):
        return "integer"
    if all(_is_number(value) for value in values):
        return "number"
    return "string"


def _is_integer(value: str) -> bool:
    try:
        int(value)
        return True
    except ValueError:
        return False


def _is_number(value: str) -> bool:
    try:
        return math.isfinite(float(value))
    except ValueError:
        return False
