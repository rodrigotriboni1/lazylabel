"""Project lookup and read-only source profiling orchestration."""

from typing import Iterator, Sequence

from finlabel.application.ports.projects import ProjectDescriptor, ProjectLookup
from finlabel.application.ports.sources import ReadOnlySource, SourceReader, SourceRecord
from finlabel.application.use_cases.errors import (
    InvalidProjectMetadata,
    InvalidSourceMetadata,
    ProjectNotFound,
    SourceAccessError,
    SourceNotFound,
    SourceNotReadOnly,
)
from finlabel.domain.projects import ColumnProfile

__all__ = [
    "InvalidProjectMetadata",
    "ProjectNotFound",
    "SourceAccessError",
    "SourceNotFound",
    "get_project",
    "iter_project_records",
    "profile_project_source",
]


_PROFILE_TYPES = {"boolean", "integer", "number", "string", "unknown"}


def get_project(projects: ProjectLookup, project_reference: str) -> ProjectDescriptor:
    """Load and validate project metadata through the injected lookup port."""
    if not isinstance(project_reference, str) or not project_reference.strip():
        raise InvalidProjectMetadata("Project reference must be a non-empty string.")
    try:
        project = projects.get_project(project_reference)
    except (ProjectNotFound, InvalidProjectMetadata):
        raise
    except FileNotFoundError as exc:
        raise ProjectNotFound("Project was not found.") from exc
    except Exception as exc:
        raise InvalidProjectMetadata("Project metadata is malformed.") from exc
    return _validate_project(project, project_reference)


def profile_project_source(
    projects: ProjectLookup,
    sources: SourceReader,
    project_reference: str,
    source_name: str,
) -> Sequence[ColumnProfile]:
    """Return a structural profile without materializing or modifying source rows."""
    source = _resolve_source(projects, sources, project_reference, source_name)
    _require_read_only(source)
    try:
        columns = source.columns()
    except Exception as exc:
        raise SourceAccessError("Could not read source profile.") from exc
    return _validate_columns(columns)


def iter_project_records(
    projects: ProjectLookup,
    sources: SourceReader,
    project_reference: str,
    source_name: str,
    columns: Sequence[str],
    batch_size: int = 1000,
) -> Iterator[SourceRecord]:
    """Stream selected fields from a validated read-only source."""
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise InvalidSourceMetadata("Batch size must be a positive integer.")
    if not isinstance(columns, (tuple, list)) or any(
        not isinstance(name, str) or not name.strip() for name in columns
    ):
        raise InvalidSourceMetadata("Selected source columns must be non-empty strings.")
    if len(columns) != len(set(columns)):
        raise InvalidSourceMetadata("Selected source columns must be unique.")
    source = _resolve_source(projects, sources, project_reference, source_name)
    _require_read_only(source)
    try:
        profile = _validate_columns(source.columns())
    except InvalidSourceMetadata:
        raise
    except Exception as exc:
        raise SourceAccessError("Could not read source profile.") from exc
    available = {column.name for column in profile}
    if any(name not in available for name in columns):
        raise InvalidSourceMetadata("Selected source column does not exist.")
    try:
        records = source.iter_records(tuple(columns), batch_size=batch_size)
    except Exception as exc:
        raise SourceAccessError("Could not start source record iteration.") from exc
    return _validate_records(records, tuple(columns))


def _resolve_source(
    projects: ProjectLookup,
    sources: SourceReader,
    project_reference: str,
    source_name: str,
) -> ReadOnlySource:
    project = get_project(projects, project_reference)
    if not isinstance(source_name, str) or source_name not in project.source_names:
        raise SourceNotFound("Source was not found in the project.")
    try:
        return sources.open_source(project_reference, source_name)
    except KeyError as exc:
        raise SourceNotFound("Source was not found in the project.") from exc
    except Exception as exc:
        raise SourceAccessError("Could not open source.") from exc


def _require_read_only(source: ReadOnlySource) -> None:
    try:
        capabilities = source.capabilities()
    except Exception as exc:
        raise SourceAccessError("Could not inspect source capabilities.") from exc
    read_only = getattr(capabilities, "read_only", None)
    if not isinstance(read_only, bool):
        raise InvalidSourceMetadata("Source read-only capability is malformed.")
    if not read_only:
        raise SourceNotReadOnly("Source must provide read-only access.")


def _validate_project(project: ProjectDescriptor, requested_reference: str) -> ProjectDescriptor:
    try:
        reference = project.reference
        source_names = project.source_names
    except AttributeError as exc:
        raise InvalidProjectMetadata("Project lookup returned malformed metadata.") from exc
    if reference != requested_reference or not isinstance(source_names, (tuple, list)):
        raise InvalidProjectMetadata("Project lookup returned malformed metadata.")
    if any(not isinstance(name, str) or not name.strip() for name in source_names):
        raise InvalidProjectMetadata("Project source names must be non-empty strings.")
    if len(source_names) != len(set(source_names)):
        raise InvalidProjectMetadata("Project source names must be unique.")
    return ProjectDescriptor(reference, tuple(source_names))


def _validate_columns(columns: Sequence[ColumnProfile]) -> Sequence[ColumnProfile]:
    if not isinstance(columns, (tuple, list)):
        raise InvalidSourceMetadata("Source profile must be a sequence of columns.")
    names = []
    for column in columns:
        if not isinstance(column, ColumnProfile):
            raise InvalidSourceMetadata("Source profile contains an invalid column.")
        if not isinstance(column.name, str) or not column.name.strip():
            raise InvalidSourceMetadata("Source column names must be non-empty strings.")
        if not isinstance(column.inferred_type, str) or column.inferred_type not in _PROFILE_TYPES:
            raise InvalidSourceMetadata("Source column has an unsupported inferred type.")
        if any(
            isinstance(count, bool) or not isinstance(count, int) or count < 0
            for count in (column.missing_count, column.non_missing_count)
        ):
            raise InvalidSourceMetadata("Source column counts must be non-negative integers.")
        names.append(column.name)
    if len(names) != len(set(names)):
        raise InvalidSourceMetadata("Source profile contains duplicate column names.")
    return tuple(columns)


def _validate_records(records, columns: tuple[str, ...]) -> Iterator[SourceRecord]:
    selected = set(columns)
    try:
        for record in records:
            if not isinstance(record, SourceRecord):
                raise InvalidSourceMetadata("Source returned an invalid record.")
            if not isinstance(record.values, dict) and not hasattr(record.values, "keys"):
                raise InvalidSourceMetadata("Source record values must be a mapping.")
            if set(record.values.keys()) != selected:
                raise InvalidSourceMetadata("Source returned fields outside the requested projection.")
            if record.record_id is not None and (
                not isinstance(record.record_id, str) or not record.record_id
            ):
                raise InvalidSourceMetadata("Source record identity is malformed.")
            if not isinstance(record.input_digest, str) or not record.input_digest:
                raise InvalidSourceMetadata("Source record digest is malformed.")
            yield record
    except InvalidSourceMetadata:
        raise
    except Exception as exc:
        raise SourceAccessError("Source record iteration failed.") from exc
