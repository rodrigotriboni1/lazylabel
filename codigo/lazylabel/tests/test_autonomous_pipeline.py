import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from lazylabel.adapters.outbound.persistence.policies import LabelingPolicy
from lazylabel.domain.labeling.prediction import Prediction, PredictionError
from lazylabel.adapters.outbound.models.labeling import run_labeling
from lazylabel.adapters.outbound.persistence.tasks import LabelTask
from lazylabel.adapters.outbound.sources.base import SourceSpec
from lazylabel.adapters.outbound.sources.csv_source import CsvSource


def _prediction(label="low", rationale="private rationale"):
    evidence = {"low": 0.8, "high": 0.2}
    evidence.setdefault(label, 0.1)
    return Prediction(
        label=label,
        rationale=rationale,
        confidence_evidence=evidence,
        calibrated_confidence=None,
        calibration_ref=None,
        confidence_method="logits",
        raw_output_digest=hashlib.sha256(b"raw output").hexdigest(),
    )


class Backend:
    model_id = "local-model"
    revision = "rev1"

    def __init__(self, response=None, on_predict=None):
        self.response = response or _prediction()
        self.on_predict = on_predict
        self.calls = []

    def predict(self, values, *, task, max_new_tokens):
        self.calls.append(dict(values))
        if self.on_predict:
            self.on_predict()
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class Calibrator:
    def __init__(self, **overrides):
        self.values = {
            "task_id": "risk",
            "policy_id": "risk-policy-v1",
            "model_ref": "local-model@rev1",
            "confidence_method": "logits",
            "calibration_ref": "cal-v1",
            "confidence": 0.91,
        }
        self.values.update(overrides)

    def calibrate(self, prediction, *, task, policy, model_ref):
        return type("CalibrationResult", (), self.values)()


def _policy():
    return LabelingPolicy(
        policy_id="risk-policy-v1",
        task_id="risk",
        allowed_labels=("low", "high"),
        rules_version="rules-v1",
        calibration_ref="cal-v1",
        min_calibrated_confidence=0.8,
        max_staleness_seconds=120,
        rules=({"field": "amount", "operator": "number_between", "minimum": 0},),
    )


class AutonomousPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source_path = self.root / "ledger.csv"
        self.source_path.write_text("amount,private\n10,ROW_SECRET\n", encoding="utf-8")
        self.source = CsvSource(SourceSpec("ledger", "csv", self.source_path))
        self.task = LabelTask("risk", "Classify risk", ("amount",), ("low", "high"), "local-model")
        self.workspace = self.root / ".lazylabel"

    def tearDown(self):
        self.temporary.cleanup()

    def _run(self, policy, backend, calibrator=None):
        return run_labeling(
            self.source,
            self.task,
            policy,
            backend,
            workspace_dir=self.workspace,
            calibrator=calibrator,
        )

    def _outcomes(self, run):
        return [json.loads(line) for line in run.outcomes_path.read_text(encoding="utf-8").splitlines()]

    def test_missing_policy_quarantines_without_calling_model(self):
        backend = Backend()

        run = self._run(None, backend)

        self.assertEqual(backend.calls, [])
        self.assertEqual(run.applied_count, 0)
        self.assertEqual(run.reason_counts, {"missing_policy": 1})

    def test_valid_calibrated_prediction_is_applied(self):
        run = self._run(_policy(), Backend(), Calibrator())

        outcome = self._outcomes(run)[0]
        self.assertEqual(outcome["state"], "applied")
        self.assertEqual(outcome["predicted_label"], "low")
        self.assertEqual(outcome["confidence"], 0.91)

    def test_missing_or_mismatched_calibrator_quarantines_prediction(self):
        for calibrator in (None, Calibrator(policy_id="other-policy"), Calibrator(calibration_ref="expired-ref")):
            with self.subTest(calibrator=calibrator):
                run = self._run(_policy(), Backend(), calibrator)
                outcome = self._outcomes(run)[0]
                self.assertEqual(outcome["state"], "quarantined")
                self.assertEqual(outcome["reason_code"], "uncalibrated")

    def test_unknown_labels_and_rule_conflicts_are_quarantined(self):
        invalid_backend = Backend(_prediction("not-configured"))
        invalid = self._run(_policy(), invalid_backend, Calibrator())
        self.assertEqual(self._outcomes(invalid)[0]["reason_code"], "unknown_label")

        self.source_path.write_text("amount,private\n-5,ROW_SECRET\n", encoding="utf-8")
        self.source = CsvSource(SourceSpec("ledger", "csv", self.source_path))
        blocked_backend = Backend()
        blocked = self._run(_policy(), blocked_backend, Calibrator())
        self.assertEqual(blocked_backend.calls, [])
        self.assertEqual(self._outcomes(blocked)[0]["reason_code"], "rule_conflict")

    def test_record_changed_before_publish_is_quarantined_without_source_write(self):
        before = self.source_path.read_bytes()

        def mutate_source():
            self.source_path.write_text("amount,private\n11,ROW_SECRET\n", encoding="utf-8")

        run = self._run(_policy(), Backend(on_predict=mutate_source), Calibrator())

        outcome = self._outcomes(run)[0]
        self.assertEqual(outcome["state"], "quarantined")
        self.assertEqual(outcome["reason_code"], "stale_source")
        self.assertNotEqual(self.source_path.read_bytes(), before)
        self.assertTrue(json.loads(run.run_metadata_path.read_text())["source_rechecked_before_publish"])

    def test_persisted_outcomes_exclude_source_values_prompts_and_free_form_rationale(self):
        run = self._run(_policy(), Backend(_prediction(rationale="PROMPT_SECRET RATIONALE_SECRET")), Calibrator())

        artifact = run.outcomes_path.read_text(encoding="utf-8") + run.run_metadata_path.read_text(encoding="utf-8")
        for secret in ("ROW_SECRET", "PROMPT_SECRET", "RATIONALE_SECRET", '"amount"'):
            self.assertNotIn(secret, artifact)


if __name__ == "__main__":
    unittest.main()
