import json
import tempfile
import unittest
from pathlib import Path

from lazylabel.cli import _verified_label_run
from lazylabel.labeling.outcomes import LabelOutcome, write_label_run


def _outcome(run_id, *, state="applied", reason_code=None, label="low"):
    return LabelOutcome(
        run_id=run_id,
        record_ref="a" * 64,
        input_digest="b" * 64,
        task_id="risk",
        policy_id="policy-v1",
        model_ref="local-model@rev1",
        predicted_label=label,
        state=state,
        reason_code=reason_code,
        confidence=0.9 if state == "applied" else None,
        created_at="2026-10-25T12:00:00Z",
    )


class LabelOutcomeTests(unittest.TestCase):
    def test_outcome_rejects_free_form_quarantine_reason(self):
        with self.assertRaisesRegex(ValueError, "reason_code"):
            _outcome("1" * 32, state="quarantined", reason_code="row contained SECRET")

    def test_outcome_rejects_non_finite_confidence(self):
        outcome = _outcome("1" * 32)
        raw = outcome.to_dict()
        raw["confidence"] = float("nan")
        with self.assertRaisesRegex(ValueError, "confidence"):
            LabelOutcome(**raw)

    def test_summary_is_recomputed_from_immutable_outcomes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_id = "1" * 32
            run = write_label_run(
                root,
                run_id=run_id,
                task_id="risk",
                policy_id="policy-v1",
                model_ref="local-model@rev1",
                started_at="2026-10-25T12:00:00Z",
                outcomes=(
                    _outcome(run_id),
                    LabelOutcome(
                        run_id=run_id,
                        record_ref="c" * 64,
                        input_digest="d" * 64,
                        task_id="risk",
                        policy_id="policy-v1",
                        model_ref="local-model@rev1",
                        predicted_label=None,
                        state="quarantined",
                        reason_code="uncalibrated",
                        confidence=None,
                        created_at="2026-10-25T12:00:00Z",
                    ),
                ),
            )

            verified = _verified_label_run(root, run_id)

            self.assertEqual(verified["applied_count"], 1)
            self.assertEqual(verified["quarantined_count"], 1)
            self.assertEqual(verified["reason_counts"], {"uncalibrated": 1})
            metadata_path = run.run_metadata_path
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["applied_count"] = 99
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "aggregate metadata"):
                _verified_label_run(root, run_id)


if __name__ == "__main__":
    unittest.main()
