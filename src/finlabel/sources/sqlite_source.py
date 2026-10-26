"""Streaming SQLite adapter that opens databases in read-only mode."""

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterator, Sequence

from finlabel.domain.projects import ColumnProfile
from finlabel.sources.base import SourceCapabilities, SourceRecord, SourceSpec


def _quote(identifier: str) -> str:
    return '"{}"'.format(identifier.replace('"', '""'))


def _digest(values):
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SqliteSource:
    def __init__(self, spec: SourceSpec):
        if spec.kind != "sqlite":
            raise ValueError("SqliteSource requires a sqlite SourceSpec.")
        if not spec.table:
            raise ValueError("SQLite source requires a table name.")
        self.spec = spec
        self.path = Path(spec.path).expanduser()

    def _connect(self):
        if not self.path.is_file():
            raise FileNotFoundError("SQLite database not found: {}".format(self.path))
        uri = self.path.resolve().as_uri() + "?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True)
            connection.row_factory = sqlite3.Row
            return connection
        except sqlite3.Error as exc:
            raise ValueError("Could not open SQLite database {}: {}".format(self.path, exc)) from exc

    def _table_columns(self, connection):
        match = connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
            (self.spec.table,),
        ).fetchone()
        if match is None:
            raise ValueError("SQLite table or view {!r} was not found in {}".format(self.spec.table, self.path))
        rows = connection.execute("PRAGMA table_info({})".format(_quote(self.spec.table))).fetchall()
        if not rows:
            raise ValueError("SQLite table {!r} has no readable columns.".format(self.spec.table))
        return rows

    def _validate_id(self, connection, columns):
        if self.spec.id_column is None:
            return
        if self.spec.id_column not in {row["name"] for row in columns}:
            raise ValueError("Unknown SQLite identity column: {}".format(self.spec.id_column))
        identity = _quote(self.spec.id_column)
        table = _quote(self.spec.table)
        counts = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT {}), SUM(CASE WHEN {} IS NULL THEN 1 ELSE 0 END) FROM {}".format(
                identity, identity, table
            )
        ).fetchone()
        if counts[0] != counts[1] or (counts[2] or 0) > 0:
            raise ValueError("SQLite identity column {!r} must contain unique, non-null values.".format(self.spec.id_column))

    def capabilities(self) -> SourceCapabilities:
        with self._connect() as connection:
            columns = self._table_columns(connection)
            self._validate_id(connection, columns)
        return SourceCapabilities(self.spec.id_column is not None, True, True, True)

    def columns(self) -> Sequence[ColumnProfile]:
        with self._connect() as connection:
            rows = self._table_columns(connection)
            self._validate_id(connection, rows)
            count = connection.execute("SELECT COUNT(*) FROM {}".format(_quote(self.spec.table))).fetchone()[0]
            result = []
            for row in rows:
                name = row["name"]
                missing = connection.execute(
                    "SELECT COUNT(*) FROM {} WHERE {} IS NULL OR TRIM(CAST({} AS TEXT)) = ''".format(
                        _quote(self.spec.table), _quote(name), _quote(name)
                    )
                ).fetchone()[0]
                declared = (row["type"] or "").upper()
                if any(token in declared for token in ("INT",)):
                    inferred = "integer"
                elif any(token in declared for token in ("REAL", "FLOA", "DOUB", "NUM", "DEC")):
                    inferred = "number"
                elif "BOOL" in declared:
                    inferred = "boolean"
                else:
                    inferred = "string" if declared else "unknown"
                result.append(ColumnProfile(name, inferred, missing, count - missing))
            return result

    def iter_records(self, columns: Sequence[str], *, batch_size: int = 1000) -> Iterator[SourceRecord]:
        if batch_size < 1:
            raise ValueError("batch_size must be a positive integer.")
        with self._connect() as connection:
            available = self._table_columns(connection)
            available_names = {row["name"] for row in available}
            unknown = [name for name in columns if name not in available_names]
            if unknown:
                raise ValueError("Unknown SQLite column(s): {}".format(", ".join(unknown)))
            self._validate_id(connection, available)
            selected = list(dict.fromkeys(columns))
            identity = self.spec.id_column
            query_columns = list(selected)
            if identity and identity not in query_columns:
                query_columns.append(identity)
            select_sql = ", ".join(_quote(name) for name in query_columns) if query_columns else "1"
            query = "SELECT {} FROM {}".format(select_sql, _quote(self.spec.table))
            if identity:
                query += " ORDER BY {}".format(_quote(identity))
            cursor = connection.execute(query)
            row_number = 0
            while True:
                batch = cursor.fetchmany(batch_size)
                if not batch:
                    break
                for row in batch:
                    row_number += 1
                    values = {name: row[name] for name in selected}
                    record_id = str(row[identity]) if identity else None
                    yield SourceRecord(record_id, values, _digest(values))

