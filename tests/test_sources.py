import csv
import importlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

class CsvSourceTests(unittest.TestCase):
    def setUp(self):
        try:
            self.project = importlib.import_module("finlabel.project")
            self.base = importlib.import_module("finlabel.sources.base")
            self.csv_source = importlib.import_module("finlabel.sources.csv_source")
        except ImportError:
            self.fail("Read-only CSV source adapter is not implemented")

    def test_streams_only_selected_fields_with_row_identity_and_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.csv"
            path.write_text("account,amount,note\nA,10,private\nB,20,secret\n", encoding="utf-8")
            source = self.csv_source.CsvSource(self.base.SourceSpec("ledger", "csv", path))

            records = list(source.iter_records(["amount"]))

            self.assertEqual([record.record_id for record in records], ["ledger:1", "ledger:2"])
            self.assertEqual([dict(record.values) for record in records], [{"amount": "10"}, {"amount": "20"}])
            self.assertNotIn("private", repr(records))
            self.assertTrue(source.capabilities().read_only)
            self.assertTrue(source.capabilities().streaming)

    def test_csv_rejects_duplicate_headers_and_malformed_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.csv"
            path.write_text("id,id\n1,2\n", encoding="utf-8")
            source = self.csv_source.CsvSource(self.base.SourceSpec("bad", "csv", path))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                source.columns()
            path.write_text("id,value\n1,2,3\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "more fields"):
                list(source.iter_records(["id"]))


class SqliteSourceTests(unittest.TestCase):
    def setUp(self):
        try:
            self.base = importlib.import_module("finlabel.sources.base")
            self.sqlite_source = importlib.import_module("finlabel.sources.sqlite_source")
        except ImportError:
            self.fail("Read-only SQLite source adapter is not implemented")

    def make_database(self, path):
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE ledger (id TEXT, amount TEXT, note TEXT)")
        connection.executemany(
            "INSERT INTO ledger VALUES (?, ?, ?)",
            [("a", "10.50", "private"), ("b", "20.00", "secret")],
        )
        connection.commit()
        connection.close()

    def test_reads_only_selected_fields_and_uses_unique_id_column(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.db"
            self.make_database(path)
            source = self.sqlite_source.SqliteSource(self.base.SourceSpec("ledger", "sqlite", path, table="ledger", id_column="id"))

            records = list(source.iter_records(["amount"]))

            self.assertEqual([record.record_id for record in records], ["a", "b"])
            self.assertEqual([dict(record.values) for record in records], [{"amount": "10.50"}, {"amount": "20.00"}])
            self.assertTrue(source.capabilities().stable_record_ids)
            with self.assertRaises(sqlite3.OperationalError):
                with source._connect() as connection:
                    connection.execute("DELETE FROM ledger")
            check = sqlite3.connect(path)
            self.assertEqual(check.execute("SELECT COUNT(*) FROM ledger").fetchone()[0], 2)
            check.close()

    def test_rejects_missing_table_bad_column_and_duplicate_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.db"
            self.make_database(path)
            missing = self.sqlite_source.SqliteSource(self.base.SourceSpec("missing", "sqlite", path, table="not_a_table"))
            with self.assertRaisesRegex(ValueError, "table"):
                missing.columns()
            source = self.sqlite_source.SqliteSource(self.base.SourceSpec("ledger", "sqlite", path, table="ledger", id_column="id"))
            with self.assertRaisesRegex(ValueError, "(?i)unknown SQLite column"):
                list(source.iter_records(["amount; DROP TABLE ledger"]))
            check = sqlite3.connect(path)
            check.execute("UPDATE ledger SET amount='10.50' WHERE id='b'")
            check.commit()
            check.close()
            duplicate = self.sqlite_source.SqliteSource(self.base.SourceSpec("ledger", "sqlite", path, table="ledger", id_column="amount"))
            with self.assertRaisesRegex(ValueError, "unique"):
                duplicate.capabilities()

    def test_sqlite_without_id_is_aggregate_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ledger.db"
            self.make_database(path)
            source = self.sqlite_source.SqliteSource(self.base.SourceSpec("ledger", "sqlite", path, table="ledger"))

            self.assertFalse(source.capabilities().stable_record_ids)
            self.assertTrue(all(row.record_id is None for row in source.iter_records(["amount"])))


class SourceCliTests(unittest.TestCase):
    def test_source_add_commands_store_csv_and_sqlite_sources(self):
        from finlabel.cli import main

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(main(["project", "init", str(root)]), 0)
            config_path = root / ".finlabel" / "project.json"
            csv_path = root / "ledger.csv"
            csv_path.write_text("id\na\n", encoding="utf-8")
            db_path = root / "ledger.db"
            connection = sqlite3.connect(db_path)
            connection.execute("CREATE TABLE ledger (id TEXT)")
            connection.commit()
            connection.close()

            self.assertEqual(main(["source", "add-csv", "csv-ledger", str(csv_path), "--project", str(root)]), 0)
            self.assertEqual(main(["source", "add-sqlite", "db-ledger", str(db_path), "--table", "ledger", "--project", str(root)]), 0)

            loaded = importlib.import_module("finlabel.project").load_project(config_path)
            self.assertEqual(loaded.sources["csv-ledger"].kind, "csv")
            self.assertEqual(loaded.sources["db-ledger"].table, "ledger")


if __name__ == "__main__":
    unittest.main()
