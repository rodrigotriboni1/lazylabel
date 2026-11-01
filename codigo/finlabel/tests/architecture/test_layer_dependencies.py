"""Executable dependency rules for the complete Python package."""

import ast
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "finlabel"

# Legacy public modules have explicit canonical destinations. They receive no
# permission to depend on one another or to contain implementation logic.
FACADE_TARGETS = {
    "finlabel": {"finlabel.domain.projects", "finlabel.adapters.outbound.sources.profile",
        "finlabel.adapters.outbound.persistence.projects", "finlabel.adapters.outbound.persistence.reviews",
        "finlabel.adapters.outbound.sources.base"},
    "finlabel.analysis": {"finlabel.adapters.outbound.sources.analysis", "finlabel.adapters.outbound.models.analysis_planner",
        "finlabel.domain.analysis.schema", "finlabel.adapters.outbound.persistence.analysis_runs"},
    "finlabel.analysis.engine": {"finlabel.adapters.outbound.sources.analysis"},
    "finlabel.analysis.schema": {"finlabel.domain.analysis.schema"},
    "finlabel.analysis.charts": {"finlabel.adapters.outbound.persistence.charts"},
    "finlabel.analysis.planner": {"finlabel.adapters.outbound.models.analysis_planner"},
    "finlabel.analysis.service": {"finlabel.adapters.outbound.persistence.analysis_runs"},
    "finlabel.cli": {"finlabel.bootstrap.cli", "finlabel.adapters.outbound.persistence.pipeline_runs"},
    "finlabel.labeling": {"finlabel.adapters.outbound.persistence.tasks"},
    "finlabel.labeling.outcomes": {"finlabel.adapters.outbound.persistence.label_runs"},
    "finlabel.labeling.policy": {"finlabel.adapters.outbound.persistence.policies"},
    "finlabel.labeling.prediction": {"finlabel.domain.labeling.prediction"},
    "finlabel.labeling.service": {"finlabel.adapters.outbound.models.labeling"},
    "finlabel.labeling.suggestions": {"finlabel.adapters.outbound.persistence.suggestions"},
    "finlabel.labeling.task": {"finlabel.adapters.outbound.persistence.tasks"},
    "finlabel.models": {"finlabel.adapters.outbound.models.text_generation"},
    "finlabel.models.text_generation": {"finlabel.adapters.outbound.models.text_generation"},
    "finlabel.monitor": {"finlabel.adapters.outbound.persistence.baselines"},
    "finlabel.profile": {"finlabel.adapters.outbound.sources.profile"},
    "finlabel.project": {"finlabel.adapters.outbound.persistence.projects"},
    "finlabel.review": {"finlabel.adapters.outbound.persistence.reviews"},
    "finlabel.sources": set(),
    "finlabel.sources.base": {"finlabel.adapters.outbound.sources.base"},
    "finlabel.sources.csv_source": {"finlabel.adapters.outbound.sources.csv_source"},
    "finlabel.sources.sqlite_source": {"finlabel.adapters.outbound.sources.sqlite_source"},
    "finlabel.training": set(),
    "finlabel.training.active_model": {"finlabel.adapters.outbound.models.active_model"},
    "finlabel.training.autopipeline": {"finlabel.adapters.outbound.training.lifecycle"},
    "finlabel.training.backend": {"finlabel.adapters.outbound.training.backend"},
    "finlabel.training.dataset": {"finlabel.adapters.outbound.persistence.datasets"},
    "finlabel.training.evaluation": {"finlabel.adapters.outbound.training.evaluation"},
    "finlabel.training.jobs": {"finlabel.adapters.outbound.training.jobs"},
    "finlabel.training.local_evaluator": {"finlabel.adapters.outbound.training.local_evaluator"},
    "finlabel.training.quality": {"finlabel.domain.training.quality"},
    "finlabel.training.registry": {"finlabel.adapters.outbound.persistence.registry"},
    "finlabel.training.split": {"finlabel.domain.training.split"},
    "finlabel.training.task_spec": {"finlabel.domain.training.task_spec"},
    "finlabel.training.trusted_labels": {"finlabel.adapters.outbound.sources.trusted_labels"},
    "finlabel.web": set(),
    "finlabel.web.app": {"finlabel.bootstrap.http", "finlabel.adapters.inbound.http.app",
        "finlabel.adapters.outbound.persistence.workspace", "finlabel.adapters.outbound.persistence.idempotency"},
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
        if (importer == "finlabel.cli" and isinstance(node, ast.If)
                and ast.dump(node) == ast.dump(ast.parse(
                    'if __name__ == "__main__":\n    raise SystemExit(main())').body[0])):
            continue
        violations.append(type(node).__name__)
    return violations


def layer(module: str) -> str:
    if module in FACADE_TARGETS:
        return "facade"
    for candidate in ("domain", "application", "adapters", "bootstrap"):
        if module == f"finlabel.{candidate}" or module.startswith(f"finlabel.{candidate}."):
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
        "finlabel.adapters.outbound.sources.csv_source", "fastapi"
    }


def test_relative_and_nested_imports_are_collected():
    source = "from ..ports import sources\nif True:\n    import sqlite3\n"
    assert imported_modules(source, "finlabel.application.use_cases.projects") == {
        "finlabel.application.ports.sources", "sqlite3"
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
        if layer(importer) == "facade":
            blocked.update(f"<facade {kind}>" for kind in facade_violations(path.read_text(), importer))
        if blocked:
            violations[importer] = sorted(blocked)
    assert violations == {}


@pytest.mark.parametrize("importer, target", [
    ("finlabel.profile", "finlabel.profile"),
    ("finlabel.profile", "pathlib"),
    ("finlabel.profile", "finlabel.adapters.outbound.persistence.projects"),
    ("finlabel.domain.analysis.rules", "finlabel.cli"),
    ("finlabel.application.use_cases.analysis", "finlabel.analysis.schema"),
    ("finlabel.adapters.outbound.sources.csv_source", "finlabel.profile"),
])
def test_facades_are_not_a_dependency_escape_hatch(importer, target):
    assert forbidden_imports(importer, {target}) == {target}


def test_package_alias_cannot_hide_outward_dependency():
    imports = imported_modules("from finlabel import cli", "finlabel.domain.rules")
    assert forbidden_imports("finlabel.domain.rules", imports) == {"finlabel.cli"}


@pytest.mark.parametrize("source", [
    "def run():\n    return 1",
    "class Data: pass",
    "from pathlib import Path\nresult = Path('data').read_text()",
    "for row in source: pass",
    "if True: print('business rule')",
])
def test_facades_cannot_accumulate_business_logic(source):
    assert facade_violations(source, "finlabel.profile")


def test_facade_module_identity_alias_is_permitted():
    assert facade_violations(
        "import sys\nfrom finlabel.adapters.outbound.sources import profile as _implementation\nsys.modules[__name__] = _implementation",
        "finlabel.profile",
    ) == []
