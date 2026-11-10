"""Read-only report of which labeling and training prerequisites a project has."""
from typing import Mapping, Protocol


class PrerequisiteChecks(Protocol):
    def statuses(self, task_id: str) -> Mapping[str, str]:
        """Map each check id to `present`, `missing` or (labeling policy only) `invalid`."""
