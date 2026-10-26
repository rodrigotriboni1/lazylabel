"""Shared data-source contracts used by analysis and labeling workflows."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Mapping, Optional, Protocol, Sequence

from finlabel.domain.projects import ColumnProfile


@dataclass(frozen=True)
class SourceSpec:
    name: str
    kind: str
    path: Path
    table: Optional[str] = None
    id_column: Optional[str] = None
    schema: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectConfig:
    path: Path
    sources: Mapping[str, SourceSpec] = field(default_factory=dict)
    model_roles: Mapping[str, str] = field(default_factory=dict)
    workspace_dir: Optional[Path] = None
    supervision_sources: Mapping[str, Mapping[str, object]] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceCapabilities:
    stable_record_ids: bool
    read_only: bool
    streaming: bool
    selected_columns: bool


@dataclass(frozen=True)
class SourceRecord:
    record_id: Optional[str]
    values: Mapping[str, object]
    input_digest: str


class DataSource(Protocol):
    spec: SourceSpec

    def capabilities(self) -> SourceCapabilities: ...

    def columns(self) -> Sequence[ColumnProfile]: ...

    def iter_records(
        self, columns: Sequence[str], *, batch_size: int = 1000
    ) -> Iterator[SourceRecord]: ...

