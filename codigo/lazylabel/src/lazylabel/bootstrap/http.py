"""Compose HTTP delivery without importing optional FastAPI until requested."""
from pathlib import Path
from lazylabel.bootstrap.application import build_application
from lazylabel.adapters.inbound.http.app import create_app as http_app


def create_app(project_path, backend_factory=None, *, host="127.0.0.1", port=8765, application=None):
    services = application if application is not None else build_application(project_path, backend_factory=backend_factory)
    return http_app(services, Path(__file__).resolve().parent.parent / "web", host=host, port=port)
