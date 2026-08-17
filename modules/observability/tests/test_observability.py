"""Tests for the observability (live fleet health + Prometheus) module."""
from __future__ import annotations

import asyncio
import socket

import pytest

from enterprise.modules.observability import FleetHealthAggregator


def _free_port() -> int:
    """Return an unbound port number (bound then closed)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _fake_probe(results):
    def probe(host, port, timeout=1.0):
        return results.get((host, port), False)
    return probe


def test_tcp_probe_up_and_down():
    live_port = _free_port()
    # bind a listener on that port so it's genuinely up
    ls = socket.socket()
    ls.bind(("127.0.0.1", live_port))
    ls.listen(1)
    try:
        agg = FleetHealthAggregator(services=[])
        assert agg._probe("127.0.0.1", live_port) is True
    finally:
        ls.close()
    # unbound port -> down
    assert agg._probe("127.0.0.1", 59999) is False


def test_snapshot_counts_up_down():
    fake = _fake_probe({
        ("127.0.0.1", 9001): True,
        ("127.0.0.1", 9002): False,
    })
    agg = FleetHealthAggregator(registry=None,
                                services=[("a", "127.0.0.1", 9001),
                                          ("b", "127.0.0.1", 9002)],
                                probe=fake)
    snap = agg.snapshot()
    assert snap["total"] == 2
    assert snap["up"] == 1
    assert snap["down"] == 1
    assert len(snap["entities"]) == 2


def test_prometheus_format():
    fake = _fake_probe({("127.0.0.1", 1): True, ("127.0.0.1", 2): False})
    agg = FleetHealthAggregator(registry=None,
                                services=[("a", "127.0.0.1", 1),
                                          ("b", "127.0.0.1", 2)],
                                probe=fake)
    txt = agg.prometheus_text()
    assert 'eni_entity_up{name="a"' in txt
    assert 'eni_entity_up{name="b",kind="service"} 0' in txt
    assert "eni_entities_total 2" in txt
    assert "eni_entities_up 1" in txt


def test_module_health_check():
    from enterprise.modules.observability import create_observability_module
    mod = create_observability_module({})
    asyncio.run(mod.initialize())
    assert mod.aggregator is not None
    snap = mod.snapshot()
    assert "ts" in snap and "entities" in snap