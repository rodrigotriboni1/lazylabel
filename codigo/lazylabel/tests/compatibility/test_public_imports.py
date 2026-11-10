"""Snapshot of the public package-level import contracts before migration."""

import importlib

import pytest


PUBLIC_EXPORTS = {
    "lazylabel": {
        "ColumnProfile", "DatasetProfile", "DataSource", "ProjectConfig",
        "ReviewAction", "ReviewDecision", "ReviewLog", "SourceCapabilities",
        "SourceRecord", "SourceSpec", "init_project", "inspect_csv",
        "load_project", "save_project",
    },
    "lazylabel.analysis": {
        "AnalysisPlan", "AnalysisResult", "AnalysisRun",
        "AnalysisClarificationError", "FilterSpec", "HighlightRef", "MetricSpec",
        "TimeAxis", "plan_from_dict", "plan_analysis", "plan_highlights",
        "plan_to_dict", "analyze_source", "result_to_dict",
        "render_highlight", "run_analysis", "validate_analysis_plan",
    },
    "lazylabel.labeling": {"LabelTask", "load_task", "save_task", "task_file_path"},
    "lazylabel.models": {"TextGenerationBackend", "TransformersTextGenerationBackend"},
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
        ("lazylabel.cli", "main"),
        ("lazylabel.web.app", "create_app"),
        ("lazylabel.analysis.schema", "AnalysisPlan"),
        ("lazylabel.analysis.service", "analyze_source"),
        ("lazylabel.labeling.task", "LabelTask"),
        ("lazylabel.labeling.service", "suggest_labels"),
        ("lazylabel.models.text_generation", "TransformersTextGenerationBackend"),
        ("lazylabel.project", "load_project"),
    ],
)
def test_legacy_import_paths_resolve(path: str, name: str):
    assert getattr(importlib.import_module(path), name) is not None


# Module aliases preserve historical private helpers and monkeypatch identity as
# well as their public symbols, while code lives only at the canonical boundary.
MODULE_ALIASES = {
    "lazylabel.profile": "lazylabel.adapters.outbound.sources.profile",
    "lazylabel.project": "lazylabel.adapters.outbound.persistence.projects",
    "lazylabel.review": "lazylabel.adapters.outbound.persistence.reviews",
    "lazylabel.monitor": "lazylabel.adapters.outbound.persistence.baselines",
    "lazylabel.sources.base": "lazylabel.adapters.outbound.sources.base",
    "lazylabel.sources.csv_source": "lazylabel.adapters.outbound.sources.csv_source",
    "lazylabel.sources.sqlite_source": "lazylabel.adapters.outbound.sources.sqlite_source",
    "lazylabel.analysis.charts": "lazylabel.adapters.outbound.persistence.charts",
    "lazylabel.analysis.planner": "lazylabel.adapters.outbound.models.analysis_planner",
    "lazylabel.analysis.service": "lazylabel.adapters.outbound.persistence.analysis_runs",
    "lazylabel.labeling.task": "lazylabel.adapters.outbound.persistence.tasks",
    "lazylabel.labeling.policy": "lazylabel.adapters.outbound.persistence.policies",
    "lazylabel.labeling.outcomes": "lazylabel.adapters.outbound.persistence.label_runs",
    "lazylabel.labeling.suggestions": "lazylabel.adapters.outbound.persistence.suggestions",
    "lazylabel.labeling.service": "lazylabel.adapters.outbound.models.labeling",
    "lazylabel.models.text_generation": "lazylabel.adapters.outbound.models.text_generation",
    "lazylabel.training.active_model": "lazylabel.adapters.outbound.models.active_model",
    "lazylabel.training.autopipeline": "lazylabel.adapters.outbound.training.lifecycle",
    "lazylabel.training.backend": "lazylabel.adapters.outbound.training.backend",
    "lazylabel.training.dataset": "lazylabel.adapters.outbound.persistence.datasets",
    "lazylabel.training.evaluation": "lazylabel.adapters.outbound.training.evaluation",
    "lazylabel.training.jobs": "lazylabel.adapters.outbound.training.jobs",
    "lazylabel.training.local_evaluator": "lazylabel.adapters.outbound.training.local_evaluator",
    "lazylabel.training.registry": "lazylabel.adapters.outbound.persistence.registry",
    "lazylabel.training.trusted_labels": "lazylabel.adapters.outbound.sources.trusted_labels",
}


