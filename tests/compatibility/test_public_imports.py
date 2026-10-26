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
