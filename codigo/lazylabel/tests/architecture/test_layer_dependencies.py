"""Executable dependency rules for the complete Python package."""

import ast
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "lazylabel"

# The package root only carries metadata; the old facade modules were removed.
ROOT = "lazylabel"

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
                candidates = {f"{base}.{alias.name}" for alias in node.names}
                submodules = {name for name in candidates if name in PACKAGE_MODULES}
                found.update(submodules or {base})
                if len(submodules) != len(candidates):
                    found.add(base)
    return found


PACKAGE_MODULES = {module_name(path) for path in PACKAGE_ROOT.rglob("*.py")}


def layer(module: str) -> str:
    if module == ROOT:
        return "root"
    for candidate in ("domain", "application", "adapters", "bootstrap"):
        if module == f"lazylabel.{candidate}" or module.startswith(f"lazylabel.{candidate}."):
            return candidate
    return "unclassified"


def forbidden_imports(importer: str, imports: set[str]) -> set[str]:
    current = layer(importer)
    if current == "root":
        return set(imports)
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
        if imported == "lazylabel" or imported.startswith("lazylabel."):
            if layer(imported) not in allowed_layers:
                forbidden.add(imported)
        elif current in {"domain", "application"}:
            root = imported.split(".")[0]
            if root not in PURE_STDLIB_ROOTS:
                forbidden.add(imported)
    return forbidden


def test_synthetic_forbidden_imports_are_reported():
    source = "from lazylabel.adapters.outbound.sources import csv_source\nimport fastapi\n"
    imports = imported_modules(source, "lazylabel.domain.analysis.rules")
    assert forbidden_imports("lazylabel.domain.analysis.rules", imports) == {
        "lazylabel.adapters.outbound.sources.csv_source", "fastapi"
    }


def test_relative_and_nested_imports_are_collected():
    source = "from ..ports import sources\nif True:\n    import sqlite3\n"
    assert imported_modules(source, "lazylabel.application.use_cases.projects") == {
        "lazylabel.application.ports.sources", "sqlite3"
    }


@pytest.mark.parametrize(
    "importer, imported, blocked",
    [
        ("lazylabel.domain.analysis.rules", "lazylabel.domain.labeling", False),
        ("lazylabel.domain.analysis.rules", "lazylabel.application.ports", True),
        ("lazylabel.domain.analysis.rules", "pathlib", True),
        ("lazylabel.domain.analysis.rules", "io", True),
        ("lazylabel.domain.analysis.rules", "socket", True),
        ("lazylabel.domain.analysis.rules", "http.client", True),
        ("lazylabel.application.use_cases.analysis", "lazylabel.domain.analysis", False),
        ("lazylabel.application.use_cases.analysis", "lazylabel.adapters.outbound", True),
        ("lazylabel.application.use_cases.analysis", "sqlite3", True),
        ("lazylabel.application.use_cases.analysis", "io", True),
        ("lazylabel.application.use_cases.analysis", "socket", True),
        ("lazylabel.application.use_cases.analysis", "http.client", True),
        ("lazylabel.adapters.outbound.sources.csv_source", "lazylabel.application.ports", False),
        ("lazylabel.adapters.outbound.sources.csv_source", "lazylabel.bootstrap", True),
        ("lazylabel.bootstrap.cli", "lazylabel.adapters.inbound.cli", False),
        ("lazylabel.domain.analysis.rules", "lazylabel.analysis.schema", True),
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


def test_package_alias_cannot_hide_outward_dependency():
    imports = imported_modules("from lazylabel import cli", "lazylabel.domain.rules")
    assert forbidden_imports("lazylabel.domain.rules", imports) == {"lazylabel"}
