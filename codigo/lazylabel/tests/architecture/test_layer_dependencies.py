"""Executable dependency rules for the complete Python package."""

import ast
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "lazylabel"

# Legacy public modules have explicit canonical destinations. They receive no
# permission to depend on one another or to contain implementation logic.
FACADE_TARGETS = {
    "lazylabel": {"lazylabel.domain.projects", "lazylabel.adapters.outbound.sources.profile",
        "lazylabel.adapters.outbound.persistence.projects", "lazylabel.adapters.outbound.persistence.reviews",
        "lazylabel.adapters.outbound.sources.base"},
    "lazylabel.analysis": {"lazylabel.adapters.outbound.sources.analysis", "lazylabel.adapters.outbound.models.analysis_planner",
        "lazylabel.domain.analysis.schema", "lazylabel.adapters.outbound.persistence.analysis_runs"},
    "lazylabel.analysis.engine": {"lazylabel.adapters.outbound.sources.analysis"},
    "lazylabel.analysis.schema": {"lazylabel.domain.analysis.schema"},
    "lazylabel.analysis.charts": {"lazylabel.adapters.outbound.persistence.charts"},
    "lazylabel.analysis.planner": {"lazylabel.adapters.outbound.models.analysis_planner"},
    "lazylabel.analysis.service": {"lazylabel.adapters.outbound.persistence.analysis_runs"},
    "lazylabel.cli": {"lazylabel.bootstrap.cli", "lazylabel.adapters.outbound.persistence.pipeline_runs"},
    "lazylabel.labeling": {"lazylabel.adapters.outbound.persistence.tasks"},
    "lazylabel.labeling.outcomes": {"lazylabel.adapters.outbound.persistence.label_runs"},
    "lazylabel.labeling.policy": {"lazylabel.adapters.outbound.persistence.policies"},
    "lazylabel.labeling.prediction": {"lazylabel.domain.labeling.prediction"},
    "lazylabel.labeling.service": {"lazylabel.adapters.outbound.models.labeling"},
    "lazylabel.labeling.suggestions": {"lazylabel.adapters.outbound.persistence.suggestions"},
    "lazylabel.labeling.task": {"lazylabel.adapters.outbound.persistence.tasks"},
    "lazylabel.models": {"lazylabel.adapters.outbound.models.text_generation"},
    "lazylabel.models.text_generation": {"lazylabel.adapters.outbound.models.text_generation"},
    "lazylabel.monitor": {"lazylabel.adapters.outbound.persistence.baselines"},
    "lazylabel.profile": {"lazylabel.adapters.outbound.sources.profile"},
    "lazylabel.project": {"lazylabel.adapters.outbound.persistence.projects"},
    "lazylabel.review": {"lazylabel.adapters.outbound.persistence.reviews"},
    "lazylabel.sources": set(),
    "lazylabel.sources.base": {"lazylabel.adapters.outbound.sources.base"},
    "lazylabel.sources.csv_source": {"lazylabel.adapters.outbound.sources.csv_source"},
    "lazylabel.sources.sqlite_source": {"lazylabel.adapters.outbound.sources.sqlite_source"},
    "lazylabel.training": set(),
    "lazylabel.training.active_model": {"lazylabel.adapters.outbound.models.active_model"},
    "lazylabel.training.autopipeline": {"lazylabel.adapters.outbound.training.lifecycle"},
    "lazylabel.training.backend": {"lazylabel.adapters.outbound.training.backend"},
    "lazylabel.training.dataset": {"lazylabel.adapters.outbound.persistence.datasets"},
    "lazylabel.training.evaluation": {"lazylabel.adapters.outbound.training.evaluation"},
    "lazylabel.training.jobs": {"lazylabel.adapters.outbound.training.jobs"},
    "lazylabel.training.local_evaluator": {"lazylabel.adapters.outbound.training.local_evaluator"},
    "lazylabel.training.quality": {"lazylabel.domain.training.quality"},
    "lazylabel.training.registry": {"lazylabel.adapters.outbound.persistence.registry"},
    "lazylabel.training.split": {"lazylabel.domain.training.split"},
    "lazylabel.training.task_spec": {"lazylabel.domain.training.task_spec"},
    "lazylabel.training.trusted_labels": {"lazylabel.adapters.outbound.sources.trusted_labels"},
    "lazylabel.web": set(),
    "lazylabel.web.app": {"lazylabel.bootstrap.http", "lazylabel.adapters.inbound.http.app",
        "lazylabel.adapters.outbound.persistence.workspace", "lazylabel.adapters.outbound.persistence.idempotency"},
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
                candidates = {f"{base}.{alias.name}" for alias in node.names}
                submodules = {name for name in candidates if name in PACKAGE_MODULES}
                found.update(submodules or {base})
                if len(submodules) != len(candidates):
                    found.add(base)
    return found


PACKAGE_MODULES = {module_name(path) for path in PACKAGE_ROOT.rglob("*.py")}


def facade_violations(source: str, importer: str) -> list[str]:
    """Only imports, literal export metadata, aliases and the CLI entrypoint."""
    violations = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1:
                target, value = node.targets[0], node.value
                if isinstance(target, ast.Name) and target.id in {"__all__", "__version__"}:
                    try:
                        ast.literal_eval(value)
                        continue
                    except (ValueError, TypeError):
                        pass
                # Preserve old module identity and monkeypatch behavior.
                if (ast.unparse(target) == "sys.modules[__name__]"
                        and isinstance(value, ast.Name) and value.id == "_implementation"):
                    continue
                if isinstance(target, ast.Name) and (isinstance(value, ast.Name) or (isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name))):
                    continue
        if (importer == "lazylabel.cli" and isinstance(node, ast.If)
                and ast.dump(node) == ast.dump(ast.parse(
                    'if __name__ == "__main__":\n    raise SystemExit(main())').body[0])):
            continue
        violations.append(type(node).__name__)
    return violations


