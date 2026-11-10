import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from lazylabel.adapters.outbound.persistence.projects import init_project, load_project, save_project
from lazylabel.adapters.outbound.sources.base import ProjectConfig, SourceSpec
from lazylabel.adapters.outbound.sources.trusted_labels import TrustedLabelSourceSpec, load_trusted_labels, snapshot_manifest, supervision_key
from lazylabel.adapters.outbound.persistence.tasks import LabelTask


class TrustedLabelSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config_path = init_project(self.root)
        self.task = LabelTask("risk", "Classify risk", ("amount",), ("low", "high"), "local/model")

    def tearDown(self):
        self.temp.cleanup()

    def _config(self, spec, trusted_spec):
        return ProjectConfig(self.config_path, {spec.name: spec}, {}, self.config_path.parent,
                             {supervision_key("risk", spec.name): trusted_spec})

    def _registered(self, spec, mapping=None):
        trusted = TrustedLabelSourceSpec(spec.name, "risk", "class", mapping or {"L": "low", "H": "high"},
                                         "advisor-reviewed-v1", "provided_ground_truth")
        batch = load_trusted_labels(self._config(spec, {**trusted.to_dict()}), self.task)
        persisted = {**trusted.to_dict(), "snapshot_sha256": batch.snapshot_sha256, "row_count": batch.row_count}
        config = self._config(spec, persisted)
        save_project(config, self.config_path)
        return load_project(self.root), batch

    def test_csv_registration_reload_mapping_and_snapshot_drift(self):
        path = self.root / "labels.csv"
        path.write_text("amount,class,extra\n10,L,never-selected\n11,H,secret\n", encoding="utf-8")
        spec = SourceSpec("labels", "csv", path)
        project, original = self._registered(spec)
        reloaded = load_trusted_labels(project, self.task)
        self.assertEqual([r.label for r in reloaded.records], ["low", "high"])
        self.assertEqual(tuple(reloaded.feature_columns), ("amount",))
        self.assertNotIn("extra", reloaded.records[0].features)
        self.assertEqual(snapshot_manifest(reloaded)["row_count"], 2)
        path.write_text("amount,class,extra\n10,L,never-selected\n12,H,secret\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed since registration"):
            load_trusted_labels(project, self.task)

    def test_sqlite_registration_reload_and_duplicate_or_missing_ids_fail_closed(self):
        path = self.root / "labels.db"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE labels (id INTEGER, amount INTEGER, class TEXT)")
            db.executemany("INSERT INTO labels VALUES (?, ?, ?)", [(1, 10, "L"), (2, 20, "H")])
        spec = SourceSpec("labels", "sqlite", path, "labels", "id")
        project, _ = self._registered(spec)
        self.assertEqual([r.label for r in load_trusted_labels(project, self.task).records], ["low", "high"])
        for rows in ([(1, 10, "L"), (1, 20, "H")], [(None, 10, "L"), (2, 20, "H")]):
            with sqlite3.connect(path) as db:
                db.execute("DELETE FROM labels")
                db.executemany("INSERT INTO labels VALUES (?, ?, ?)", rows)
            with self.assertRaisesRegex(ValueError, "unique, non-null"):
                load_trusted_labels(project, self.task)

    def test_invalid_mapping_input_overlap_and_model_output_sources_are_rejected(self):
        path = self.root / "labels.csv"
        path.write_text("amount,class\n10,L\n", encoding="utf-8")
        spec = SourceSpec("labels", "csv", path)
        with self.assertRaisesRegex(ValueError, "outside the configured task taxonomy"):
            self._registered(spec, {"L": "not-a-task-label"})
        overlap = LabelTask("risk", "Classify risk", ("amount", "class"), ("low", "high"), "local/model")
        trusted = TrustedLabelSourceSpec("labels", "risk", "class", {"L": "low"}, "approved-v1", "provided_ground_truth")
        with self.assertRaisesRegex(ValueError, "must not appear"):
            load_trusted_labels(self._config(spec, {**trusted.to_dict()}), overlap)
        with self.assertRaisesRegex(ValueError, "cannot be trusted provenance"):
            TrustedLabelSourceSpec("predictions", "risk", "class", {"L": "low"}, "model-output-v1", "provided_ground_truth")

    def test_duplicate_or_missing_csv_record_identity_is_rejected_at_adapter_boundary(self):
        # CSV source IDs are physical row ordinals. Malformed row structure cannot create
        # a duplicate identity and instead fails parsing; stable IDs remain unique.
        path = self.root / "labels.csv"
        path.write_text("amount,class\n10,L\n10,L\n", encoding="utf-8")
        spec = SourceSpec("labels", "csv", path)
        trusted = TrustedLabelSourceSpec("labels", "risk", "class", {"L": "low"}, "approved-v1", "provided_ground_truth")
        batch = load_trusted_labels(self._config(spec, {**trusted.to_dict()}), self.task)
        self.assertEqual(len({row.record_ref for row in batch.records}), 2)
        path.write_text("amount,class\n10,L\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed since registration"):
            load_trusted_labels(self._config(spec, {**trusted.to_dict(), "snapshot_sha256": "0" * 64, "row_count": 2}), self.task)


if __name__ == "__main__":
    unittest.main()
