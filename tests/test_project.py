import json
import importlib
import tempfile
import unittest
from pathlib import Path


class ProjectContractTests(unittest.TestCase):
    def setUp(self):
        try:
            self.project = importlib.import_module("finlabel.project")
            self.source_base = importlib.import_module("finlabel.sources.base")
        except ImportError:
            self.fail("FinLabel project workspace and source contracts are not implemented")

    def test_init_creates_local_workspace_and_resolves_relative_source_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            csv_path = root / "records.csv"
            csv_path.write_text("account,amount\nA,12.50\n", encoding="utf-8")
            config_path = self.project.init_project(root)

            config = self.project.load_project(config_path)

            self.assertEqual(config.path, config_path.resolve())
            self.assertEqual(config.workspace_dir, (root / ".finlabel").resolve())
            self.assertEqual(config.sources, {})
            self.assertTrue((config.workspace_dir / "schemas").is_dir())
            self.assertTrue((config.workspace_dir / "analyses").is_dir())
            self.assertTrue(csv_path.exists())

    def test_project_round_trip_resolves_source_relative_to_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = self.project.init_project(root)
            source_path = root / "data" / "source.csv"
            source_path.parent.mkdir()
            source_path.write_text("id,value\n1,2\n", encoding="utf-8")
            config = self.project.load_project(config_path)
            config.sources["ledger"] = self.source_base.SourceSpec(
                name="ledger", kind="csv", path=Path("data/source.csv"),
                table=None, id_column=None, schema={"id": "string", "value": "decimal"}
            )

            self.project.save_project(config, config_path)
            loaded = self.project.load_project(config_path)

            self.assertEqual(loaded.sources["ledger"].path, source_path.resolve())
            self.assertEqual(loaded.model_roles, {})

    def test_unknown_source_kind_fails_with_config_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            config_path = Path(temporary) / "project.json"
            config_path.write_text(json.dumps({"sources": {"x": {"kind": "oracle"}}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, str(config_path)):
                self.project.load_project(config_path)

    def test_capabilities_describe_read_only_stream_and_stable_identity(self):
        capabilities = self.source_base.SourceCapabilities(True, True, True, True)

        self.assertTrue(capabilities.stable_record_ids)
        self.assertTrue(capabilities.read_only)
        self.assertTrue(capabilities.streaming)
        self.assertTrue(capabilities.selected_columns)

    def test_open_source_rejects_unknown_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.project.load_project(self.project.init_project(temporary))
            with self.assertRaisesRegex(KeyError, "missing"):
                self.project.open_source(config, "missing")


if __name__ == "__main__":
    unittest.main()
