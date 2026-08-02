"""Tests for Enterprise Dashboard."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.dashboard.server import app
from starlette.testclient import TestClient

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


if __name__ == "__main__":
    unittest.main()