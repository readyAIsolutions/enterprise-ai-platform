"""Unit tests for the model_router enterprise module.

Covers the LiteLLM-style retry/cooldown/fallback gateway:

  - DeploymentModel parsing + add/remove management.
  - Deterministic offline adapters (Echo/Noop).
  - Weighted (hash-bucket) selection distribution.
  - Cooldown after N failures excludes a deployment; expiry re-enables it.
  - Per-exception-type retry policy retries transient errors on the SAME deployment.
  - Cross-model fallback chain switching deployments; max_fallbacks cap.
  - Metric counters (success/fail/latency/fallbacks) increment correctly.
  - Module lifecycle (initialize / health_check / shutdown) incl. idempotency.
  - HTTPAdapter status-code mapping via mocked transport.

Run with:
    python3 -m pytest modules/model_router/tests -q -p no:cacheprovider
"""

from __future__ import annotations

import asyncio
import random
import sys
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from enterprise.modules.model_router import (
    AuthenticationError,
    CooldownCache,
    DeploymentModel,
    EchoAdapter,
    HTTPAdapter,
    ModelRouter,
    ModelRouterModule,
    NoopAdapter,
    ProviderTimeoutError,
    RateLimitError,
    Router,
    ServiceUnavailableError,
    create_model_router_module,
)


# ---------------------------------------------------------------------------
# Data models / management
# ---------------------------------------------------------------------------


def test_deployment_from_dict_parses_known_fields():
    d = DeploymentModel.from_dict(
        {
            "id": "a",
            "model": "gpt-4o",
            "provider": "openrouter",
            "base_url": "https://api.openrouter.ai/v1",
            "api_key_env": "OPENROUTER_KEY",
            "weight": 5,
            "allowed_fails": 2,
            "cooldown_time": 30,
            "max_fallbacks": 3,
            "retry_policy": {"RateLimitError": 4},
            "group": "chat",
        }
    )
    assert d.id == "a"
    assert d.model == "gpt-4o"
    assert d.weight == 5
    assert d.allowed_fails == 2
    assert d.cooldown_time == 30
    assert d.retry_policy == {"RateLimitError": 4}
    assert d.group == "chat"


def test_deployment_defaults():
    d = DeploymentModel(id="x")
    assert d.group == "default"
    assert d.allowed_fails == 3
    assert d.cooldown_time == 60.0
    assert not d.blacklisted


def test_add_remove_deployment_roundtrip():
    r = Router()
    r.add_deployment(DeploymentModel(id="a", group="chat"))
    assert r.get_deployment("a") is not None
    assert len(r.deployments) == 1
    removed = r.remove_deployment("a")
    assert removed.id == "a"
    assert r.get_deployment("a") is None


def test_router_seeds_deployments_from_config():
    cfg = {
        "deployments": [
            {"id": "a", "model": "m1", "group": "g"},
            {"id": "b", "model": "m2", "group": "g"},
        ]
    }
    r = Router(cfg)
    assert set(r.deployments) == {"a", "b"}


def test_unknown_group_returns_error():
    r = Router()
    r.add_deployment(DeploymentModel(id="a", group="g"))
    result = asyncio.run(r.route("nope", [{"role": "user", "content": "hi"}]))
    assert result.status == "error"
    assert "unknown model group" in result.final_error


# ---------------------------------------------------------------------------
# Offline adapters
# ---------------------------------------------------------------------------


def test_echo_adapter_deterministic_offline():
    async def run():
        adapter = EchoAdapter()
        dep = DeploymentModel(id="a", model="m1")
        resp = await adapter.call(dep, [{"role": "user", "content": "hello"}])
        return resp

    resp = asyncio.run(run())
    assert resp.status == "success"
    assert resp.content == "echo[m1]:hello"
    assert resp.tokens["completion_tokens"] > 0


def test_noop_adapter_never_fails():
    async def run():
        adapter = NoopAdapter()
        dep = DeploymentModel(id="a")
        resp = await adapter.call(dep, [])
        return resp

    resp = asyncio.run(run())
    assert resp.status == "success"
    assert resp.content == ""


# ---------------------------------------------------------------------------
# Weighted selection (hash-bucket)
# ---------------------------------------------------------------------------


def _count_weights(seed=42, iterations=4000):
    r = ModelRouter(adapter=NoopAdapter(), rng=random.Random(seed))
    r.add_deployment({"id": "a", "model": "m1", "weight": 1, "group": "g"})
    r.add_deployment({"id": "b", "model": "m2", "weight": 3, "group": "g"})

    counts = {"a": 0, "b": 0}
    for _ in range(iterations):
        res = asyncio.run(r.route("g", [{"role": "user", "content": "x"}]))
        assert res.status == "success"
        counts[res.deployment_id] += 1
    return counts


