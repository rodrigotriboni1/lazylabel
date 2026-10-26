"""Snapshot of the public package-level import contracts before migration."""

import importlib

import pytest


PUBLIC_EXPORTS = {
    "finlabel": {
        "ColumnProfile", "DatasetProfile", "DataSource", "ProjectConfig",
        "ReviewAction", "ReviewDecision", "ReviewLog", "SourceCapabilities",
        "SourceRecord", "SourceSpec", "init_project", "inspect_csv",
        "load_project", "save_project",
    },
    "finlabel.analysis": {
        "AnalysisPlan", "AnalysisResult", "AnalysisRun",
        "AnalysisClarificationError", "FilterSpec", "HighlightRef", "MetricSpec",
        "TimeAxis", "plan_from_dict", "plan_analysis", "plan_highlights",
        "plan_to_dict", "analyze_source", "result_to_dict",
        "render_highlight", "run_analysis", "validate_analysis_plan",
    },
    "finlabel.labeling": {"LabelTask", "load_task", "save_task", "task_file_path"},
    "finlabel.models": {"TextGenerationBackend", "TransformersTextGenerationBackend"},
}


@pytest.mark.parametrize("package, expected", PUBLIC_EXPORTS.items())
def test_public_exports_resolve(package: str, expected: set[str]):
    module = importlib.import_module(package)
    assert set(module.__all__) == expected
    for name in expected:
        assert getattr(module, name) is not None


@pytest.mark.parametrize(
    "path, name",
    [
        ("finlabel.cli", "main"),
        ("finlabel.web.app", "create_app"),
        ("finlabel.analysis.schema", "AnalysisPlan"),
        ("finlabel.analysis.service", "analyze_source"),
        ("finlabel.labeling.task", "LabelTask"),
        ("finlabel.labeling.service", "suggest_labels"),
        ("finlabel.models.text_generation", "TransformersTextGenerationBackend"),
        ("finlabel.project", "load_project"),
    ],
)
def test_legacy_import_paths_resolve(path: str, name: str):
    assert getattr(importlib.import_module(path), name) is not None


# Module aliases preserve historical private helpers and monkeypatch identity as
# well as their public symbols, while code lives only at the canonical boundary.
MODULE_ALIASES = {
    "finlabel.profile": "finlabel.adapters.outbound.sources.profile",
    "finlabel.project": "finlabel.adapters.outbound.persistence.projects",
    "finlabel.review": "finlabel.adapters.outbound.persistence.reviews",
    "finlabel.monitor": "finlabel.adapters.outbound.persistence.baselines",
    "finlabel.sources.base": "finlabel.adapters.outbound.sources.base",
    "finlabel.sources.csv_source": "finlabel.adapters.outbound.sources.csv_source",
    "finlabel.sources.sqlite_source": "finlabel.adapters.outbound.sources.sqlite_source",
    "finlabel.analysis.charts": "finlabel.adapters.outbound.persistence.charts",
    "finlabel.analysis.planner": "finlabel.adapters.outbound.models.analysis_planner",
    "finlabel.analysis.service": "finlabel.adapters.outbound.persistence.analysis_runs",
    "finlabel.labeling.task": "finlabel.adapters.outbound.persistence.tasks",
    "finlabel.labeling.policy": "finlabel.adapters.outbound.persistence.policies",
    "finlabel.labeling.outcomes": "finlabel.adapters.outbound.persistence.label_runs",
    "finlabel.labeling.suggestions": "finlabel.adapters.outbound.persistence.suggestions",
    "finlabel.labeling.service": "finlabel.adapters.outbound.models.labeling",
    "finlabel.models.text_generation": "finlabel.adapters.outbound.models.text_generation",
    "finlabel.training.active_model": "finlabel.adapters.outbound.models.active_model",
    "finlabel.training.autopipeline": "finlabel.adapters.outbound.training.lifecycle",
    "finlabel.training.backend": "finlabel.adapters.outbound.training.backend",
    "finlabel.training.dataset": "finlabel.adapters.outbound.persistence.datasets",
    "finlabel.training.evaluation": "finlabel.adapters.outbound.training.evaluation",
    "finlabel.training.jobs": "finlabel.adapters.outbound.training.jobs",
    "finlabel.training.local_evaluator": "finlabel.adapters.outbound.training.local_evaluator",
    "finlabel.training.registry": "finlabel.adapters.outbound.persistence.registry",
    "finlabel.training.trusted_labels": "finlabel.adapters.outbound.sources.trusted_labels",
}


@pytest.mark.parametrize("legacy, canonical", MODULE_ALIASES.items())
def test_legacy_module_alias_preserves_implementation_identity(legacy, canonical):
    assert importlib.import_module(legacy) is importlib.import_module(canonical)


