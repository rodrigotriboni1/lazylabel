from dataclasses import dataclass
from typing import Iterator, Sequence

import pytest

from finlabel.application.ports.projects import ProjectDescriptor
from finlabel.application.ports.sources import ReadOnlySource, SourceCapabilities, SourceRecord
from finlabel.application.use_cases.monitoring import (
    InvalidSourceMetadata,
    SourceNotReadOnly,
    capture_project_schema,
    monitor_project_source,
)
from finlabel.application.use_cases.projects import (
    InvalidProjectMetadata,
    ProjectNotFound,
    SourceNotFound,
    SourceAccessError,
    get_project,
    iter_project_records,
    profile_project_source,
)
from finlabel.domain.monitoring import QualityFinding, SchemaBaseline
from finlabel.domain.projects import ColumnProfile


@dataclass(frozen=True)
class FakeProject:
    reference: str
    source_names: Sequence[str]


class FakeProjects:
    def __init__(self, project=None, error=None):
        self.project = project or FakeProject("demo", ("ledger",))
        self.error = error
        self.lookups = []

    def get_project(self, reference: str) -> ProjectDescriptor:
        self.lookups.append(reference)
        if self.error:
            raise self.error
        return self.project


class FakeSource(ReadOnlySource):
    def __init__(self, columns, *, read_only=True, records=()):
        self._columns = columns
        self._read_only = read_only
        self._records = records
        self.columns_calls = 0
        self.iterated = []

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(read_only=self._read_only, streaming=True, selected_columns=True)

    def columns(self) -> Sequence[ColumnProfile]:
        self.columns_calls += 1
        return self._columns

    def iter_records(self, columns: Sequence[str], *, batch_size: int = 1000) -> Iterator[SourceRecord]:
        self.iterated.append((tuple(columns), batch_size))
        yield from self._records


class FakeSources:
    def __init__(self, source=None, error=None):
        self.source = source or FakeSource([ColumnProfile("amount", "number", 0, 3)])
        self.error = error
        self.opened = []

    def open_source(self, project_reference: str, source_name: str) -> ReadOnlySource:
        self.opened.append((project_reference, source_name))
        if self.error:
            raise self.error
        return self.source


def test_project_lookup_maps_missing_and_malformed_configuration_to_typed_errors():
    with pytest.raises(ProjectNotFound):
        get_project(FakeProjects(error=FileNotFoundError("missing")), "demo")

    with pytest.raises(InvalidProjectMetadata):
        get_project(FakeProjects(error=ValueError("bad config")), "demo")


def test_project_lookup_rejects_malformed_source_metadata():
    malformed = FakeProject("demo", ("ledger", "ledger"))

    with pytest.raises(InvalidProjectMetadata):
        get_project(FakeProjects(project=malformed), "demo")


def test_profile_reads_columns_from_injected_read_only_source():
    source = FakeSource([ColumnProfile("amount", "number", 1, 9)])
    projects, sources = FakeProjects(), FakeSources(source)

    result = profile_project_source(projects, sources, "demo", "ledger")

    assert result == (ColumnProfile("amount", "number", 1, 9),)
    assert projects.lookups == ["demo"]
    assert sources.opened == [("demo", "ledger")]
    assert source.columns_calls == 1
    assert source.iterated == []


def test_profile_maps_unknown_source_and_rejects_non_read_only_connector():
    with pytest.raises(SourceNotFound):
        profile_project_source(FakeProjects(), FakeSources(), "demo", "missing")

    unsafe_source = FakeSource([], read_only=False)
    with pytest.raises(SourceNotReadOnly):
        profile_project_source(FakeProjects(), FakeSources(unsafe_source), "demo", "ledger")
    assert unsafe_source.columns_calls == 0


