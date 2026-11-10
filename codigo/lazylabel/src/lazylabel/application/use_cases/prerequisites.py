"""Ordered prerequisites checklist with a fixed fix hint for each unmet check."""
from lazylabel.application.ports.prerequisites import PrerequisiteChecks

_DOCS = " See docs/verified-training-cycle.md."
_FIXES = {
    ("labeling_policy", "missing"): "Set policy_path in .lazylabel/tasks/<task>.json to a labeling policy file.",
    ("labeling_policy", "invalid"): "The file referenced by policy_path does not load as a labeling policy for the task; fix it.",
    ("trusted_label_source", "missing"): (
        "Run: lazylabel supervision add <source> --task <task> --label-column <column> "
        "--provenance <name> --trust-kind provided_ground_truth|validated_rule"),
    ("training_gate", "missing"): "Create .lazylabel/training-gate.json.",
    ("promotion_policy", "missing"): "Create .lazylabel/models/promotion-policies/<task>.json.",
    ("calibrator", "missing"): (
        "There is no promoted model with a calibrator yet; the first promotion through lazylabel run writes it."),
}
CHECKS = ("labeling_policy", "trusted_label_source", "training_gate", "promotion_policy", "calibrator")


def prerequisites_checklist(task_id: str, checks: PrerequisiteChecks) -> list:
    statuses = checks.statuses(task_id)
    items = []
    for check in CHECKS:
        item = {"check": check, "status": statuses[check]}
        if item["status"] != "present":
            item["fix"] = _FIXES[(check, item["status"])] + _DOCS
        items.append(item)
    return items
