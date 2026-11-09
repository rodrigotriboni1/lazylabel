"""Public entry points must honor injected application use cases."""
import io
import json
from contextlib import redirect_stdout
from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_cli_inspection_uses_injected_application_without_accessing_a_file():
    from lazylabel.cli import main
    calls = []
    def inspect(path, target=None):
        calls.append((path, target))
        return {"row_count": 7, "columns": []}
    application = SimpleNamespace(inspect=inspect)
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(["inspect", "/does-not-exist.csv", "--target", "risk"], application=application)
    assert code == 0
    assert json.loads(out.getvalue()) == {"row_count": 7, "columns": []}
    assert calls == [("/does-not-exist.csv", "risk")]


def test_http_dependency_override_replaces_application_without_a_real_project():
    from lazylabel.web.app import create_app
    from lazylabel.adapters.inbound.http.app import get_application
    app = create_app("/does-not-exist", application=object())
    app.dependency_overrides[get_application] = lambda: SimpleNamespace(
        health=lambda: {"status": "ok", "project": "injected", "sources": 9})
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "project": "injected", "sources": 9}


def test_bootstrap_analysis_accepts_overridden_run_store_and_runtime(tmp_path):
    from lazylabel.bootstrap.application import build_application
    from lazylabel.project import init_project, load_project, save_project
    from lazylabel.sources.base import SourceSpec
    from lazylabel.domain.analysis.schema import plan_from_dict
    init_project(tmp_path)
    path = tmp_path / "data.csv"
    path.write_text("amount\n12\n")
    config = load_project(tmp_path)
    config.sources["data"] = SourceSpec("data", "csv", path, schema={"amount": "decimal"})
    save_project(config, config.path)
    received = []
    class Store:
        def save_run(self, **payload):
            received.append(payload)
            return "injected-artifact"
    runtime = SimpleNamespace(new_id=lambda: "fixed", now=lambda: "fixed-time")
    application = build_application(tmp_path, analysis_store_factory=lambda **kw: Store(), runtime=runtime)
    plan = plan_from_dict({"version": 1, "metric": {"operation": "sum", "column": "amount"},
                           "dimensions": [], "time_axis": None, "filters": [], "chart": "bar"})
    assert application.analyze("data", "total", plan) == "injected-artifact"
    assert received[0]["run_id"] == "fixed"
    assert received[0]["result"].rows[0]["value"] == 12
    assert not list((tmp_path / ".lazylabel" / "analyses").iterdir())


def test_cli_explicit_plan_does_not_implicitly_use_configured_analytics_model(tmp_path):
    from lazylabel.cli import main
    from lazylabel.project import init_project, load_project, save_project
    from lazylabel.sources.base import SourceSpec
    init_project(tmp_path)
    csv = tmp_path / "data.csv"
    csv.write_text("amount\n12\n")
    config = load_project(tmp_path)
    config.sources["data"] = SourceSpec("data", "csv", csv, schema={"amount": "decimal"})
    config.model_roles["analytics"] = "must-never-load"
    save_project(config, config.path)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"version": 1, "metric": {"operation": "sum", "column": "amount"},
                               "dimensions": [], "time_axis": None, "filters": [], "chart": "bar"}))
    out = io.StringIO()
    with redirect_stdout(out):
        status = main(["analyze", "data", "--question", "total", "--plan", str(plan), "--project", str(tmp_path)])
    assert status == 0
    assert json.loads(out.getvalue())["highlights"] == []