def test_profile_maps_connector_failures_to_typed_source_error():
    with pytest.raises(SourceAccessError):
        profile_project_source(FakeProjects(), FakeSources(error=OSError("unavailable")), "demo", "ledger")

    failing_source = FakeSource([])
    failing_source.columns = lambda: (_ for _ in ()).throw(OSError("unavailable"))
    with pytest.raises(SourceAccessError):
        profile_project_source(FakeProjects(), FakeSources(failing_source), "demo", "ledger")


def test_profile_rejects_malformed_read_only_capability_metadata():
    source = FakeSource([])
    source.capabilities = lambda: SourceCapabilities(read_only="yes")

    with pytest.raises(InvalidSourceMetadata):
        profile_project_source(FakeProjects(), FakeSources(source), "demo", "ledger")


def test_record_iteration_is_read_only_streaming_and_column_scoped():
    source = FakeSource(
        [ColumnProfile("amount", "number", 0, 1), ColumnProfile("note", "string", 0, 1)],
        records=[SourceRecord("row-1", {"amount": 12.5}, "digest")],
    )

    records = list(iter_project_records(FakeProjects(), FakeSources(source), "demo", "ledger", ["amount"], 7))

    assert records == [SourceRecord("row-1", {"amount": 12.5}, "digest")]
    assert source.iterated == [(('amount',), 7)]


def test_record_iteration_rejects_unknown_columns_and_non_read_only_source():
    source = FakeSource([ColumnProfile("amount", "number", 0, 1)], read_only=False)

    with pytest.raises(SourceNotReadOnly):
        list(iter_project_records(FakeProjects(), FakeSources(source), "demo", "ledger", ["amount"]))
    assert source.iterated == []

    with pytest.raises(InvalidSourceMetadata):
        list(iter_project_records(FakeProjects(), FakeSources(), "demo", "ledger", ["missing"]))


@pytest.mark.parametrize(
    "columns",
    [
        [ColumnProfile("", "number", 0, 1)],
        [ColumnProfile("amount", "money", 0, 1)],
        [ColumnProfile("amount", "number", -1, 1)],
        [ColumnProfile("amount", "number", 0, -1)],
        [ColumnProfile("amount", "number", 0, 1), ColumnProfile("amount", "number", 0, 1)],
    ],
)
def test_profile_maps_malformed_source_metadata_to_typed_error(columns):
    with pytest.raises(InvalidSourceMetadata):
        profile_project_source(FakeProjects(), FakeSources(FakeSource(columns)), "demo", "ledger")


def test_monitoring_uses_domain_rules_after_read_only_profile():
    source = FakeSource([
        ColumnProfile("amount", "number", 2, 8),
        ColumnProfile("new_column", "string", 0, 4),
    ])
    baseline = SchemaBaseline(
        columns={"amount": "number"},
        required_columns=("amount",),
        max_missing_ratio={"amount": 0.1},
        allow_extra_columns=False,
    )

    result = monitor_project_source(FakeProjects(), FakeSources(source), "demo", "ledger", baseline)

    assert [finding.code for finding in result] == ["unexpected_column", "missing_ratio_exceeded"]
    assert all(isinstance(finding, QualityFinding) for finding in result)


def test_schema_capture_returns_domain_candidate_without_inferred_thresholds():
    source = FakeSource([ColumnProfile("amount", "number", 1, 9)])

    baseline = capture_project_schema(FakeProjects(), FakeSources(source), "demo", "ledger")

    assert baseline.columns == {"amount": "number"}
    assert baseline.required_columns == ("amount",)
    assert baseline.max_missing_ratio == {}
    assert baseline.allow_extra_columns is False


def test_monitoring_maps_bad_baseline_metadata_to_typed_error():
    source = FakeSource([ColumnProfile("amount", "number", 0, 1)])
    baseline = SchemaBaseline(
        columns={"amount": "number"},
        required_columns=("amount",),
        max_missing_ratio={"amount": 1.2},
        allow_extra_columns=False,
    )

    with pytest.raises(InvalidSourceMetadata):
        monitor_project_source(FakeProjects(), FakeSources(source), "demo", "ledger", baseline)
