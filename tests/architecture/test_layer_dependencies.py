"""Import contracts for the staged clean architecture migration."""

import ast
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "finlabel"

# Existing modules are granted a temporary exception while their responsibilities
# are split. A new module under an old package path must be classified explicitly.
TRANSITIONAL_MODULES = {
    "finlabel", "finlabel.analysis", "finlabel.analysis.charts",
    "finlabel.analysis.engine", "finlabel.analysis.planner",
    "finlabel.analysis.schema", "finlabel.analysis.service", "finlabel.cli",
    "finlabel.labeling", "finlabel.labeling.outcomes",
    "finlabel.labeling.policy", "finlabel.labeling.prediction",
    "finlabel.labeling.service", "finlabel.labeling.suggestions",
    "finlabel.labeling.task", "finlabel.models",
    "finlabel.models.text_generation", "finlabel.monitor", "finlabel.profile",
    "finlabel.project", "finlabel.review", "finlabel.sources",
    "finlabel.sources.base", "finlabel.sources.csv_source",
    "finlabel.sources.sqlite_source", "finlabel.training",
    "finlabel.training.active_model", "finlabel.training.autopipeline",
    "finlabel.training.backend", "finlabel.training.dataset",
    "finlabel.training.evaluation", "finlabel.training.jobs",
    "finlabel.training.local_evaluator", "finlabel.training.quality",
    "finlabel.training.registry", "finlabel.training.split",
    "finlabel.training.task_spec", "finlabel.training.trusted_labels",
    "finlabel.web", "finlabel.web.app",
}

# Restricted layers may use only pure standard-library helpers. An allowlist
# avoids silently admitting a new filesystem, process, or network module.
PURE_STDLIB_ROOTS = {
    "abc", "collections", "copy", "dataclasses", "datetime", "decimal",
    "enum", "functools", "hashlib", "itertools", "json", "math",
    "numbers", "operator", "re", "statistics", "types", "typing",
}


def module_name(path: Path) -> str:
    parts = path.relative_to(PACKAGE_ROOT.parent).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imported_modules(source: str, importer: str, is_package: bool = False) -> set[str]:
    """Collect imports throughout an AST, resolving relative imports."""
    found = set()
    package = importer if is_package else importer.rpartition(".")[0]
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                prefix = package.split(".")[: -(node.level - 1) or None]
                base = ".".join((*prefix, *((node.module or "").split(".") if node.module else ())))
            else:
                base = node.module or ""
            if base:
                found.add(base)
    return found


def layer(module: str) -> str:
    if module in TRANSITIONAL_MODULES:
        return "transitional"
    for candidate in ("domain", "application", "adapters", "bootstrap"):
        if module == f"finlabel.{candidate}" or module.startswith(f"finlabel.{candidate}."):
            return candidate
    return "unclassified"


def forbidden_imports(importer: str, imports: set[str]) -> set[str]:
    current = layer(importer)
    if current == "transitional":
        return set()
    if current == "unclassified":
        return imports | {"<unclassified module>"}
    allowed_layers = {
        "domain": {"domain"},
        "application": {"application", "domain"},
        "adapters": {"adapters", "application", "domain"},
        "bootstrap": {"bootstrap", "adapters", "application", "domain"},
    }[current]
    forbidden = set()
    for imported in imports:
        if imported == "finlabel" or imported.startswith("finlabel."):
            if layer(imported) not in allowed_layers:
                forbidden.add(imported)
        elif current in {"domain", "application"}:
            root = imported.split(".")[0]
            if root not in PURE_STDLIB_ROOTS:
                forbidden.add(imported)
    return forbidden


def test_synthetic_forbidden_imports_are_reported():
    source = "from finlabel.adapters.outbound.sources import csv_source\nimport fastapi\n"
    imports = imported_modules(source, "finlabel.domain.analysis.rules")
    assert forbidden_imports("finlabel.domain.analysis.rules", imports) == {
        "finlabel.adapters.outbound.sources", "fastapi"
    }


def test_relative_and_nested_imports_are_collected():
    source = "from ..ports import sources\nif True:\n    import sqlite3\n"
    assert imported_modules(source, "finlabel.application.use_cases.projects") == {
        "finlabel.application.ports", "sqlite3"
    }


@pytest.mark.parametrize(
    "importer, imported, blocked",
    [
        ("finlabel.domain.analysis.rules", "finlabel.domain.labeling", False),
        ("finlabel.domain.analysis.rules", "finlabel.application.ports", True),
        ("finlabel.domain.analysis.rules", "pathlib", True),
        ("finlabel.domain.analysis.rules", "io", True),
        ("finlabel.domain.analysis.rules", "socket", True),
        ("finlabel.domain.analysis.rules", "http.client", True),
        ("finlabel.application.use_cases.analysis", "finlabel.domain.analysis", False),
        ("finlabel.application.use_cases.analysis", "finlabel.adapters.outbound", True),
        ("finlabel.application.use_cases.analysis", "sqlite3", True),
        ("finlabel.application.use_cases.analysis", "io", True),
        ("finlabel.application.use_cases.analysis", "socket", True),
        ("finlabel.application.use_cases.analysis", "http.client", True),
        ("finlabel.adapters.outbound.sources.csv_source", "finlabel.application.ports", False),
        ("finlabel.adapters.outbound.sources.csv_source", "finlabel.bootstrap", True),
        ("finlabel.bootstrap.cli", "finlabel.adapters.inbound.cli", False),
        ("finlabel.domain.analysis.rules", "finlabel.analysis.schema", True),
    ],
)
def test_layer_edges(importer: str, imported: str, blocked: bool):
    assert bool(forbidden_imports(importer, {imported})) is blocked


def test_every_python_module_has_an_allowed_dependency_direction():
    violations = {}
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        importer = module_name(path)
        blocked = forbidden_imports(
            importer, imported_modules(path.read_text(), importer, path.name == "__init__.py")
        )
        if blocked:
            violations[importer] = sorted(blocked)
    assert violations == {}