@pytest.mark.parametrize("legacy, canonical", MODULE_ALIASES.items())
def test_legacy_module_alias_preserves_implementation_identity(legacy, canonical):
    assert importlib.import_module(legacy) is importlib.import_module(canonical)


@pytest.mark.parametrize("legacy, canonical, names", [
    ("lazylabel", "lazylabel.domain.projects.profile", ("ColumnProfile", "DatasetProfile")),
    ("lazylabel", "lazylabel.adapters.outbound.sources.base", ("DataSource", "ProjectConfig", "SourceCapabilities", "SourceRecord", "SourceSpec")),
    ("lazylabel", "lazylabel.adapters.outbound.persistence.reviews", ("ReviewAction", "ReviewDecision", "ReviewLog")),
    ("lazylabel", "lazylabel.adapters.outbound.persistence.projects", ("init_project", "load_project", "save_project")),
    ("lazylabel", "lazylabel.adapters.outbound.sources.profile", ("inspect_csv",)),
    ("lazylabel.analysis", "lazylabel.domain.analysis.schema", ("AnalysisPlan", "AnalysisResult", "FilterSpec", "MetricSpec", "TimeAxis")),
    ("lazylabel.analysis.schema", "lazylabel.domain.analysis.schema", ("AnalysisPlan", "AnalysisResult", "FilterSpec", "MetricSpec", "TimeAxis", "plan_from_dict", "plan_to_dict", "validate_analysis_plan")),
    ("lazylabel.analysis", "lazylabel.application.use_cases.errors", ("AnalysisClarificationError",)),
    ("lazylabel.labeling", "lazylabel.domain.labeling.task", ("LabelTask",)),
    ("lazylabel.labeling.prediction", "lazylabel.domain.labeling.prediction", ("Prediction", "PredictionError")),
    ("lazylabel.training.split", "lazylabel.domain.training.split", ("TrustedSplit", "split_trusted_records")),
    ("lazylabel.training.quality", "lazylabel.domain.training.quality", ("validate_trusted_batch",)),
    ("lazylabel.training.task_spec", "lazylabel.domain.training.task_spec", ("task_spec_payload", "task_spec_sha256")),
    ("lazylabel.analysis.engine", "lazylabel.adapters.outbound.sources.analysis", ("run_analysis",)),
    ("lazylabel.analysis", "lazylabel.adapters.outbound.sources.analysis", ("run_analysis",)),
    ("lazylabel.models", "lazylabel.adapters.outbound.models.text_generation", ("TextGenerationBackend", "TransformersTextGenerationBackend")),
])
def test_exported_objects_are_the_canonical_objects(legacy, canonical, names):
    old = importlib.import_module(legacy)
    implementation = importlib.import_module(canonical)
    for name in names:
        assert getattr(old, name) is getattr(implementation, name), name


def test_entrypoints_delegate_by_identity_and_keep_console_target():
    from importlib.metadata import distribution
    from lazylabel.cli import main
    from lazylabel.bootstrap.cli import run
    from lazylabel.web.app import create_app
    from lazylabel.bootstrap.http import create_app as composed_app

    assert main is run
    assert create_app is composed_app
    entrypoint = next(item for item in distribution("lazylabel").entry_points
        if item.group == "console_scripts" and item.name == "lazylabel")
    assert entrypoint.value == "lazylabel.cli:main"
    assert entrypoint.load() is main


@pytest.mark.parametrize("module, operation", [
    ("lazylabel", ""),
    ("lazylabel.cli", "module.main(['--help'])"),
    ("lazylabel.models", ""),
    ("lazylabel.models.text_generation", ""),
    ("lazylabel.training.backend", ""),
    ("lazylabel.analysis", ""),
    ("lazylabel.web.app", ""),
    ("lazylabel.bootstrap.cli", ""),
    ("lazylabel.bootstrap.http", ""),
    ("lazylabel.bootstrap.application", "module.build_application('uninitialized-project')"),
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
