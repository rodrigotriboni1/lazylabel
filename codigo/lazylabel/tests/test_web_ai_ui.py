import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from lazylabel.adapters.inbound.http.app import create_app
from lazylabel.bootstrap.application import build_application
from lazylabel.adapters.outbound.persistence.projects import init_project

WEB_ASSETS = Path(__file__).resolve().parent.parent / "src" / "lazylabel" / "web"


class FakeGenerator:
    def __init__(self):
        self.calls = []

    def generate(self, prompt, *, max_new_tokens, system=None):
        self.calls.append((prompt, system))
        return '{"op":"add","path":"/root","value":"main"}'


class AiUiRouteTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        init_project(root)
        self.generator = FakeGenerator()
        self.application = build_application(root)

    def tearDown(self):
        self.temporary.cleanup()

    def client(self, ui_generator):
        client = TestClient(create_app(self.application, WEB_ASSETS, ui_generator=ui_generator), base_url="http://127.0.0.1:8765")
        client.get("/")
        return client, client.cookies.get("lazylabel_csrf")

    def test_forwards_system_and_prompt_and_returns_text(self):
        client, token = self.client(lambda: self.generator)
        response = client.post("/api/ai/ui", json={"prompt": "rows"}, headers={"x-csrf-token": token})
        self.assertEqual(response.status_code, 200)
        self.assertIn('"/root"', response.json()["text"])
        self.assertEqual(self.generator.calls[0][0], "rows")
        self.assertEqual(self.generator.calls[0][1], (WEB_ASSETS / "ai_ui_system_prompt.txt").read_text(encoding="utf-8"))

    def test_rejects_missing_csrf_extra_fields_and_unconfigured_generator(self):
        client, token = self.client(lambda: self.generator)
        self.assertEqual(client.post("/api/ai/ui", json={"prompt": "p"}).status_code, 403)
        self.assertEqual(client.post("/api/ai/ui", json={"prompt": "p", "system": "override"},
                                     headers={"x-csrf-token": token}).status_code, 400)
        client, token = self.client(None)
        self.assertEqual(client.post("/api/ai/ui", json={"prompt": "p"},
                                     headers={"x-csrf-token": token}).status_code, 503)
        self.assertEqual(self.generator.calls, [])

    def test_ask_route_serves_the_panel(self):
        client, _ = self.client(None)
        self.assertEqual(client.get("/ask").status_code, 200)