@pytest.mark.parametrize("legacy, canonical, names", [
    ("finlabel", "finlabel.domain.projects.profile", ("ColumnProfile", "DatasetProfile")),
    ("finlabel", "finlabel.adapters.outbound.sources.base", ("DataSource", "ProjectConfig", "SourceCapabilities", "SourceRecord", "SourceSpec")),
    ("finlabel", "finlabel.adapters.outbound.persistence.reviews", ("ReviewAction", "ReviewDecision", "ReviewLog")),
    ("finlabel", "finlabel.adapters.outbound.persistence.projects", ("init_project", "load_project", "save_project")),
    ("finlabel", "finlabel.adapters.outbound.sources.profile", ("inspect_csv",)),
    ("finlabel.analysis", "finlabel.domain.analysis.schema", ("AnalysisPlan", "AnalysisResult", "FilterSpec", "MetricSpec", "TimeAxis")),
    ("finlabel.analysis.schema", "finlabel.domain.analysis.schema", ("AnalysisPlan", "AnalysisResult", "FilterSpec", "MetricSpec", "TimeAxis", "plan_from_dict", "plan_to_dict", "validate_analysis_plan")),
    ("finlabel.analysis", "finlabel.application.use_cases.errors", ("AnalysisClarificationError",)),
    ("finlabel.labeling", "finlabel.domain.labeling.task", ("LabelTask",)),
    ("finlabel.labeling.prediction", "finlabel.domain.labeling.prediction", ("Prediction", "PredictionError")),
    ("finlabel.training.split", "finlabel.domain.training.split", ("TrustedSplit", "split_trusted_records")),
    ("finlabel.training.quality", "finlabel.domain.training.quality", ("validate_trusted_batch",)),
    ("finlabel.training.task_spec", "finlabel.domain.training.task_spec", ("task_spec_payload", "task_spec_sha256")),
    ("finlabel.analysis.engine", "finlabel.adapters.outbound.sources.analysis", ("run_analysis",)),
    ("finlabel.analysis", "finlabel.adapters.outbound.sources.analysis", ("run_analysis",)),
    ("finlabel.models", "finlabel.adapters.outbound.models.text_generation", ("TextGenerationBackend", "TransformersTextGenerationBackend")),
])
def test_exported_objects_are_the_canonical_objects(legacy, canonical, names):
    old = importlib.import_module(legacy)
    implementation = importlib.import_module(canonical)
    for name in names:
        assert getattr(old, name) is getattr(implementation, name), name


def test_entrypoints_delegate_by_identity_and_keep_console_target():
    from importlib.metadata import distribution
    from finlabel.cli import main
    from finlabel.bootstrap.cli import run
    from finlabel.web.app import create_app
    from finlabel.bootstrap.http import create_app as composed_app

    assert main is run
    assert create_app is composed_app
    entrypoint = next(item for item in distribution("finlabel-local").entry_points
        if item.group == "console_scripts" and item.name == "finlabel")
    assert entrypoint.value == "finlabel.cli:main"
    assert entrypoint.load() is main


@pytest.mark.parametrize("module, operation", [
    ("finlabel", ""),
    ("finlabel.cli", "module.main(['--help'])"),
    ("finlabel.models", ""),
    ("finlabel.models.text_generation", ""),
    ("finlabel.training.backend", ""),
    ("finlabel.analysis", ""),
    ("finlabel.web.app", ""),
    ("finlabel.bootstrap.cli", ""),
    ("finlabel.bootstrap.http", ""),
    ("finlabel.bootstrap.application", "module.build_application('uninitialized-project')"),
])
def test_imports_and_uninitialized_composition_do_not_load_optional_extras(module, operation):
    """A new interpreter prevents an earlier test from hiding eager imports."""
    import subprocess
    import sys
    from pathlib import Path

    code = f'''
import importlib
import importlib.abc
import sys
optional = {{"torch", "transformers", "peft", "trl", "datasets", "fastapi", "plotly", "jinja2"}}
class NoOptionalImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in optional:
            raise AssertionError("Optional dependency imported eagerly: " + fullname)
sys.meta_path.insert(0, NoOptionalImports())
module = importlib.import_module({module!r})
try:
    {operation or 'pass'}
except SystemExit as exc:
    assert exc.code == 0
assert not optional.intersection(sys.modules)
print("optional imports stayed lazy")
'''
    result = subprocess.run([sys.executable, "-I", "-c", code],
        cwd=Path(__file__).resolve().parents[2], text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "optional imports stayed lazy" in result.stdout
