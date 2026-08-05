"""Tests for swarm_network connection multiplexing (mux.py) + module dedupe."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from typing import Never

import pytest

from enterprise.modules.swarm_network import (
    ConnectionScorer,
    Link,
    LinkManager,
    Muxer,
    SwarmNetworkModule,
    create_swarm_network_module,
    select_route,
)
from enterprise.platform_kernel import _MODULE_REGISTRY

# ═══════════════════════════════════════════════════════════════════════════
# Dedupe verification
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleDedupe(unittest.TestCase):
    """The @module decorator must register swarm_network exactly ONCE."""

    def test_exactly_one_registry_entry(self) -> None:
        matches = [(name, cls) for name, cls in _MODULE_REGISTRY.items() if name == "swarm_network"]
        assert len(matches) == 1
        assert matches[0][1] is SwarmNetworkModule

    def test_single_decorator_in_source(self) -> None:
        """Only ONE executable @module decorator should exist in __init__.py."""
        path = Path(__file__).resolve().parents[1] / "__init__.py"
        text = path.read_text(encoding="utf-8")
        # Count decorator usages: lines starting (after ws) with @module(
        decorator_lines = [ln for ln in text.splitlines() if ln.strip().startswith("@module(")]
        assert len(decorator_lines) == 1
        assert 'name="swarm_network"' in decorator_lines[0]

    def test_factory_returns_module(self) -> None:
        m = create_swarm_network_module({"turbo_mode": True})
        assert isinstance(m, SwarmNetworkModule)
        assert m._config.get("turbo_mode")


# ═══════════════════════════════════════════════════════════════════════════
# Connection scoring
# ═══════════════════════════════════════════════════════════════════════════


class TestConnectionScorer(unittest.TestCase):
    def setUp(self) -> None:
        self.scorer = ConnectionScorer()

    def test_perfect_signals_score_100(self) -> None:
        assert self.scorer.score() == 100.0

    def test_dead_link_scores_low(self) -> None:
        s = self.scorer.score(signal=0.0, bandwidth=0.0, latency_ms=150.0, reliability=0.0)
        assert s == 0.0

    def test_score_within_bounds(self) -> None:
        for i in range(20):
            s = self.scorer.score(signal=i / 20, bandwidth=0.5, latency_ms=30 + i, reliability=0.8)
            assert s >= 0.0
            assert s <= 100.0

    def test_better_signals_beat_worse(self) -> None:
        good = self.scorer.score(signal=0.9, bandwidth=0.9, latency_ms=10, reliability=0.95)
        bad = self.scorer.score(signal=0.1, bandwidth=0.1, latency_ms=140, reliability=0.2)
        assert good > bad

    def test_latency_scoring_clamped(self) -> None:
        assert self.scorer.score_latency(0) == 100.0  # no latency
        assert self.scorer.score_latency(150.0) == 0.0  # at budget
        assert self.scorer.score_latency(1000.0) == 0.0  # over budget
        assert self.scorer.score_latency(60.0) > 50.0  # 40% of budget

    def test_custom_weights_normalise_to_1(self) -> None:
        s = ConnectionScorer(weights={"signal": 2, "bandwidth": 1})
        self.assertAlmostEqual(sum(s.weights.values()), 1.0, places=6)
        # signal-only weighting dominates
        high_signal = s.score(signal=1.0, bandwidth=0.0)
        low_signal = s.score(signal=0.0, bandwidth=1.0)
        assert high_signal > low_signal


# ═══════════════════════════════════════════════════════════════════════════
# Link + LinkManager
# ═══════════════════════════════════════════════════════════════════════════


class TestLinkManager(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = LinkManager()

    def test_register_and_get(self) -> None:
        self.mgr.register_new("eth0", link_type="ethernet", name="Eth", metric=1)
        link = self.mgr.get("eth0")
        assert link.id == "eth0"
        assert link.type == "ethernet"
        assert link.metric == 1

    def test_mark_up_down_transitions(self) -> None:
        self.mgr.register_new("w0")
        assert self.mgr.mark_down("w0")
        assert not self.mgr.get("w0").up
        assert self.mgr.mark_up("w0")
        assert self.mgr.get("w0").up
        # last_test timestamp updated on up
        assert self.mgr.get("w0").last_test > 0

    def test_best_link_by_score(self) -> None:
        self.mgr.register_new("slow", metric=0)
        self.mgr.register_new("fast", metric=1)
        signals = {
            "slow": {"signal": 0.3, "bandwidth": 0.2, "latency_ms": 130, "reliability": 0.5},
            "fast": {"signal": 0.9, "bandwidth": 0.9, "latency_ms": 20, "reliability": 0.95},
        }
        assert self.mgr.best_link(signals).id == "fast"

    def test_down_link_excluded_from_best(self) -> None:
        self.mgr.register_new("a", metric=0)
        self.mgr.register_new("b", metric=1)
        self.mgr.mark_down("a")
        best = self.mgr.best_link()
        assert best is not None
        assert best.id == "b"

    def test_best_link_none_when_all_down(self) -> None:
        self.mgr.register_new("a")
        self.mgr.register_new("b")
        self.mgr.mark_down("a")
        self.mgr.mark_down("b")
        assert self.mgr.best_link() is None

    def test_metric_breaks_equal_score_tie(self) -> None:
        self.mgr.register_new("primary", metric=0)
        self.mgr.register_new("backup", metric=5)
        # identical perfect signals → lower metric wins
        signals = {
            "primary": {"signal": 1, "bandwidth": 1, "latency_ms": 0, "reliability": 1},
            "backup": {"signal": 1, "bandwidth": 1, "latency_ms": 0, "reliability": 1},
        }
        assert self.mgr.best_link(signals).id == "primary"

    def test_test_all_uses_probe_fn(self) -> None:
        def probe(link: Link) -> bool:
            return link.id == "good"

        mgr = LinkManager(probe_fn=probe)
        mgr.register_new("good")
        mgr.register_new("bad")
        results = mgr.test_all()
        assert results["good"]
        assert not results["bad"]
        assert mgr.get("good").up
        assert not mgr.get("bad").up


# ═══════════════════════════════════════════════════════════════════════════
# Muxer — routing + fallback + stats
# ═══════════════════════════════════════════════════════════════════════════


class TestMuxer(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = LinkManager()
        self.mux = Muxer(manager=self.mgr)
        self.mgr.register_new("eth0", link_type="ethernet", metric=0)
        self.mgr.register_new("wifi0", link_type="wifi", metric=1)
        self.calls = []

    def _sink(self, link_id):
        def fn(data, **kw) -> str:
            self.calls.append((link_id, data, kw))
            return f"sent-{link_id}"

        return fn

    def test_routes_through_best_link(self) -> None:
        self.mux.attach_send("eth0", self._sink("eth0"))
        self.mux.attach_send("wifi0", self._sink("wifi0"))
        assert self.mux.route(b"hi") == "sent-eth0"  # lower metric primary
        assert self.calls[0][0] == "eth0"
        assert self.calls[0][1] == b"hi"

    def test_prefer_forces_selection(self) -> None:
        self.mux.attach_send("eth0", self._sink("eth0"))
        self.mux.attach_send("wifi0", self._sink("wifi0"))
        result = self.mux.route(b"x", prefer="wifi0")
        assert result == "sent-wifi0"

    def test_falls_back_when_primary_fails(self) -> None:
        def failing(data, **kw) -> Never:
            self.calls.append("eth0-fail")
            msg = "eth0 down"
            raise ConnectionError(msg)

        self.mux.attach_send("eth0", failing)
        self.mux.attach_send("wifi0", self._sink("wifi0"))
        result = self.mux.route(b"payload")
        assert result == "sent-wifi0"
        # eth0 marked down after failure
        assert not self.mgr.get("eth0").up
        # wifi0 routed as fallback
        assert self.calls[-1][0] == "wifi0"

    def test_fallback_count_incremented(self) -> None:
        def failing(data, **kw) -> Never:
            msg = "boom"
            raise OSError(msg)

        self.mux.attach_send("eth0", failing)
        self.mux.attach_send("wifi0", self._sink("wifi0"))
        self.mux.route(b"x")
        assert self.mux.fallback_count("wifi0") == 1
        assert self.mux.total_fallbacks == 1

    def test_stats_recorded_per_link(self) -> None:
        self.mux.attach_send("eth0", self._sink("eth0"))
        self.mux.attach_send("wifi0", self._sink("wifi0"))
        self.mux.route(b"1")
        self.mux.route(b"2")
        stats = self.mux.stats("eth0")
        assert stats["ok"] == 2
        assert stats["fail"] == 0
        assert self.mux.total_success == 2

    def test_all_links_fail_raises(self) -> None:
        def failing(data, **kw) -> Never:
            msg = "dead"
            raise ConnectionError(msg)

        self.mux.attach_send("eth0", failing)
        self.mux.attach_send("wifi0", failing)
        with pytest.raises(RuntimeError):
            self.mux.route(b"x")
        assert self.mux.total_failures == 2
        assert self.mux.total_fallbacks == 1
        assert not self.mgr.get("eth0").up
        assert not self.mgr.get("wifi0").up

    def test_no_links_raises(self) -> None:
        mux = Muxer(LinkManager())
        with pytest.raises(RuntimeError):
            mux.route(b"x")

    def test_task_kwarg_forwarded(self) -> None:
        def fn(data, task=None, **kw) -> str:
            self.calls.append((data, task))
            return "ok"

        self.mux.attach_send("eth0", fn)
        self.mux.route(b"d", task="my-task")
        assert self.calls[0] == (b"d", "my-task")

    def test_lifecycle_recovery(self) -> None:
        """Link goes down then recovers — routing resumes to it."""
        state = {"ok": True}

        def flaky(data, **kw) -> str:
            if state["ok"]:
                return "ok-eth"
            msg = "down"
            raise ConnectionError(msg)

        self.mux.attach_send("eth0", flaky)
        self.mux.attach_send("wifi0", self._sink("wifi0"))

        assert self.mux.route(b"1") == "ok-eth"
        state["ok"] = False
        assert self.mux.route(b"2") == "sent-wifi0"  # fell back
        # recovery
        self.mgr.mark_up("eth0")
        state["ok"] = True
        assert self.mux.route(b"3") == "ok-eth"  # back to primary


# ═══════════════════════════════════════════════════════════════════════════
# select_route (deterministic, side-effect free)
# ═══════════════════════════════════════════════════════════════════════════


class TestSelectRoute(unittest.TestCase):
    def test_none_when_all_down(self) -> None:
        links = [Link(id="a", up=False), Link(id="b", up=False)]
        assert select_route(links) is None

    def test_picks_highest_score(self) -> None:
        links = [
            Link(id="slow", up=True),
            Link(id="fast", up=True),
        ]
        signals = {
            "slow": {"signal": 0.2, "latency_ms": 140},
            "fast": {"signal": 0.9, "latency_ms": 10},
        }
        assert select_route(links, signals=signals).id == "fast"

    def test_prefer_wins_tie(self) -> None:
        links = [Link(id="a", up=True, metric=0), Link(id="b", up=True, metric=0)]
        signals = {
            "a": {"signal": 1, "latency_ms": 0},
            "b": {"signal": 1, "latency_ms": 0},
        }
        assert select_route(links, prefer="b", signals=signals).id == "b"

    def test_metric_breaks_tie(self) -> None:
        links = [
            Link(id="a", up=True, metric=9),
            Link(id="b", up=True, metric=1),
        ]
        signals = {
            "a": {"signal": 1, "latency_ms": 0},
            "b": {"signal": 1, "latency_ms": 0},
        }
        assert select_route(links, signals=signals).id == "b"


if __name__ == "__main__":
    unittest.main()
