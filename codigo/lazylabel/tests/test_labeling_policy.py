import json
import tempfile
import unittest
from pathlib import Path

from lazylabel.adapters.outbound.persistence.policies import LabelingPolicy, load_policy
from lazylabel.adapters.outbound.persistence.tasks import LabelTask


class LabelingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.task = LabelTask(
            "risk", "Classify risk", ("amount",), ("low", "high"), "local-model"
        )
        self.valid = {
            "policy_id": "risk-v1",
            "task_id": "risk",
            "allowed_labels": ["low", "high"],
            "rules_version": "1",
            "rules": [{"field": "amount", "operator": "number_between", "minimum": 0}],
            "calibration_ref": "calibration-1",
            "min_calibrated_confidence": 0.8,
            "max_staleness_seconds": 30,
        }

    def test_missing_policy_is_explicitly_absent_and_never_permissive(self):
        self.assertIsNone(self.task.policy_path)
        self.assertFalse(hasattr(self.task, "allowed_labels"))

    def test_loads_immutable_policy_and_matches_task(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text(json.dumps(self.valid), encoding="utf-8")

            policy = load_policy(path, task=self.task)

        self.assertIsInstance(policy, LabelingPolicy)
        self.assertEqual(policy.task_id, self.task.task_id)
        self.assertTrue(policy.has_calibration_configuration)
        self.assertEqual(tuple(policy.allowed_labels), ("low", "high"))
        with self.assertRaises((AttributeError, TypeError)):
            policy.policy_id = "changed"

    def test_rejects_task_mismatch_labels_and_unselected_rule_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            for key, value, message in (
                ("task_id", "other", "does not match"),
                ("allowed_labels", ["low"], "match task labels exactly"),
                ("rules", [{"field": "private", "operator": "not_empty"}], "not selected"),
            ):
                raw = dict(self.valid)
                raw[key] = value
                path.write_text(json.dumps(raw), encoding="utf-8")
                with self.subTest(key=key), self.assertRaisesRegex(ValueError, message):
                    load_policy(path, task=self.task)

    def test_missing_calibration_reference_is_not_calibration_configuration(self):
        raw = dict(self.valid)
        raw["calibration_ref"] = None
        policy = LabelingPolicy(**raw)
        self.assertFalse(policy.has_calibration_configuration)

    def test_rejects_invalid_threshold(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            raw = dict(self.valid)
            raw["min_calibrated_confidence"] = 1.2
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_policy(path, task=self.task)


if __name__ == "__main__":
    unittest.main()
