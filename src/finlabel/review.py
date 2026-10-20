"""Local append-only log for human label-review decisions."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union
from uuid import uuid4


PathLike = Union[str, Path]
_SCHEMA_VERSION = 2
_SUPPORTED_SCHEMA_VERSIONS = {1, 2}


class ReviewAction(str, Enum):
    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ReviewDecision:
    event_id: str
    schema_version: int
    record_id: str
    suggested_label: str
    action: ReviewAction
    final_label: Optional[str]
    model_ref: Optional[str]
    created_at: str
    run_id: Optional[str] = None
    source_name: Optional[str] = None
    task_id: Optional[str] = None
    input_digest: Optional[str] = None
    suggestion_id: Optional[str] = None

    def to_dict(self) -> dict:
        result = asdict(self)
        result["action"] = self.action.value
        return result


class ReviewLog:
    """Append and read review events without storing source-row contents.

    The caller must provide an opaque record identifier. This log is intended
    for a single local writer; it does not coordinate concurrent processes.
    """

    def __init__(self, path: PathLike):
        self.path = Path(path).expanduser()

    def record(
        self,
        record_id: str,
        suggested_label: str,
        action: ReviewAction,
        final_label: Optional[str] = None,
        model_ref: Optional[str] = None,
        *,
        run_id: Optional[str] = None,
        source_name: Optional[str] = None,
        task_id: Optional[str] = None,
        input_digest: Optional[str] = None,
        suggestion_id: Optional[str] = None,
    ) -> ReviewDecision:
        """Validate and append one human review event to the local JSONL file."""
        event = ReviewDecision(
            event_id=str(uuid4()),
            schema_version=_SCHEMA_VERSION,
            record_id=record_id,
            suggested_label=suggested_label,
            action=action,
            final_label=final_label,
            model_ref=model_ref,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            run_id=run_id,
            source_name=source_name,
            task_id=task_id,
            input_digest=input_digest,
            suggestion_id=suggestion_id,
        )
        _validate(event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            raise OSError("Could not append review log at {}: {}".format(self.path, exc)) from exc
        return event

    def read(self) -> List[ReviewDecision]:
        """Read and validate all events; report malformed JSONL with line number."""
        if not self.path.exists():
            return []
        events: List[ReviewDecision] = []
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line)
                        event = ReviewDecision(
                            event_id=raw["event_id"],
                            schema_version=raw["schema_version"],
                            record_id=raw["record_id"],
                            suggested_label=raw["suggested_label"],
                            action=ReviewAction(raw["action"]),
                            final_label=raw.get("final_label"),
                            model_ref=raw.get("model_ref"),
                            created_at=raw["created_at"],
                            run_id=raw.get("run_id"),
                            source_name=raw.get("source_name"),
                            task_id=raw.get("task_id"),
                            input_digest=raw.get("input_digest"),
                            suggestion_id=raw.get("suggestion_id"),
                        )
                        _validate(event)
                    except (ValueError, KeyError, TypeError) as exc:
                        raise ValueError(
                            "Invalid review log entry at line {}: {}".format(line_number, exc)
                        ) from exc
                    events.append(event)
        except OSError as exc:
            raise OSError("Could not read review log at {}: {}".format(self.path, exc)) from exc
        return events


def _validate(event: ReviewDecision) -> None:
    if event.schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError("Unsupported review-log schema version.")
    for field_name, value in (("event_id", event.event_id), ("created_at", event.created_at)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("{} must be a non-empty string.".format(field_name))
    if event.schema_version == 1 and any((event.run_id, event.source_name, event.task_id, event.input_digest, event.suggestion_id)):
        raise ValueError("Schema-v1 review events cannot contain provenance fields.")
    for field_name, value in (
        ("run_id", event.run_id), ("source_name", event.source_name), ("task_id", event.task_id),
        ("input_digest", event.input_digest), ("suggestion_id", event.suggestion_id),
    ):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError("{} must be a non-empty string when provided.".format(field_name))
    for field_name, value in (("record_id", event.record_id), ("suggested_label", event.suggested_label)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("{} must be a non-empty string.".format(field_name))
    if not isinstance(event.action, ReviewAction):
        raise ValueError("action must be accepted, corrected, or rejected.")
    if event.action is ReviewAction.ACCEPTED and event.final_label != event.suggested_label:
        raise ValueError("An accepted suggestion must remain the final label.")
    if event.action is ReviewAction.CORRECTED:
        if not isinstance(event.final_label, str) or not event.final_label.strip():
            raise ValueError("A corrected suggestion requires a final label.")
        if event.final_label == event.suggested_label:
            raise ValueError("A corrected label must differ from the suggestion.")
    if event.action is ReviewAction.REJECTED and event.final_label is not None:
        raise ValueError("A rejected suggestion must not define a final label.")
    if event.model_ref is not None and not isinstance(event.model_ref, str):
        raise ValueError("model_ref must be a string when provided.")