def test_weighted_selection_distribution():
    counts = _count_weights()
    total = counts["a"] + counts["b"]
    a_frac = counts["a"] / total
    # a has weight 1 of 4 => ~0.25, allow generous tolerance for a seeded rng
    assert 0.15 <= a_frac <= 0.35, f"a_frac={a_frac:.3f}, counts={counts}"


def test_weighted_selection_never_selects_excluded_or_cooldowned():
    r = ModelRouter(adapter=NoopAdapter(), rng=random.Random(1))
    r.add_deployment({"id": "a", "model": "m1", "weight": 1, "group": "g"})
    r.add_deployment({"id": "b", "model": "m2", "weight": 1, "group": "g"})
    picked = r._select_weighted("g", exclude={"a"})
    assert picked.id == "b"
    # cooldown makes a deployment unselectable
    r.cooldown.add_cooldown("b", 1000)
    assert r._select_weighted("g", exclude={"a"}) is None


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


def test_retry_policy_retries_transient_error_on_same_deployment():
    fail_map = {"a": [RateLimitError("rl-1"), RateLimitError("rl-2")]}
    r = ModelRouter(adapter=EchoAdapter(fail_map=fail_map))
    r.add_deployment(
        {
            "id": "a",
            "model": "m1",
            "group": "g",
            "allowed_fails": 10,  # high so retries happen on the same deployment
            "retry_policy": {"RateLimitError": 2},
        }
    )
    res = asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    assert res.status == "success"
    assert res.deployment_id == "a"
    assert res.attempts == 1  # only one deployment selection
    assert res.fallbacks_used == 0
    assert res.messages == "echo[m1]:hi"


def test_retry_exhausted_then_falls_back():
    fail_map = {
        # a fails twice with only 1 retry allowed -> after retry it raises again
        "a": [RateLimitError("a1"), RateLimitError("a2")],
    }
    r = ModelRouter(adapter=EchoAdapter(fail_map=fail_map), rng=random.Random(1))
    r.add_deployment(
        {
            "id": "a", "model": "m1", "group": "g",
            "allowed_fails": 10, "retry_policy": {"RateLimitError": 1},
        }
    )
    r.add_deployment({"id": "b", "model": "m2", "group": "g", "allowed_fails": 10})
    res = asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    assert res.status == "success"
    assert res.deployment_id == "b"
    assert res.attempts == 2
    assert res.fallbacks_used == 1


def test_authentication_error_never_retried():
    fail_map = {"a": [AuthenticationError("no-key")]}
    r = ModelRouter(adapter=EchoAdapter(fail_map=fail_map))
    r.add_deployment({"id": "a", "model": "m1", "group": "g",
                      "retry_policy": {"AuthenticationError": 100}})
    res = asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    assert res.status == "error"
    assert "no-key" in res.final_error


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------


def test_fallback_chain_switches_deployments():
    fail_map = {
        "a": [RateLimitError("a"), RateLimitError("a2")],
        "b": [ServiceUnavailableError("b"), ServiceUnavailableError("b2")],
    }
    r = ModelRouter(adapter=EchoAdapter(fail_map=fail_map), rng=random.Random(4))
    for rid in ("a", "b", "c"):
        r.add_deployment({"id": rid, "model": f"m{rid}", "group": "g",
                          "allowed_fails": 5})
    res = asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    assert res.status == "success"
    assert res.deployment_id == "c"
    assert res.attempts == 3
    assert res.fallbacks_used == 2


def test_max_fallbacks_caps_chain():
    fail_map = {
        "a": [RateLimitError("a"), RateLimitError("a2")],
        "b": [ServiceUnavailableError("b"), ServiceUnavailableError("b2")],
        "c": [RateLimitError("c"), RateLimitError("c2")],
    }
    r = ModelRouter(adapter=EchoAdapter(fail_map=fail_map), rng=random.Random(4))
    for rid in ("a", "b", "c"):
        r.add_deployment({"id": rid, "model": f"m{rid}", "group": "g",
                          "allowed_fails": 5, "max_fallbacks": 1})
    res = asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    # max_fallbacks=1 => only "a" -> "b" then stop (c never tried)
    assert res.status == "error"
    assert res.attempts == 2
    assert res.fallbacks_used == 1


# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------


