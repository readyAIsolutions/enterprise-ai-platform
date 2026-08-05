"""Hermetic, offline tests for the model_router live smoke/sanity helpers.

Covers:
  - LiveProbe: reachable / detail with *injected* responses (no network).
  - LiveFailoverSmoke: picks the healthy deployment after a simulated
    429 / 5xx / timeout and applies cooldown to the failing one.
  - Flailover chain chooses the non-cooldowned deployment.
  - HTTPAdapter.diagnose classifies each error category.
  - ping_local_free_router(): tuple-structure correctness via monkeypatch, and a
    live skipif-guarded check when 127.0.0.1:8920 is actually up.

All tests run fully offline — failures are injected through request functions g
so no socket or real provider is ever contacted.
"""

from __future__ import annotations

import socket
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from typing import Never

import pytest
from enterprise.modules.model_router import (
    CAT_AUTH,
    CAT_RATE_LIMIT,
    CAT_TIMEOUT,
    CAT_UNAVAILABLE,
    AuthenticationError,
    DeploymentModel,
    HTTPAdapter,
    LiveFailoverSmoke,
    LiveProbe,
    ProviderTimeoutError,
    ServiceUnavailableError,
    classify_http_error,
    ping_local_free_router,
)

# ---------------------------------------------------------------------------
# Helpers: injected request functions (deterministic, zero network)
# ---------------------------------------------------------------------------


def _mk_deployments():
    return [
        DeploymentModel(id="a", model="m-a", base_url="http://probe-a.test/v1"),
        DeploymentModel(id="b", model="m-b", base_url="http://probe-b.test/v1"),
    ]


def _ok(base_url="http://x.test/v1", model="m", api_key=None, timeout=15.0):
    return (200, {"choices": [{"message": {"content": "ok"}}]})


def _rl(base_url="http://x.test/v1", model="m", api_key=None, timeout=15.0):
    return (429, {})


def _svc(base_url="http://x.test/v1", model="m", api_key=None, timeout=15.0):
    return (503, {})


def _timeout(base_url="http://x.test/v1", model="m", api_key=None, timeout=15.0) -> Never:
    msg = "connection timed out"
    raise ProviderTimeoutError(msg)


def _route_by_url(responses):
    """Return a request_fn routing on exact base_url match (falls back to 200)."""

    def _fn(base_url, model="m", api_key=None, timeout=15.0):
        if base_url in responses:
            return responses[base_url](
                base_url=base_url, model=model, api_key=api_key, timeout=timeout
            )
        return (200, {})

    return _fn


# ---------------------------------------------------------------------------
# LiveProbe
# ---------------------------------------------------------------------------


def test_live_probe_reachable_with_injected_response() -> None:
    res = LiveProbe().run("http://ok.test/v1", model="m", request_fn=_ok)
    assert res.reachable is True
    assert res.status_code == 200
    assert res.error is None
    assert res.latency_ms >= 0.0


def test_live_probe_rate_limited_unreachable() -> None:
    res = LiveProbe().run("http://rl.test/v1", model="m", request_fn=_rl)
    assert res.reachable is False
    assert res.status_code == 429
    assert "429" in res.error


def test_live_probe_5xx_unreachable() -> None:
    res = LiveProbe().run("http://svc.test/v1", model="m", request_fn=_svc)
    assert res.reachable is False
    assert res.status_code == 503


def test_live_probe_timeout_unreachable() -> None:
    res = LiveProbe().run("http://to.test/v1", model="m", request_fn=_timeout)
    assert res.reachable is False
    assert res.status_code is None
    assert "timed out" in res.error.lower() or "timeout" in res.error.lower()


def test_live_probe_result_dict_keys_present() -> None:
    res = LiveProbe().run("http://ok.test/v1", model="m", request_fn=_ok)
    d = res.as_dict()
    for key in ("reachable", "status_code", "error", "latency_ms", "cooldowned"):
        assert key in d


# ---------------------------------------------------------------------------
# LiveFailoverSmoke
# ---------------------------------------------------------------------------


def test_failover_picks_healthy_after_429_cooldown() -> None:
    deployments = _mk_deployments()
    smoke = LiveFailoverSmoke(
        deployments,
        request_fn=_route_by_url({"http://probe-a.test/v1": _rl}),
        allowed_fails=1,
        cooldown_time=60.0,
    )
    out = smoke.run()
    assert out["ok"] is True
    assert out["selected"] == "b"
    assert "b" in out["reachable"]
    assert smoke.cooldown.is_deployment_cooldowned("a") is True


def test_failover_picks_healthy_after_5xx() -> None:
    deployments = _mk_deployments()
    smoke = LiveFailoverSmoke(
        deployments,
        request_fn=_route_by_url({"http://probe-a.test/v1": _svc}),
        allowed_fails=1,
        cooldown_time=60.0,
    )
    out = smoke.run()
    assert out["selected"] == "b"
    assert smoke.cooldown.is_deployment_cooldowned("a") is True


