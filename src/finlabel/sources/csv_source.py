"""Streaming, read-only CSV source adapter."""

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterator, Sequence

from finlabel.profile import ColumnProfile, inspect_csv
from finlabel.sources.base import SourceCapabilities, SourceRecord, SourceSpec


def _digest(values):
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CsvSource:
    def __init__(self, spec: SourceSpec):
        if spec.kind != "csv":
            raise ValueError("CsvSource requires a csv SourceSpec.")
        self.spec = spec
        self.path = Path(spec.path).expanduser()

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(True, True, True, True)

    def columns(self) -> Sequence[ColumnProfile]:
        columns = inspect_csv(self.path).columns
        # Validate short rows too; DictReader represents absent cells as None.
        for _record in self.iter_records([column.name for column in columns]):
            pass
        return columns

    def iter_records(self, columns: Sequence[str], *, batch_size: int = 1000) -> Iterator[SourceRecord]:
        if batch_size < 1:
            raise ValueError("batch_size must be a positive integer.")
        if not self.path.is_file():
            raise FileNotFoundError("CSV file not found: {}".format(self.path))
        try:
            with self.path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, strict=True)
                headers = reader.fieldnames
                if not headers:
                    raise ValueError("CSV must contain a header row.")
                if any(name is None or not name.strip() for name in headers):
                    raise ValueError("CSV contains an empty column name.")
                if len(headers) != len(set(headers)):
                    raise ValueError("CSV contains duplicate column names.")
                unknown = [column for column in columns if column not in headers]
                if unknown:
                    raise ValueError("Unknown CSV column(s): {}".format(", ".join(unknown)))
                for row_number, row in enumerate(reader, start=1):
                    if None in row:
                        raise ValueError("CSV row {} has more fields than the header.".format(row_number + 1))
                    if any(row.get(name) is None for name in headers):
                        raise ValueError("CSV row {} has fewer fields than the header.".format(row_number + 1))
                    values = {name: row[name] for name in columns}
                    yield SourceRecord(
                        record_id="{}:{}".format(self.spec.name, row_number),
                        values=values,
                        input_digest=_digest(values),
                    )
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must be UTF-8 encoded (UTF-8 with BOM is supported).") from exc
        except csv.Error as exc:
            raise ValueError("Malformed CSV: {}".format(exc)) from exc

