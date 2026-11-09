import importlib
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from lazylabel.analysis.schema import AnalysisPlan, MetricSpec
from lazylabel.project import init_project, load_project, save_project
from lazylabel.sources.base import SourceSpec
from lazylabel.labeling.task import LabelTask, save_task
from lazylabel.review import ReviewLog


class QueueBackend:
    model_id = "test-local-model"

    def __init__(self, responses):
        self.responses = list(responses)

    def generate(self, prompt, *, max_new_tokens):
        self.prompts.append(prompt)
        return self.responses.pop(0)

    prompts = []


class WebPanelTests(unittest.TestCase):
    def setUp(self):
        try:
            self.web_app = importlib.import_module("lazylabel.web.app")
        except ImportError:
            self.fail("Local FastAPI panel and browser security controls are not implemented")
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        init_project(self.root)
        source_path = self.root / "sales.csv"
        source_path.write_text(
            "date,product,amount,private\n2025-01-01,A,10,SECRET_ROW_VALUE\n2025-02-01,A,15,SECRET_ROW_VALUE\n",
            encoding="utf-8",
        )
        config = load_project(self.root)
        config.sources["sales"] = SourceSpec(
            "sales", "csv", source_path,
            schema={"date": "date", "product": "string", "amount": "decimal", "private": "string"},
        )
        save_project(config, config.path)
        self.responses = [
            json.dumps({
                "version": 1,
                "metric": {"operation": "sum", "column": "amount"},
                "dimensions": ["product"],
                "time_axis": {"column": "date", "grain": "month"},
                "filters": [],
                "chart": "line",
            }),
            json.dumps({"highlights": [{"result_key": ["A", "2025-02"], "observation": "highest"}]}),
        ]
        self.backend = QueueBackend(self.responses)
        self.backend.prompts = []
        self.client = TestClient(
            self.web_app.create_app(self.root, backend_factory=lambda config: self.backend, host="127.0.0.1", port=8765),
            base_url="http://127.0.0.1:8765",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def csrf(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        return self.client.cookies.get("lazylabel_csrf")

    def test_home_serves_react_shell_without_source_metadata_or_rows(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/app/assets/index.js', response.text)
        self.assertNotIn("sales", response.text)
        self.assertNotIn("amount", response.text)
        self.assertNotIn("SECRET_ROW_VALUE", response.text)
        self.assertEqual(response.cookies.get("lazylabel_csrf") is not None, True)
        self.assertIn("SameSite=strict", response.headers.get("set-cookie", ""))

    def test_rejects_non_loopback_bind_and_does_not_embed_untrusted_source_names(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            self.web_app.create_app(self.root, backend_factory=lambda config: None, host="0.0.0.0", port=8765)
        config = load_project(self.root)
        malicious_name = "<script>alert(1)</script>"
        config.sources[malicious_name] = SourceSpec(malicious_name, "csv", self.root / "sales.csv")
        save_project(config, config.path)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<script>alert(1)</script>", response.text)
        self.assertNotIn("&lt;script&gt;", response.text)
        self.assertIn('/static/app/assets/index.js', response.text)

    def test_rejects_untrusted_host_origin_missing_csrf_and_oversized_body(self):
        token = self.csrf()
        invalid_host = TestClient(
            self.client.app, base_url="http://evil.example:8765"
        ).get("/")
        self.assertEqual(invalid_host.status_code, 400)

        mismatch_origin = self.client.post(
            "/api/schema/capture", json={"source": "sales"},
            headers={"Origin": "http://evil.example:8765", "X-CSRF-Token": token},
        )
        self.assertEqual(mismatch_origin.status_code, 403)
        missing_csrf = self.client.post(
            "/api/schema/capture", json={"source": "sales"},
            headers={"Origin": "http://127.0.0.1:8765"},
        )
        self.assertEqual(missing_csrf.status_code, 403)
        oversized = self.client.post(
            "/api/schema/capture", content=b"x", headers={
                "Origin": "http://127.0.0.1:8765", "X-CSRF-Token": token,
                "Content-Type": "application/json", "Content-Length": "65537",
            },
        )
        self.assertEqual(oversized.status_code, 413)

    def test_capture_requires_confirmation_then_panel_executes_and_displays_plan(self):
        token = self.csrf()
        headers = {"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": token}
        capture = self.client.post("/api/schema/capture", json={"source": "sales"}, headers=headers)

        self.assertEqual(capture.status_code, 200)
        candidate = capture.json()["candidate"]
        baseline_path = self.root / ".lazylabel" / "schemas" / "sales.json"
        self.assertFalse(baseline_path.exists())
        confirm = self.client.post(
            "/api/schema/confirm", json={"source": "sales", "baseline": candidate}, headers=headers,
        )
        self.assertEqual(confirm.status_code, 200)
        self.assertTrue(baseline_path.exists())
        self.assertEqual(self.client.get("/api/monitor", params={"source": "sales"}).json()["findings"], [])

        malformed = dict(candidate)
        malformed["required_columns"] = "amount"
        rejected = self.client.post(
            "/api/schema/confirm", json={"source": "sales", "baseline": malformed}, headers=headers,
        )
        self.assertEqual(rejected.status_code, 400)

        proposed = self.client.post(
            "/api/plan", json={"source": "sales", "question": "Monthly sales trend"}, headers=headers,
        )
        self.assertEqual(proposed.status_code, 200)
        plan = proposed.json()["plan"]
        self.assertEqual(plan["chart"], "line")
        self.assertNotIn("SECRET_ROW_VALUE", self.backend.prompts[0])

        executed = self.client.post(
            "/api/analyze", json={"source": "sales", "question": "Monthly sales trend", "plan": plan}, headers=headers,
        )
        self.assertEqual(executed.status_code, 200, executed.text)
        payload = executed.json()
        self.assertEqual(payload["valid_row_count"], 2)
        self.assertEqual(payload["rows"][1]["value"], "15")
        self.assertIn("15", payload["highlights"][0])
        page = self.client.get(payload["analysis_url"])
        self.assertEqual(page.status_code, 200)
        self.assertIn('/static/app/assets/index.js', page.text)
        saved = self.client.get(f"/api/analyses/{payload['run_id']}")
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["valid_row_count"], 2)
        self.assertEqual(saved.json()["rows"], payload["rows"])
        chart = self.client.get(payload["chart_url"])
        self.assertEqual(chart.status_code, 200)
        self.assertIn("sandbox allow-scripts", chart.headers.get("content-security-policy", ""))
        self.assertFalse(any((self.root / ".lazylabel" / "analyses").glob("*/source.csv")))

    def test_web_retires_per_record_label_review_endpoints(self):
        headers = {"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": self.csrf()}
        page = self.client.get("/labeling")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/static/app/assets/index.js", page.text)
        start = self.client.post("/api/label/start", json={"source": "sales", "task": "risk"}, headers=headers)
        self.assertEqual(start.status_code, 410, start.text)
        review = self.client.post("/api/label/review", json={"action": "accepted"}, headers=headers)
        self.assertEqual(review.status_code, 410, review.text)
        config = load_project(self.root)
        self.assertFalse((config.workspace_dir / "review.jsonl").exists())
        training_page = self.client.get("/training")
        self.assertEqual(training_page.status_code, 200)
        self.assertIn("/static/app/assets/index.js", training_page.text)

    def test_web_does_not_accept_human_review_for_legacy_artifacts(self):
        headers = {"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": self.csrf()}
        response = self.client.post("/api/label/review", json={
            "run_id": "a" * 32, "suggestion_id": "b" * 32, "record_id": "row-1",
            "input_digest": "c" * 64, "idempotency_key": "d" * 32, "action": "accepted",
        }, headers=headers)
        self.assertEqual(response.status_code, 410)
        config = load_project(self.root)
        self.assertFalse((config.workspace_dir / "review.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