def test_failover_picks_healthy_after_timeout() -> None:
    deployments = _mk_deployments()
    smoke = LiveFailoverSmoke(
        deployments,
        request_fn=_route_by_url({"http://probe-a.test/v1": _timeout}),
        allowed_fails=1,
        cooldown_time=60.0,
    )
    out = smoke.run()
    assert out["selected"] == "b"
    assert smoke.cooldown.is_deployment_cooldowned("a") is True


def test_failover_reports_reachable_list() -> None:
    deployments = _mk_deployments()
    smoke = LiveFailoverSmoke(
        deployments,
        request_fn=_route_by_url({"http://probe-a.test/v1": _rl}),
        allowed_fails=1,
        cooldown_time=60.0,
    )
    out = smoke.run()
    assert out["reachable"] == ["b"]


def test_failover_chain_chooses_non_cooldowned_deployment() -> None:
    # Both transient-fail: 'a' 429, 'b' 503 -> nothing healthy.
    deployments = _mk_deployments()
    smoke = LiveFailoverSmoke(
        deployments,
        request_fn=_route_by_url(
            {
                "http://probe-a.test/v1": _rl,
                "http://probe-b.test/v1": _svc,
            }
        ),
        allowed_fails=1,
        cooldown_time=60.0,
    )
    out = smoke.run()
    assert out["ok"] is False
    assert out["selected"] is None
    assert smoke.cooldown.is_deployment_cooldowned("a") is True
    assert smoke.cooldown.is_deployment_cooldowned("b") is True


def test_failover_smoke_accepts_dict_deployments() -> None:
    deployments = [
        {"id": "x", "model": "m", "base_url": "http://x.test/v1"},
        {"id": "y", "model": "m", "base_url": "http://y.test/v1"},
    ]
    smoke = LiveFailoverSmoke(
        deployments,
        request_fn=_route_by_url({"http://x.test/v1": _timeout}),
        allowed_fails=1,
        cooldown_time=60.0,
    )
    out = smoke.run()
    assert out["selected"] == "y"


# ---------------------------------------------------------------------------
# HTTPAdapter.diagnose / classify_http_error
# ---------------------------------------------------------------------------


def test_classify_auth() -> None:
    cat, reason = classify_http_error(AuthenticationError("bad key"))
    assert cat == CAT_AUTH
    assert "auth" in reason.lower()


def test_classify_rate_limit_with_retry_after() -> None:
    raw = urllib.error.HTTPError("http://x.test", 429, "rl", {"Retry-After": "2"}, None)
    cat, reason = classify_http_error(raw)
    assert cat == CAT_RATE_LIMIT
    assert "Retry-After" in reason


def test_classify_unavailable() -> None:
    raw = urllib.error.HTTPError("http://x.test", 503, "svc", {}, None)
    cat, reason = classify_http_error(raw)
    assert cat == CAT_UNAVAILABLE


def test_classify_timeout() -> None:
    cat, reason = classify_http_error(ProviderTimeoutError("slow"))
    assert cat == CAT_TIMEOUT


def test_adapter_diagnose_classifies_last_outcome() -> None:
    adapter = HTTPAdapter()
    assert adapter.diagnose() == "no prior call recorded"
    adapter._record_outcome(429, None)
    assert "429" in adapter.diagnose()
    assert "rate" in adapter.diagnose().lower()


def test_adapter_diagnose_with_explicit_error() -> None:
    adapter = HTTPAdapter()
    assert "auth" in adapter.diagnose(error=AuthenticationError("denied")).lower()
    assert "unavailable" in adapter.diagnose(error=ServiceUnavailableError("down")).lower()


# ---------------------------------------------------------------------------
# ping_local_free_router (hermetic + live-skipif)
# ---------------------------------------------------------------------------


def test_ping_local_free_router_returns_tuple() -> None:
    ok, detail = ping_local_free_router(host="127.0.0.1", port=9, timeout=0.2)
    assert isinstance(ok, bool)
    assert isinstance(detail, str)


def test_ping_local_free_router_unreachable(monkeypatch) -> None:
    def _refuse(*a, **k) -> Never:
        msg = "nope"
        raise ConnectionRefusedError(msg)

    monkeypatch.setattr(socket, "create_connection", _refuse)
    ok, detail = ping_local_free_router(host="127.0.0.1", port=8920, timeout=0.2)
    assert ok is False
    assert "unreachable" in detail


def _local_free_router_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8920), timeout=0.5):
            return True
    except OSError:
        return False


@pytest.mark.skipif(
    not _local_free_router_up(), reason="local free-router not up at 127.0.0.1:8920"
)
def test_ping_local_free_router_live_when_up() -> None:
    ok, detail = ping_local_free_router()
    assert ok is True
    assert "reachable" in detail
