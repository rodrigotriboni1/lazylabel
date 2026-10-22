"""Immutable model evidence; raw scores are never calibrated confidence."""

import math
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional


class PredictionError(ValueError):
    """A structured output could not be used; safe reason for quarantine."""

    def __init__(self, message: str, *, reason_code: str = "invalid_output"):
        super().__init__(message)
        self.reason_code = reason_code


def _finite_number(value) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


@dataclass(frozen=True)
class Prediction:
    label: Optional[str]
    rationale: Optional[str]
    confidence_evidence: Optional[Mapping[str, float]]
    calibrated_confidence: Optional[float]
    calibration_ref: Optional[str]
    confidence_method: Optional[str]
    raw_output_digest: str

    def __post_init__(self):
        if self.label is not None and (not isinstance(self.label, str) or not self.label.strip()):
            raise ValueError("Prediction label must be a non-empty string or null.")
        if self.rationale is not None and (
            not isinstance(self.rationale, str) or len(self.rationale) > 1000
        ):
            raise ValueError("Prediction rationale must be a string of at most 1000 characters.")
        if not isinstance(self.raw_output_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.raw_output_digest
        ):
            raise ValueError("raw_output_digest must be a SHA-256 hex digest.")
        for name in ("confidence_method", "calibration_ref"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError("{} must be a non-empty string or null.".format(name))
        evidence = self.confidence_evidence
        if evidence is not None:
            if not isinstance(evidence, Mapping) or not evidence:
                raise ValueError("confidence_evidence must be a non-empty mapping or null.")
            if any(not isinstance(label, str) or not label.strip() or not _finite_number(score)
                   for label, score in evidence.items()):
                raise ValueError("Raw label scores must have non-empty labels and finite numbers.")
            if self.confidence_method is None:
                raise ValueError("Raw label scores require a confidence_method.")
            if self.label is not None and self.label not in evidence:
                raise ValueError("Raw label scores must include the predicted label.")
            object.__setattr__(self, "confidence_evidence", MappingProxyType(dict(evidence)))
        confidence = self.calibrated_confidence
        if confidence is not None:
            if not _finite_number(confidence) or not 0 <= confidence <= 1:
                raise ValueError("calibrated_confidence must be finite and between 0 and 1.")
            if evidence is None or self.calibration_ref is None or self.label is None:
                raise ValueError("Calibrated confidence requires label, evidence and calibration reference.")
