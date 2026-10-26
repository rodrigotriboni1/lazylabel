"""Privacy-safe labeling outcome value."""

import math
import re
from dataclasses import asdict, dataclass
from typing import Optional

_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_REASON_CODES = {
    "invalid_output", "unknown_label", "rule_conflict", "uncalibrated",
    "below_threshold", "stale_source", "backend_error", "missing_policy",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class LabelOutcome:
    run_id: str
    record_ref: str
    input_digest: str
    task_id: str
    policy_id: Optional[str]
    model_ref: str
    predicted_label: Optional[str]
    state: str
    reason_code: Optional[str]
    confidence: Optional[float]
    created_at: str

    def __post_init__(self):
        if not isinstance(self.run_id, str) or not _RUN_ID.fullmatch(self.run_id):
            raise ValueError("run_id must be a 32-character lowercase hex identifier.")
        if not isinstance(self.record_ref, str) or not _DIGEST.fullmatch(self.record_ref):
            raise ValueError("record_ref must be a SHA-256 digest.")
        if not isinstance(self.input_digest, str) or not _DIGEST.fullmatch(self.input_digest):
            raise ValueError("input_digest must be a SHA-256 digest.")
        for name in ("task_id", "model_ref"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError("{} must be a non-empty string.".format(name))
        if self.policy_id is not None and (
            not isinstance(self.policy_id, str) or not self.policy_id.strip()
        ):
            raise ValueError("policy_id must be a non-empty string or null.")
        if self.predicted_label is not None and (
            not isinstance(self.predicted_label, str) or not self.predicted_label.strip()
        ):
            raise ValueError("predicted_label must be a non-empty string or null.")
        if self.state not in {"applied", "quarantined"}:
            raise ValueError("state must be 'applied' or 'quarantined'.")
        if self.state == "applied" and self.reason_code is not None:
            raise ValueError("Applied outcomes cannot have a quarantine reason.")
        if self.state == "quarantined" and self.reason_code not in _REASON_CODES:
            raise ValueError("Quarantined outcomes require a known reason_code.")
        if self.confidence is not None and (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("confidence must be finite and between 0 and 1 or null.")
        if not isinstance(self.created_at, str) or not self.created_at.endswith("Z"):
            raise ValueError("created_at must be an ISO-8601 UTC timestamp ending in Z.")

    def to_dict(self) -> dict:
        return asdict(self)
