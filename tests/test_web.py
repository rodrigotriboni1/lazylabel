import importlib
import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from finlabel.analysis.schema import AnalysisPlan, MetricSpec
from finlabel.project import init_project, load_project, save_project
from finlabel.sources.base import SourceSpec
from finlabel.labeling.task import LabelTask, save_task
from finlabel.review import ReviewLog


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
            self.web_app = importlib.import_module("finlabel.web.app")
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
        return self.client.cookies.get("finlabel_csrf")

    def test_home_escapes_metadata_and_does_not_render_source_rows(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("sales", response.text)
        self.assertIn("amount", response.text)
        self.assertNotIn("SECRET_ROW_VALUE", response.text)
        self.assertEqual(response.cookies.get("finlabel_csrf") is not None, True)
        self.assertIn("SameSite=strict", response.headers.get("set-cookie", ""))

    def test_rejects_non_loopback_bind_and_escapes_untrusted_source_names(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            self.web_app.create_app(self.root, backend_factory=lambda config: None, host="0.0.0.0", port=8765)
        config = load_project(self.root)
        malicious_name = "<script>alert(1)</script>"
        config.sources[malicious_name] = SourceSpec(malicious_name, "csv", self.root / "sales.csv")
        save_project(config, config.path)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<script>alert(1)</script>", response.text)
        self.assertIn("&lt;script&gt;", response.text)

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
        baseline_path = self.root / ".finlabel" / "schemas" / "sales.json"
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
        self.assertEqual(payload["rows"][1]["value"], "15")
        self.assertIn("15", payload["highlights"][0])
        page = self.client.get(payload["analysis_url"])
        self.assertEqual(page.status_code, 200)
        self.assertIn('sandbox="allow-scripts"', page.text)
        chart = self.client.get(payload["chart_url"])
        self.assertEqual(chart.status_code, 200)
        self.assertIn("sandbox allow-scripts", chart.headers.get("content-security-policy", ""))
        self.assertFalse(any((self.root / ".finlabel" / "analyses").glob("*/source.csv")))

    def test_web_label_review_and_dataset_prepare_use_shared_local_state(self):
        config = load_project(self.root)
        save_task(
            LabelTask("risk", "Classify financial risk", ("amount",), ("low", "high"), "test-local-model"),
            config.workspace_dir / "tasks" / "risk.json",
        )
        self.backend.responses = ['{"label":"low"}', '{"label":"high"}']
        token = self.csrf()
        headers = {"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": token}

        page = self.client.get("/labeling")
        self.assertEqual(page.status_code, 200)
        started = self.client.post("/api/label/start", json={"source": "sales", "task": "risk"}, headers=headers)
        self.assertEqual(started.status_code, 200, started.text)
        run_id = started.json()["run_id"]
        suggestions = self.client.get("/api/label/suggestions", params={"run_id": run_id})
        self.assertEqual(suggestions.status_code, 200)
        first = suggestions.json()["suggestions"][0]
        self.assertEqual(first["fields"], {"amount": "10"})
        self.assertNotIn("SECRET_ROW_VALUE", suggestions.text)
        self.assertEqual(first["stale"], False)

        review_payload = {
            "run_id": run_id, "suggestion_id": first["suggestion_id"], "record_id": first["record_id"],
            "input_digest": first["input_digest"], "idempotency_key": "a" * 32, "action": "accepted",
        }
        review = self.client.post("/api/label/review", json=review_payload, headers=headers)
        self.assertEqual(review.status_code, 200, review.text)
        duplicate = self.client.post("/api/label/review", json=review_payload, headers=headers)
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json()["duplicate"])
        reused_key = dict(review_payload)
        reused_key.update({key: second_value for key, second_value in {
            "suggestion_id": suggestions.json()["suggestions"][1]["suggestion_id"],
            "record_id": suggestions.json()["suggestions"][1]["record_id"],
            "input_digest": suggestions.json()["suggestions"][1]["input_digest"],
        }.items()})
        key_conflict = self.client.post("/api/label/review", json=reused_key, headers=headers)
        self.assertEqual(key_conflict.status_code, 409)
        self.assertEqual(len(ReviewLog(config.workspace_dir / "review.jsonl").read()), 1)

        dataset = self.client.post(
            "/api/dataset/prepare", json={"run_id": run_id, "output_name": "reviewed.jsonl"}, headers=headers,
        )
        self.assertEqual(dataset.status_code, 200, dataset.text)
        self.assertEqual(dataset.json()["rows"], 1)
        training_page = self.client.get("/training")
        self.assertEqual(training_page.status_code, 200)
        self.assertIn("reviewed.jsonl", training_page.text)
        unconfirmed = self.client.post("/api/train/submit", json={
            "confirmed": False, "dataset_name": "reviewed.jsonl", "model_id": "test-local-model",
        }, headers=headers)
        self.assertEqual(unconfirmed.status_code, 400)
        gate_rejected = self.client.post("/api/train/submit", json={
            "confirmed": True, "dataset_name": "reviewed.jsonl", "model_id": "test-local-model",
        }, headers=headers)
        self.assertEqual(gate_rejected.status_code, 400)
        self.assertIn("training gate", gate_rejected.json()["error"])
        self.assertFalse((config.workspace_dir / "training" / "jobs").exists())


if __name__ == "__main__":
    unittest.main()
