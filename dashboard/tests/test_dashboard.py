"""Tests for Enterprise Dashboard."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.dashboard import server as dash_server
from enterprise.dashboard.server import app
from starlette.testclient import TestClient

client = TestClient(app)


class TestDashboardServer(unittest.TestCase):
    """Dashboard server tests. Tolerant of offline validation engine."""

    def test_app_created(self) -> None:
        assert app is not None

    def test_homepage_returns_200(self) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_homepage_contains_dashboard(self) -> None:
        resp = client.get("/")
        assert "DASHBOARD" in resp.text.upper()

    def test_api_score_returns_json(self) -> None:
        resp = client.get("/api/score")
        assert resp.status_code == 200
        data = resp.json()
        assert "final_score" in data

    def test_api_score_offline_handled(self) -> None:
        resp = client.get("/api/score")
        data = resp.json()
        score = data.get("final_score")
        assert score is not None

    def test_api_modules_returns_dict(self) -> None:
        resp = client.get("/api/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_api_swarm_returns_json(self) -> None:
        resp = client.get("/api/swarm")
        assert resp.status_code == 200
        data = resp.json()
        assert "signal_dbm" in data

    def test_api_events_returns_json(self) -> None:
        resp = client.get("/api/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data

    def test_api_health_returns_json(self) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_score_caching(self) -> None:
        resp1 = client.get("/api/score")
        resp2 = client.get("/api/score")
        assert resp1.json().get("final_score") == resp2.json().get("final_score")

    def test_static_css(self) -> None:
        resp = client.get("/static/style.css")
        assert resp.status_code == 200

    def test_api_metrics_returns_snapshot(self) -> None:
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert "counters" in data
        assert "gauges" in data
        assert "histograms" in data
        assert "history_count" in data
        assert "live" in data

    def test_api_events_live_last_n_after_publish(self) -> None:
        """/api/events must return REAL last-N events after publishing."""
        dash_server.publish_event("test.live", "dashboard", {"seq": 1})
        dash_server.publish_event("test.live", "dashboard", {"seq": 2})
        dash_server.publish_event("test.live", "dashboard", {"seq": 3})
        resp = client.get("/api/events?limit=3")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("count", 0) >= 3
        events = data.get("events", [])
        assert data.get("live", False) is not None
        topics = [e["topic"] for e in events]
        # All three real test events surface in the last-3 window.
        assert topics.count("test.live") == 3
        # Payloads are real and serialized, not hardcoded empties.
        seqs = [e["payload"].get("seq") for e in events if e["topic"] == "test.live"]
        assert 1 in seqs
        assert 3 in seqs

    def test_api_health_includes_module_and_metrics_data(self) -> None:
        """/api/health must report real per-module + live metrics data."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "uptime" in data
        assert "modules" in data
        assert "metrics" in data
        # The self-check module has a real per-module report.
        module_map = data["modules"]
        assert "dashboard" in module_map
        latest = module_map["dashboard"][-1]
        assert "status" in latest
        assert "response_time_ms" in latest
        assert "details" in latest
        # Functional capability probe recorded in details.
        assert "functional" in latest["details"]
        # Live metrics snapshot embedded.
        assert "counters" in data["metrics"]
        assert "gauges" in data["metrics"]


if __name__ == "__main__":
    unittest.main()


class TestControlConsole(unittest.TestCase):
    """Control-console endpoint tests (POST /api/control)."""

    def test_control_route_registered(self) -> None:
        routes = [r.path for r in app.routes]
        assert "/api/control" in routes

    def test_control_rejects_unknown_verb(self) -> None:
        resp = client.post("/api/control", json={"verb": "rm -rf /tmp/x"})
        assert resp.status_code == 400
        assert resp.json().get("ok") is False

    def test_control_rejects_bad_agent_os_sub_verb(self) -> None:
        resp = client.post("/api/control", json={"verb": "agent-os", "args": {"verb": "drop database"}})
        assert resp.status_code == 400

    def test_control_agent_os_status_runs(self) -> None:
        resp = client.post("/api/control", json={"verb": "agent-os", "args": {"verb": "status"}})
        assert resp.status_code == 200
        data = resp.json()
        assert "ok" in data

    def test_homepage_has_console(self) -> None:
        resp = client.get("/")
        assert "CONTROL CONSOLE" in resp.text.upper()