def test_cooldown_after_n_fails_excludes_deployment():
    fail_map = {"a": [RateLimitError("x")] * 100}
    r = ModelRouter(adapter=EchoAdapter(fail_map=fail_map))
    r.add_deployment({"id": "a", "model": "m1", "group": "g",
                      "allowed_fails": 2, "cooldown_time": 1000})

    for _ in range(2):
        res = asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
        assert res.status == "error"

    assert r.cooldown.is_deployment_cooldowned("a")
    assert "a" in r.cooldown.active_cooldowns()
    assert "a" in r.get_status()["in_cooldown"]
    # with only one irrelevant deployment in group, nothing is selectable now
    res = asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    assert res.status == "error"
    assert "no_healthy_deployment" in res.final_error


def test_cooldown_requires_allowed_fails_threshold():
    cc = CooldownCache(clock=lambda: 0.0)
    assert not cc.is_deployment_cooldowned("a")
    assert not cc.record_failure("a", allowed_fails=2, cooldown_time=60)
    assert not cc.is_deployment_cooldowned("a")
    entered = cc.record_failure("a", allowed_fails=2, cooldown_time=60)
    assert entered is True
    assert cc.is_deployment_cooldowned("a")
    # failure counter is reset after cooldown is added
    assert cc.failure_count("a") == 0


def test_cooldown_expiry_reenables_deployment():
    fail_map = {"a": [RateLimitError("x")] * 100}
    r = ModelRouter(adapter=EchoAdapter(fail_map=fail_map), rng=random.Random(3))
    r.add_deployment({"id": "a", "model": "m1", "group": "g",
                      "allowed_fails": 1, "cooldown_time": 0.05})

    res = asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    assert res.status == "error"
    assert r.cooldown.is_deployment_cooldowned("a")
    # Wait for the tiny cooldown to elapse.
    pytest.importorskip("asyncio")
    import time

    time.sleep(0.1)
    assert not r.cooldown.is_deployment_cooldowned("a")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def test_success_and_failure_counters_increment():
    r = ModelRouter(adapter=EchoAdapter(fail_map={"a": [RateLimitError("x")] * 100}),
                    rng=random.Random(1))
    r.add_deployment({"id": "a", "model": "m1", "group": "g", "allowed_fails": 10})
    r.add_deployment({"id": "b", "model": "m2", "group": "g", "allowed_fails": 10})

    asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))  # a fails -> b wins
    snap = r.snapshot()
    assert snap["deployments"]["a"]["failures"] == 1
    assert snap["deployments"]["b"]["successes"] == 1
    assert snap["request_count"] == 1


def test_avg_latency_and_fallbacks_metrics():
    r = ModelRouter(adapter=EchoAdapter(fail_map={"a": [RateLimitError("x")] * 100}),
                    rng=random.Random(1))
    r.add_deployment({"id": "a", "model": "m1", "group": "g", "allowed_fails": 10})
    r.add_deployment({"id": "b", "model": "m2", "group": "g", "allowed_fails": 10})
    asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    snap = r.snapshot()
    assert snap["fallbacks_used"] == 1
    assert snap["deployments"]["b"]["avg_latency_ms"] >= 0
    assert snap["route_metrics_enabled"] is True


def test_metrics_disabled_when_route_metrics_false():
    r = ModelRouter(adapter=EchoAdapter(), config={"route_metrics": False})
    r.add_deployment({"id": "a", "model": "m1", "group": "g"})
    asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    snap = r.snapshot()
    assert snap["route_metrics_enabled"] is False
    # counters stay at zero when metrics are disabled
    assert snap["deployments"]["a"]["successes"] == 0
    assert snap["request_count"] == 0


def test_snapshot_structure_complete():
    r = ModelRouter(adapter=NoopAdapter())
    r.add_deployment({"id": "a", "model": "m1", "group": "g"})
    asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    snap = r.snapshot()
    for key in ("request_count", "fallbacks_used", "cooldowns", "deployments"):
        assert key in snap
    dep = snap["deployments"]["a"]
    for key in ("successes", "failures", "avg_latency_ms", "model", "weight"):
        assert key in dep


# ---------------------------------------------------------------------------
# Status / health
# ---------------------------------------------------------------------------


def test_get_status_and_health():
    r = ModelRouter(adapter=NoopAdapter())
    assert r.health() is False  # no deployments
    r.add_deployment({"id": "a", "model": "m1", "group": "g"})
    assert r.health() is True
    status = r.get_status()
    assert "a" in status["healthy"]
    assert "a" in status["deployments"]


