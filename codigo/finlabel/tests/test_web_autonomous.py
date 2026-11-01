import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from finlabel.labeling.task import LabelTask, save_task
from finlabel.project import init_project, load_project, save_project
from finlabel.sources.base import SourceSpec


class AutonomousWebTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        init_project(self.root)
        source_path = self.root / "portfolio.csv"
        source_path.write_text("amount,private\n12,SECRET_FINANCIAL_ROW\n18,SECRET_FINANCIAL_ROW\n", encoding="utf-8")
        config = load_project(self.root)
        config.sources["portfolio"] = SourceSpec("portfolio", "csv", source_path, schema={"amount": "decimal", "private": "string"})
        save_project(config, config.path)
        save_task(LabelTask("risk", "Classify portfolio risk", ("amount",), ("low", "high"), "local-test-model"), config.workspace_dir / "tasks" / "risk.json")
        from finlabel.web.app import create_app
        self.client = TestClient(create_app(self.root, host="127.0.0.1", port=8765), base_url="http://127.0.0.1:8765")

    def tearDown(self):
        self.temporary.cleanup()

    def test_panel_routes_serve_the_react_shell_on_direct_load_and_refresh(self):
        run_id = "a" * 32
        for path in ("/", "/analysis", "/monitor", "/labeling", "/training", "/review", f"/analysis/{run_id}"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.text[:200])
                self.assertIn("/static/app/assets/index.js", response.text)

    def test_health_endpoint_matches_the_panel_connection_contract(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"status": "ok", "project": self.root.name, "sources": 1})

    def test_sources_endpoint_serves_only_schema_metadata_for_existing_panel_pages(self):
        response = self.client.get("/api/sources")
        self.assertEqual(response.status_code, 200, response.text)
        source = response.json()["sources"][0]
        self.assertEqual(source["name"], "portfolio")
        self.assertEqual([column["name"] for column in source["columns"]], ["amount", "private"])
        self.assertNotIn("SECRET_FINANCIAL_ROW", response.text)

    def test_autonomy_overview_exposes_metadata_and_aggregates_without_rows(self):
        response = self.client.get("/api/autonomy/overview")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["sources"][0]["name"], "portfolio")
        self.assertEqual(response.json()["tasks"][0]["task_id"], "risk")
        self.assertNotIn("SECRET_FINANCIAL_ROW", response.text)
        self.assertNotIn("Classify portfolio risk", response.text)

    def test_autonomy_overview_rejects_a_tampered_model_event(self):
        from finlabel.training.registry import ModelRegistry, _digest
        event = {
            "candidate_id": "c" * 32, "evaluation_id": "e" * 32, "task_id": "risk",
            "action": "reject", "reason_codes": [], "previous_model_ref": None,
            "active_model_ref": "local/model", "policy_sha256": "a" * 64,
            "evaluation_sha256": "b" * 64, "created_at": "2026-10-26T12:00:00Z",
        }
        event["event_id"] = _digest({key: value for key, value in event.items() if key != "created_at"})
        journal = self.root / ".finlabel" / "models" / "registry-events.jsonl"
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text(json.dumps(event) + "\n", encoding="utf-8")

        original_init = ModelRegistry.__init__
        def initialize_then_tamper(registry, workspace_dir):
            original_init(registry, workspace_dir)
            event["action"] = "promote"
            journal.write_text(json.dumps(event) + "\n", encoding="utf-8")

        from unittest.mock import patch
        with patch.object(ModelRegistry, "__init__", initialize_then_tamper):
            response = self.client.get("/api/autonomy/overview")

        self.assertEqual(response.status_code, 400, response.text)
        self.assertNotIn('"action": "reject"', response.text)

    def test_autonomous_run_uses_csrf_and_returns_only_aggregate_results(self):
        self.client.get("/")
        token = self.client.cookies.get("finlabel_csrf")
        headers = {"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": token, "Idempotency-Key": "run-risk-001"}
        denied = self.client.post("/api/autonomy/run", json={"source": "portfolio", "task": "risk"}, headers={"Origin": headers["Origin"]})
        self.assertEqual(denied.status_code, 403)
        response = self.client.post("/api/autonomy/run", json={"source": "portfolio", "task": "risk"}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["labeling"]["outcome_count"], 2)
        self.assertEqual(payload["labeling"]["quarantined_count"], 2)
        self.assertEqual(payload["training"]["state"], "blocked")
        self.assertNotIn("SECRET_FINANCIAL_ROW", response.text)
        self.assertTrue((self.root / ".finlabel" / "pipeline-runs" / (payload["run_id"] + "/run.json")).is_file())
        replay = self.client.post("/api/autonomy/run", json={"source": "portfolio", "task": "risk"}, headers=headers)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), payload)
        conflict = self.client.post("/api/autonomy/run", json={"source": "portfolio", "task": "other"}, headers=headers)
        self.assertEqual(conflict.status_code, 409, conflict.text)

