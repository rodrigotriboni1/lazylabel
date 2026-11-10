"""Closed labeling rules and quarantine decisions."""

from decimal import Decimal, InvalidOperation
import math
from typing import Optional

from lazylabel.domain.labeling.policy import LabelingPolicy
from lazylabel.domain.labeling.prediction import Prediction
from lazylabel.domain.labeling.task import LabelTask


def _same_scalar(left, right) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        try:
            left_number = Decimal(str(left))
            right_number = Decimal(str(right))
            return left_number.is_finite() and right_number.is_finite() and left_number == right_number
        except (InvalidOperation, ValueError, TypeError):
            return False
    return type(left) is type(right) and left == right


def rules_match(rules, selected_values: dict) -> bool:
    """Evaluate only the supported declarative operators; unknown rules fail closed."""
    if not rules:
        return False
    for rule in rules:
        field = rule["field"]
        operator = rule["operator"]
        value = selected_values.get(field)
        if operator == "not_empty":
            valid = value is not None and (not isinstance(value, str) or bool(value.strip()))
        elif operator == "equals":
            valid = _same_scalar(value, rule["value"])
        elif operator == "one_of":
            valid = any(_same_scalar(value, allowed) for allowed in rule["values"])
        elif operator == "number_between":
            try:
                if isinstance(value, bool) or value is None:
                    raise InvalidOperation
                number = Decimal(str(value).strip())
                valid = number.is_finite()
                if "minimum" in rule:
                    valid = valid and number >= Decimal(str(rule["minimum"]))
                if "maximum" in rule:
                    valid = valid and number <= Decimal(str(rule["maximum"]))
            except (InvalidOperation, ValueError, TypeError):
                valid = False
        else:
            return False
        if not valid:
            return False
    return True


def choose_quarantine_reason(
    task: LabelTask, policy: LabelingPolicy, label: Optional[str],
    confidence: Optional[float], elapsed_seconds: float,
) -> Optional[str]:
    """Return a safe reason code or None for an eligible applied label."""
    if label is None:
        reason = "invalid_output"
    elif label not in task.labels:
        reason = "unknown_label"
    elif label not in policy.allowed_labels:
        reason = "rule_conflict"
    elif (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
          or not math.isfinite(confidence) or not 0 <= confidence <= 1):
        reason = "uncalibrated"
    elif confidence < policy.min_calibrated_confidence:
        reason = "below_threshold"
    else:
        reason = None
    return "stale_source" if elapsed_seconds > policy.max_staleness_seconds else reason


def validate_calibration(result: object, prediction: Prediction, task: LabelTask,
                         policy: LabelingPolicy, model_ref: str) -> Optional[float]:
    """Accept confidence only when all calibration provenance matches this run."""
    if (policy.calibration_ref is None or prediction.confidence_evidence is None
            or set(prediction.confidence_evidence) != set(task.labels)):
        return None
    try:
        confidence = result.confidence
        if (result.task_id != task.task_id or result.policy_id != policy.policy_id
                or result.model_ref != model_ref
                or result.confidence_method != prediction.confidence_method
                or result.calibration_ref != policy.calibration_ref
                or isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            return None
        return float(confidence)
    except Exception:
        return None