def test_blacklist_excludes_deployment():
    r = ModelRouter(adapter=NoopAdapter(), config={"blacklist": ["a"]})
    r.add_deployment({"id": "a", "model": "m1", "group": "g"})
    r.add_deployment({"id": "b", "model": "m2", "group": "g"})
    assert r.get_deployment("a").blacklisted is True
    res = asyncio.run(r.route("g", [{"role": "user", "content": "hi"}]))
    assert res.status == "success"
    assert res.deployment_id == "b"


# ---------------------------------------------------------------------------
# Module lifecycle
# ---------------------------------------------------------------------------


def test_module_version_and_creation():
    assert create_model_router_module.__module__  # callable exists
    mod = create_model_router_module({})
    assert isinstance(mod, ModelRouterModule)
    assert mod.version == "1.0.0"


def test_module_health_check_healthy_after_initialize():
    mod = ModelRouterModule({"deployments": [{"id": "a", "model": "m1"}]})

    async def run():
        await mod.initialize()
        status = await mod.health_check()
        await mod.shutdown()
        return status

    status = asyncio.run(run())
    assert status.value == "healthy"


def test_module_health_check_unhealthy_before_init():
    mod = ModelRouterModule({})

    async def run():
        return await mod.health_check()

    status = asyncio.run(run())
    assert status.value == "unhealthy"


def test_shutdown_is_idempotent_and_builds_router():
    mod = ModelRouterModule({"deployments": [{"id": "a", "model": "m1"}]})

    async def run():
        await mod.initialize()
        assert mod.router is not None
        assert len(mod.router.deployments) == 1
        await mod.shutdown()
        await mod.shutdown()  # idempotent, must not raise
        await mod.shutdown()
        return True

    assert asyncio.run(run()) is True


def test_state_transitions_no_crash():
    mod = ModelRouterModule({})

    async def run():
        await mod.initialize()
        await mod.initialize()  # re-init should not crash
        await mod.shutdown()
        await mod.initialize()
        await mod.shutdown()
        return True

    assert asyncio.run(run()) is True


def test_module_registered_by_decorator():
    from enterprise.platform_kernel import _MODULE_REGISTRY  # noqa: PLC2701

    assert "model_router" in _MODULE_REGISTRY
    assert _MODULE_REGISTRY["model_router"]._meta_name == "model_router"


# ---------------------------------------------------------------------------
# HTTPAdapter transport mapping (mocked, no network)
# ---------------------------------------------------------------------------


def _http_body(content="ok"):
    return '{"choices":[{"message":{"content":"%s"}}],"usage":{"prompt_tokens":1,"completion_tokens":1}}' % content


def test_http_adapter_maps_429_to_rate_limit():
    dep = DeploymentModel(id="a", model="m1", base_url="https://example.test/v1")
    with mock.patch.object(
        urllib.request, "urlopen",
        side_effect=urllib.error.HTTPError("https://example.test", 429, "rl", {}, None),
    ):
        with pytest.raises(RateLimitError):
            asyncio.run(HTTPAdapter().call(dep, []))

def test_http_adapter_maps_500_to_service_unavailable():
    dep = DeploymentModel(id="a", model="m1", base_url="https://example.test/v1")
    with mock.patch.object(
        urllib.request, "urlopen",
        side_effect=urllib.error.HTTPError("https://example.test", 503, "down", {}, None),
    ):
        with pytest.raises(ServiceUnavailableError):
            asyncio.run(HTTPAdapter().call(dep, []))


def test_http_adapter_success_parses_content_and_tokens():
    dep = DeploymentModel(
        id="a", model="m1", base_url="https://example.test/v1",
        api_key_env="MODEL_ROUTER_TEST_KEY",
    )
    fake = mock.MagicMock()
    fake.read.return_value = _http_body("hi there").encode()
    fake.__enter__.return_value = fake
    with mock.patch.dict("os.environ", {"MODEL_ROUTER_TEST_KEY": "sekret"}):
        with mock.patch.object(urllib.request, "urlopen", return_value=fake):
            resp = asyncio.run(HTTPAdapter().call(dep, [{"role": "user", "content": "hi"}]))

    assert resp.status == "success"
    assert resp.content == "hi there"
    assert resp.tokens["prompt_tokens"] == 1


@pytest.mark.parametrize(
    "exc,factory",
    [
        (urllib.error.URLError("conn refused"), ProviderTimeoutError),
        (TimeoutError("took long"), ProviderTimeoutError),
    ],
)
def test_http_adapter_maps_network_errors_to_timeout(exc, factory):
    from unittest.mock import patch as _patch

    dep = DeploymentModel(id="a", model="m1", base_url="https://example.test/v1")
    with _patch.object(urllib.request, "urlopen", side_effect=exc):
        with pytest.raises(factory):
            asyncio.run(HTTPAdapter().call(dep, []))