def layer(module: str) -> str:
    if module in FACADE_TARGETS:
        return "facade"
    for candidate in ("domain", "application", "adapters", "bootstrap"):
        if module == f"lazylabel.{candidate}" or module.startswith(f"lazylabel.{candidate}."):
            return candidate
    return "unclassified"


def forbidden_imports(importer: str, imports: set[str]) -> set[str]:
    current = layer(importer)
    if current == "facade":
        return {target for target in imports
                if target != "sys" and target not in FACADE_TARGETS[importer]}
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
        if layer(importer) == "facade":
            blocked.update(f"<facade {kind}>" for kind in facade_violations(path.read_text(), importer))
        if blocked:
            violations[importer] = sorted(blocked)
    assert violations == {}


@pytest.mark.parametrize("importer, target", [
    ("lazylabel.profile", "lazylabel.profile"),
    ("lazylabel.profile", "pathlib"),
    ("lazylabel.profile", "lazylabel.adapters.outbound.persistence.projects"),
    ("lazylabel.domain.analysis.rules", "lazylabel.cli"),
    ("lazylabel.application.use_cases.analysis", "lazylabel.analysis.schema"),
    ("lazylabel.adapters.outbound.sources.csv_source", "lazylabel.profile"),
])
def test_facades_are_not_a_dependency_escape_hatch(importer, target):
    assert forbidden_imports(importer, {target}) == {target}


def test_package_alias_cannot_hide_outward_dependency():
    imports = imported_modules("from lazylabel import cli", "lazylabel.domain.rules")
    assert forbidden_imports("lazylabel.domain.rules", imports) == {"lazylabel.cli"}


@pytest.mark.parametrize("source", [
    "def run():\n    return 1",
    "class Data: pass",
    "from pathlib import Path\nresult = Path('data').read_text()",
    "for row in source: pass",
    "if True: print('business rule')",
])
def test_facades_cannot_accumulate_business_logic(source):
    assert facade_violations(source, "lazylabel.profile")


def test_facade_module_identity_alias_is_permitted():
    assert facade_violations(
        "import sys\nfrom lazylabel.adapters.outbound.sources import profile as _implementation\nsys.modules[__name__] = _implementation",
        "lazylabel.profile",
    ) == []
