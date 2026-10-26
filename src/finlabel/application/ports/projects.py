"""Project lookup contracts and application-facing project metadata."""

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class ProjectDescriptor:
    """Minimal project metadata needed by use cases; contains no source rows."""

    reference: str
    source_names: Sequence[str]


class ProjectLookup(Protocol):
    """Look up a local project through an injected persistence adapter."""

    def get_project(self, reference: str) -> ProjectDescriptor: ...
