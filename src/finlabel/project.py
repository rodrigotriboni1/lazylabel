"""Project configuration and local workspace management."""

import json
from pathlib import Path
from typing import Union

from finlabel.sources.base import ProjectConfig, SourceSpec


PathLike = Union[str, Path]
_ARTIFACT_DIRS = ("schemas", "analyses", "runs", "label-runs", "tasks", "models", "training", "supervision")


def _config_path(path: PathLike) -> Path:
    candidate = Path(path).expanduser()
    if candidate.name == "project.json":
        return candidate.resolve()
    return (candidate / ".finlabel" / "project.json").resolve()


def init_project(path: PathLike) -> Path:
    """Create an empty project workspace without copying any source data."""
    config_path = _config_path(path)
    workspace = config_path.parent
    workspace.mkdir(parents=True, exist_ok=True)
    for directory in _ARTIFACT_DIRS:
        (workspace / directory).mkdir(exist_ok=True)
    if config_path.exists():
        raise FileExistsError("Project configuration already exists: {}".format(config_path))
    config_path.write_text(
        json.dumps({"version": 1, "sources": {}, "model_roles": {}, "supervision_sources": {}}, indent=2) + "\n",
        encoding="utf-8",
    )
    return config_path


def load_project(path: PathLike) -> ProjectConfig:
    config_path = _config_path(path)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError("Project configuration not found: {}".format(config_path)) from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not read project configuration {}: {}".format(config_path, exc)) from exc
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("Unsupported or malformed project configuration: {}".format(config_path))
    sources_raw = raw.get("sources", {})
    roles = raw.get("model_roles", {})
    supervision = raw.get("supervision_sources", {})
    if not isinstance(sources_raw, dict) or not isinstance(roles, dict) or not isinstance(supervision, dict):
        raise ValueError("Project sources, model_roles, and supervision_sources must be objects: {}".format(config_path))
    sources = {}
    for source_name, source_raw in sources_raw.items():
        if not isinstance(source_raw, dict):
            raise ValueError("Malformed source {!r} in {}".format(source_name, config_path))
        kind = source_raw.get("kind")
        if kind not in {"csv", "sqlite"}:
            raise ValueError("Unknown source kind {!r} in {}".format(kind, config_path))
        try:
            source_path = Path(source_raw["path"]).expanduser()
            if not source_path.is_absolute():
                source_path = (config_path.parent.parent / source_path).resolve()
            sources[source_name] = SourceSpec(
                name=source_name,
                kind=kind,
                path=source_path,
                table=source_raw.get("table"),
                id_column=source_raw.get("id_column"),
                schema=source_raw.get("schema", {}),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Malformed source {!r} in {}: {}".format(source_name, config_path, exc)) from exc
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in roles.items()):
        raise ValueError("Model role references must be strings in {}".format(config_path))
    return ProjectConfig(config_path, sources, roles, config_path.parent, supervision)


def save_project(config: ProjectConfig, path: PathLike) -> None:
    config_path = _config_path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "sources": {
            name: {
                "kind": spec.kind,
                "path": str(spec.path),
                "table": spec.table,
                "id_column": spec.id_column,
                "schema": dict(spec.schema),
            }
            for name, spec in sorted(config.sources.items())
        },
        "model_roles": dict(config.model_roles),
        "supervision_sources": {
            key: dict(value) for key, value in sorted(config.supervision_sources.items())
        },
    }
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def open_source(config: ProjectConfig, name: str):
    try:
        spec = config.sources[name]
    except KeyError as exc:
        raise KeyError("Unknown source: {}".format(name)) from exc
    if spec.kind == "csv":
        from finlabel.sources.csv_source import CsvSource

        return CsvSource(spec)
    if spec.kind == "sqlite":
        from finlabel.sources.sqlite_source import SqliteSource

        return SqliteSource(spec)
    raise ValueError("Unknown source kind: {}".format(spec.kind))

