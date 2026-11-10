import hashlib
import json
import tempfile
import unittest

from lazylabel.adapters.outbound.sources.trusted_labels import TrustedLabelRecord
from lazylabel.domain.training.split import split_trusted_records
from lazylabel.adapters.outbound.persistence.datasets import prepare_trusted_dataset
from lazylabel.adapters.outbound.training.lifecycle import _manifest_for
from lazylabel.adapters.outbound.persistence.tasks import LabelTask
from lazylabel.adapters.outbound.sources.trusted_labels import TrustedLabelBatch


def _record(index, label, *, group=None):
    features = {"amount": group if group is not None else index}
    digest = hashlib.sha256(json.dumps(features, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    ref = hashlib.sha256(("ref-" + str(index)).encode()).hexdigest()
    return TrustedLabelRecord(ref, features, label, digest, hashlib.sha256(("split-" + str(index)).encode()).hexdigest())


class TrustedSplitTests(unittest.TestCase):
    def setUp(self):
        self.records = tuple(_record(i, "low" if i < 14 else "high") for i in range(28))

    def test_split_is_deterministic_disjoint_and_stratified(self):
        first = split_trusted_records(self.records, ("low", "high"), seed=81)
        second = split_trusted_records(tuple(reversed(self.records)), ("low", "high"), seed=81)
        for name in ("train", "calibration", "holdout"):
            left, right = getattr(first, name), getattr(second, name)
            self.assertEqual([r.record_ref for r in left], [r.record_ref for r in right])
            self.assertEqual(first.manifest["partitions"][name], second.manifest["partitions"][name])
        groups = [{row.record_ref for row in getattr(first, name)} for name in ("train", "calibration", "holdout")]
        self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
        for name in ("train", "calibration", "holdout"):
            self.assertEqual(set(first.manifest["partitions"][name]["label_counts"]), {"low", "high"})
            self.assertGreaterEqual(min(first.manifest["partitions"][name]["label_counts"].values()), 1)

    def test_identical_feature_groups_stay_in_one_partition_and_conflicting_labels_fail(self):
        records = [_record(i, "low" if i < 28 else "high", group=((i if i < 14 else i - 14) // 2))
                   for i in range(56)]
        split = split_trusted_records(records, ("low", "high"))
        placement = {}
        for name in ("train", "calibration", "holdout"):
            for row in getattr(split, name):
                placement[row.input_digest] = placement.get(row.input_digest, name)
                self.assertEqual(placement[row.input_digest], name)
        conflicting = records + [_record(100, "high", group=0)]
        with self.assertRaisesRegex(ValueError, "contradictory labels"):
            split_trusted_records(conflicting, ("low", "high"))

    def test_minimum_unique_group_count_and_duplicate_ids_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "at least 7 unique feature groups"):
            split_trusted_records(self.records[:6] + self.records[14:], ("low", "high"))
        with self.assertRaisesRegex(ValueError, "duplicate record IDs"):
            split_trusted_records(self.records + (self.records[0],), ("low", "high"))

    def test_frozen_partition_tampering_is_detected_on_reload(self):
        task = LabelTask("risk", "classify", ("amount",), ("low", "high"), "local/model")
        batch = TrustedLabelBatch("labels", "risk", "advisor-v1", "provided_ground_truth", ("amount",), "class",
                                  self.records, "a" * 64)
        with tempfile.TemporaryDirectory() as temporary:
            manifest = prepare_trusted_dataset(batch, task, workspace_dir=temporary)
            self.assertEqual(_manifest_for(batch, task, temporary).manifest_sha256, manifest.manifest_sha256)
            with (manifest.path / "holdout.jsonl").open("a", encoding="utf-8") as handle:
                handle.write('{"tampered":true}\n')
            with self.assertRaisesRegex(ValueError, "does_not_match_live_source:holdout"):
                _manifest_for(batch, task, temporary)


if __name__ == "__main__":
    unittest.main()
