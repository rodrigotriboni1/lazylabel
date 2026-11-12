"""Pure labeling policy values and matching rules."""

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional, Sequence

from lazylabel.domain.labeling.task import LabelTask

_RULE_OPERATORS = {"not_empty", "equals", "one_of", "number_between"}
_MISSING = object()


def _is_json_scalar(value) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _validate_rules(rules):
    if not isinstance(rules, (list, tuple)):
        raise ValueError("rules must be a list of deterministic rule objects.")
    normalized = []
    for index, raw in enumerate(rules):
        if not isinstance(raw, Mapping):
            raise ValueError("rules[{}] must be an object.".format(index))
        field = raw.get("field")
        operator = raw.get("operator")
        if not isinstance(field, str) or not field.strip():
            raise ValueError("rules[{}].field must be a non-empty string.".format(index))
        if not isinstance(operator, str) or operator not in _RULE_OPERATORS:
            raise ValueError("rules[{}].operator is unsupported.".format(index))
        if operator == "not_empty":
            expected = {"field", "operator"}
            normalized.append(MappingProxyType({"field": field, "operator": operator}))
        elif operator == "equals":
            expected = {"field", "operator", "value"}
            value = raw.get("value", _MISSING)
            if value is _MISSING or not _is_json_scalar(value):
                raise ValueError("rules[{}].value must be a JSON scalar.".format(index))
            normalized.append(MappingProxyType({"field": field, "operator": operator, "value": value}))
        elif operator == "one_of":
            expected = {"field", "operator", "values"}
            values = raw.get("values", _MISSING)
            if (not isinstance(values, (list, tuple)) or not values
                    or any(not _is_json_scalar(value) for value in values)):
                raise ValueError("rules[{}].values must be a non-empty list of JSON scalars.".format(index))
            normalized.append(MappingProxyType({
                "field": field, "operator": operator, "values": tuple(values),
            }))
        else:
            expected = {"field", "operator"}
            minimum = raw.get("minimum", _MISSING)
            maximum = raw.get("maximum", _MISSING)
            if minimum is _MISSING and maximum is _MISSING:
                raise ValueError("rules[{}].number_between requires minimum or maximum.".format(index))
            if minimum is not _MISSING:
                expected.add("minimum")
            if maximum is not _MISSING:
                expected.add("maximum")
            for name, value in (("minimum", minimum), ("maximum", maximum)):
                if value is not _MISSING and (
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise ValueError("rules[{}].{} must be a finite number.".format(index, name))
            if minimum is not _MISSING and maximum is not _MISSING and minimum > maximum:
                raise ValueError("rules[{}].minimum cannot exceed maximum.".format(index))
            normalized_rule = {"field": field, "operator": operator}
            if minimum is not _MISSING:
                normalized_rule["minimum"] = minimum
            if maximum is not _MISSING:
                normalized_rule["maximum"] = maximum
            normalized.append(MappingProxyType(normalized_rule))
        if set(raw) != expected:
            unknown = set(raw) - expected
            missing = expected - set(raw)
            details = []
            if missing:
                details.append("missing {}".format(", ".join(sorted(missing))))
            if unknown:
                details.append("unknown {}".format(", ".join(sorted(unknown))))
            raise ValueError("rules[{}] has {}.".format(index, " and ".join(details)))
    return tuple(normalized)


@dataclass(frozen=True)
class LabelingPolicy:
    policy_id: str
    task_id: str
    allowed_labels: Sequence[str]
    rules_version: str
    calibration_ref: Optional[str]
    min_calibrated_confidence: float
    max_staleness_seconds: int
    rules: Sequence[Mapping[str, object]] = ()
    # Optional per-label override; labels left out use min_calibrated_confidence (decisão 10).
    min_confidence_by_label: Optional[Mapping[str, float]] = None

    def __post_init__(self):
        for name in ("policy_id", "task_id", "rules_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("{} must be a non-empty string.".format(name))
        if not isinstance(self.allowed_labels, (tuple, list)) or not self.allowed_labels:
            raise ValueError("allowed_labels must be a non-empty list of labels.")
        if any(not isinstance(label, str) or not label.strip() for label in self.allowed_labels):
            raise ValueError("allowed_labels must contain non-empty strings.")
        if len(set(self.allowed_labels)) != len(self.allowed_labels):
            raise ValueError("allowed_labels must be unique.")
        object.__setattr__(self, "allowed_labels", tuple(self.allowed_labels))
        object.__setattr__(self, "rules", _validate_rules(self.rules))
        if self.calibration_ref is not None and (
            not isinstance(self.calibration_ref, str) or not self.calibration_ref.strip()
        ):
            raise ValueError("calibration_ref must be a non-empty string or null.")
        confidence = self.min_calibrated_confidence
        if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError("min_calibrated_confidence must be finite and between 0 and 1.")
        by_label = self.min_confidence_by_label
        if by_label is not None:
            if not isinstance(by_label, Mapping) or not by_label or set(by_label) - set(self.allowed_labels):
                raise ValueError("min_confidence_by_label must map allowed labels to thresholds.")
            for value in by_label.values():
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) or not 0 <= value <= 1):
                    raise ValueError("min_confidence_by_label values must be finite and between 0 and 1.")
            object.__setattr__(self, "min_confidence_by_label", dict(by_label))
        seconds = self.max_staleness_seconds
        if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
            raise ValueError("max_staleness_seconds must be a positive integer.")

    def threshold_for(self, label: str) -> float:
        return (self.min_confidence_by_label or {}).get(label, self.min_calibrated_confidence)

    def thresholds(self) -> dict:
        return {label: self.threshold_for(label) for label in self.allowed_labels}

    @property
    def has_calibration_configuration(self) -> bool:
        """A reference is configured; runtime must still validate its evidence."""
        return self.calibration_ref is not None


def validate_policy_for_task(policy: LabelingPolicy, task: LabelTask) -> LabelingPolicy:
    """Validate a loaded policy against the exact task taxonomy and selected data."""
    if policy.task_id != task.task_id:
        raise ValueError("Labeling policy task_id {!r} does not match task {!r}.".format(
            policy.task_id, task.task_id))
    if set(policy.allowed_labels) != set(task.labels):
        raise ValueError("Labeling policy allowed_labels must match task labels exactly.")
    missing_rule_fields = sorted({rule["field"] for rule in policy.rules} - set(task.input_columns))
    if missing_rule_fields:
        raise ValueError("Policy rules reference columns not selected by the task: {}".format(
            ", ".join(missing_rule_fields)))
    return policy


def policy_matches_task(policy: LabelingPolicy, task: LabelTask) -> bool:
    if not policy.rules:
        return False
    try:
        validate_policy_for_task(policy, task)
    except ValueError:
        return False
    return True


def policy_from_dict(raw: object, *, task: LabelTask) -> LabelingPolicy:
    if not isinstance(raw, dict):
        raise ValueError("Labeling policy document must be a JSON object.")
    fields = {"policy_id", "task_id", "allowed_labels", "rules_version", "rules", "calibration_ref",
              "min_calibrated_confidence", "max_staleness_seconds", "min_confidence_by_label"}
    unknown = set(raw) - fields
    if unknown:
        raise ValueError("Unknown labeling policy field(s): {}".format(", ".join(sorted(unknown))))
    if "rules" not in raw or not raw["rules"]:
        raise ValueError("Labeling policy requires a non-empty supported rules list.")
    try:
        policy = LabelingPolicy(**raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid labeling policy: {}".format(exc)) from exc
    return validate_policy_for_task(policy, task)
