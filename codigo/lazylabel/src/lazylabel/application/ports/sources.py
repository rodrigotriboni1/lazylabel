"""Read-only source contracts consumed by application use cases."""

from dataclasses import dataclass
from typing import Iterator, Mapping, Protocol, Sequence

from lazylabel.domain.projects import ColumnProfile


@dataclass(frozen=True)
class SourceCapabilities:
    stable_record_ids: bool = False
    read_only: bool = True
    streaming: bool = True
    selected_columns: bool = True


@dataclass(frozen=True)
class SourceRecord:
    record_id: str | None
    values: Mapping[str, object]
    input_digest: str


class ReadOnlySource(Protocol):
    """Source view exposes declared metadata and reads, with no mutation operation."""

    name: str
    kind: str
    schema: Mapping[str, str]

    def capabilities(self) -> SourceCapabilities: ...

    def columns(self) -> Sequence[ColumnProfile]: ...

    def iter_records(
        self, columns: Sequence[str], *, batch_size: int = 1000
    ) -> Iterator[SourceRecord]: ...


class SourceReader(Protocol):
    """Resolve a project's named source to a read-only source view."""

    def open_source(self, project_reference: str, source_name: str) -> ReadOnlySource: ...
