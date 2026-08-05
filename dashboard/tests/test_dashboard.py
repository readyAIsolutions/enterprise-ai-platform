"""Tests for Enterprise Dashboard."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.dashboard.server import app
from starlette.testclient import TestClient
from enterprise.dashboard import server as dash_server

client = TestClient(app)


class TestDashboardServer(unittest.TestCase):
    """Dashboard server tests. Tolerant of offline validation engine."""

    def test_app_created(self):
        self.assertIsNotNone(app)

    def test_homepage_returns_200(self):
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)

    def test_homepage_contains_dashboard(self):
        resp = client.get("/")
        self.assertIn("DASHBOARD", resp.text.upper())

    def test_api_score_returns_json(self):
        resp = client.get("/api/score")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("final_score", data)

    def test_api_score_offline_handled(self):
        resp = client.get("/api/score")
        data = resp.json()
        score = data.get("final_score")
        self.assertIsNotNone(score)

    def test_api_modules_returns_dict(self):
        resp = client.get("/api/modules")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, dict)

    def test_api_swarm_returns_json(self):
        resp = client.get("/api/swarm")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("signal_dbm", data)

    def test_api_events_returns_json(self):
        resp = client.get("/api/events")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("events", data)

    def test_api_health_returns_json(self):
        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)

    def test_score_caching(self):
        resp1 = client.get("/api/score")
        resp2 = client.get("/api/score")
        self.assertEqual(resp1.json().get("final_score"), resp2.json().get("final_score"))

    def test_static_css(self):
        resp = client.get("/static/style.css")
        self.assertEqual(resp.status_code, 200)

    def test_api_metrics_returns_snapshot(self):
        resp = client.get("/api/metrics")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("counters", data)
        self.assertIn("gauges", data)
        self.assertIn("histograms", data)
        self.assertIn("history_count", data)
        self.assertIn("live", data)

    def test_api_events_live_last_n_after_publish(self):
        """/api/events must return REAL last-N events after publishing."""
        dash_server.publish_event("test.live", "dashboard", {"seq": 1})
        dash_server.publish_event("test.live", "dashboard", {"seq": 2})
        dash_server.publish_event("test.live", "dashboard", {"seq": 3})
        resp = client.get("/api/events?limit=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data.get("count", 0), 3)
        events = data.get("events", [])
        self.assertTrue(data.get("live", False) is not None)
        topics = [e["topic"] for e in events]
        # All three real test events surface in the last-3 window.
        self.assertEqual(topics.count("test.live"), 3)
        # Payloads are real and serialized, not hardcoded empties.
        seqs = [e["payload"].get("seq") for e in events if e["topic"] == "test.live"]
        self.assertIn(1, seqs)
        self.assertIn(3, seqs)

    def test_api_health_includes_module_and_metrics_data(self):
        """/api/health must report real per-module + live metrics data."""
        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("uptime", data)
        self.assertIn("modules", data)
        self.assertIn("metrics", data)
        # The self-check module has a real per-module report.
        module_map = data["modules"]
        self.assertIn("dashboard", module_map)
        latest = module_map["dashboard"][-1]
        self.assertIn("status", latest)
        self.assertIn("response_time_ms", latest)
        self.assertIn("details", latest)
        # Functional capability probe recorded in details.
        self.assertIn("functional", latest["details"])
        # Live metrics snapshot embedded.
        self.assertIn("counters", data["metrics"])
        self.assertIn("gauges", data["metrics"])


if __name__ == "__main__":
    unittest.main()