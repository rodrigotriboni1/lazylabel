"""Deterministic synthetic sample project files for `finlabel quickstart`."""
import json

CSV_NAME = "finlabel-sample-synthetic.csv"
INPUT_COLUMNS = ("fake_amount", "fake_days_past_due", "fake_utilization")
LABELS = ("low", "medium", "high")


def _reference_label(days_past_due, utilization):
    score = days_past_due + utilization
    return LABELS[0] if score < 60 else LABELS[1] if score < 110 else LABELS[2]


def sample_files(model_id, model_revision):
    """Return file name -> text for the sample CSV, task and policy."""
    lines = [",".join(INPUT_COLUMNS + ("reference_label",))]
    for i in range(40):
        amount, days, utilization = 100 + (i * 37) % 900, (i * 7) % 60, (i * 13) % 100
        lines.append("{},{},{},{}".format(amount, days, utilization, _reference_label(days, utilization)))
    task = {
        "task_id": "sample",
        "instructions": "Classify risk for this synthetic, fake sample data as low, medium or high.",
        "input_columns": list(INPUT_COLUMNS),
        "labels": list(LABELS),
        "model_id": model_id,
        "model_revision": model_revision,
        "policy_path": "./policy.json",
    }
    policy = {
        "policy_id": "sample-policy-v1",
        "task_id": "sample",
        "allowed_labels": list(LABELS),
        "rules_version": "sample-rules-v1",
        "rules": [{"field": column, "operator": "number_between", "minimum": 0} for column in INPUT_COLUMNS],
        "calibration_ref": None,
        "min_calibrated_confidence": 0.95,
        "max_staleness_seconds": 300,
    }
    return {CSV_NAME: "\n".join(lines) + "\n",
            "task.json": json.dumps(task, indent=2) + "\n",
            "policy.json": json.dumps(policy, indent=2) + "\n"}
