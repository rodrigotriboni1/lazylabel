"""Inbound inventories and every mutation remain protected by the shared middleware."""
import ast
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lazylabel.bootstrap.http import create_app

POST_ROUTES = (
    "/api/autonomy/run", "/api/schema/capture", "/api/schema/confirm", "/api/plan",
    "/api/analyze", "/api/ai/ui", "/api/label/start", "/api/label/review", "/api/dataset/prepare", "/api/train/submit",
)
GET_ROUTES = (
    "/", "/analysis", "/monitor", "/review", "/ask", "/labeling", "/training", "/api/health",
    "/api/sources", "/api/autonomy/overview", "/api/autonomy/runs/{run_id}", "/api/monitor",
    "/api/label/suggestions", "/api/train/jobs/{job_id}", "/analysis/{run_id}",
    "/api/analyses/{run_id}", "/analysis/{run_id}/chart",
)


def test_public_http_route_and_static_mount_inventory_is_unchanged():
    app = create_app("/unused", application=object())
    inventory = {(method, route.path) for route in app.routes for method in getattr(route, "methods", ())}
    assert inventory == {*(('POST', path) for path in POST_ROUTES), *(('GET', path) for path in GET_ROUTES)}
    assert [(route.path, route.name) for route in app.routes if not hasattr(route, "methods")] == [("/static", "static")]


@pytest.mark.parametrize("path", POST_ROUTES)
def test_every_mutation_keeps_csrf_origin_and_body_limit_checks_before_execution(path):
    # No application methods exist: a missing middleware check would call a route and fail this test.
    client = TestClient(create_app("/unused", application=object()), base_url="http://127.0.0.1:8765")
    home = client.get("/")
    token = client.cookies.get("lazylabel_csrf")
    assert token and "SameSite=strict" in home.headers["set-cookie"]
    assert client.post(path, json={}).status_code == 403
    headers = {"Origin": "http://evil.example:8765", "X-CSRF-Token": token}
    assert client.post(path, json={}, headers=headers).status_code == 403
    headers.update(Origin="http://127.0.0.1:8765", **{"Content-Length": "65537"})
    assert client.post(path, content=b"{}", headers=headers).status_code == 413


@pytest.mark.parametrize("path", ("/", "/training", "/static/app/assets/index.js", "/api/health"))
def test_host_check_protects_page_static_and_api_delivery(path):
    client = TestClient(create_app("/unused", application=object()), base_url="http://evil.example:8765")
    assert client.get(path).status_code == 400


def test_entrypoint_imports_do_not_load_optional_web_or_model_libraries():
    script = '''
import sys
import lazylabel.bootstrap.cli
import lazylabel.bootstrap.http
from lazylabel.bootstrap.application import build_application
build_application('/unused')
assert not {'fastapi', 'uvicorn', 'torch', 'transformers', 'peft', 'datasets', 'trl', 'plotly', 'jinja2'} & set(sys.modules)
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_inbound_adapters_do_not_import_or_construct_concrete_outbound_adapters():
    root = Path(__file__).resolve().parents[3] / "src" / "lazylabel" / "adapters" / "inbound"
    violations = []
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = ([node.module or ""] if isinstance(node, ast.ImportFrom) else
                     [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
            if any(name.startswith("lazylabel.adapters.outbound") or name.startswith("lazylabel.bootstrap") for name in names):
                violations.append((str(path), node.lineno))
    assert violations == []


@pytest.mark.parametrize("path, method, payload", (
    ("/api/sources", "sources", {"sources": [{"name": "x" * (1024 * 1024)}]}),
    ("/api/autonomy/overview", "overview", {"tasks": ["x" * (1024 * 1024)]}),
    ("/api/label/suggestions?run_id=" + "a" * 32, "suggestions", {"suggestions": ["x" * (1024 * 1024)]}),
))
def test_metadata_queries_keep_response_size_limits_with_overridden_use_cases(path, method, payload):
    application = SimpleNamespace(**{method: lambda *args: payload})
    client = TestClient(create_app("/unused", application=application), base_url="http://127.0.0.1:8765")
    response = client.get(path)
    assert response.status_code == 422
    assert "limit" in response.json()["error"]


def test_http_mutation_uses_application_override_and_preserves_json_shape():
    from lazylabel.adapters.inbound.http.app import get_application
    from lazylabel.domain.monitoring import SchemaBaseline
    app = create_app("/missing", application=object())
    app.dependency_overrides[get_application] = lambda: SimpleNamespace(
        capture_schema=lambda name: SchemaBaseline({name: "number"}, (name,), {}, False))
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    client.get("/")
    response = client.post("/api/schema/capture", json={"source": "injected"}, headers={
        "Origin": "http://127.0.0.1:8765", "X-CSRF-Token": client.cookies.get("lazylabel_csrf")})
    assert response.status_code == 200
    assert response.json() == {"candidate": {"columns": {"injected": "number"},
        "required_columns": ["injected"], "max_missing_ratio": {}, "allow_extra_columns": False}}


def test_missing_project_preserves_historical_error_mapping_and_validation_order(tmp_path):
    client = TestClient(create_app(tmp_path / "missing"), base_url="http://127.0.0.1:8765",
                        raise_server_exceptions=False)
    client.get("/")
    headers = {"X-CSRF-Token": client.cookies.get("lazylabel_csrf"), "Idempotency-Key": "missing"}
    assert client.get("/api/analyses/" + "a" * 32).status_code == 500
    response = client.post("/api/analyze", json={"source": "missing", "question": "total", "plan": {}}, headers=headers)
    assert response.status_code == 400
    assert "Project configuration not found" in response.json()["error"]
    assert client.post("/api/autonomy/run", json={"source": "missing", "task": "risk"}, headers=headers).status_code == 500
