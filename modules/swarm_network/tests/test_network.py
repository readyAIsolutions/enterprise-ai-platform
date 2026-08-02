"""Tests for Swarm Network Optimization OS."""
import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from enterprise.modules.swarm_network import (
    SwarmNetworkBridge,
    NetworkHealth,
    WiFiReader,
    get_aggressive_concurrency,
    get_sustained_rate,
    get_burst_capacity,
)


class TestConcurrencyTiers(unittest.TestCase):
    """Verify aggressive concurrency tier calculations."""

    def test_tier_80(self):
        self.assertEqual(get_aggressive_concurrency(-47), 80)

    def test_tier_70(self):
        self.assertEqual(get_aggressive_concurrency(-50), 70)

    def test_tier_60(self):
        self.assertEqual(get_aggressive_concurrency(-54), 60)

    def test_tier_50(self):
        self.assertEqual(get_aggressive_concurrency(-58), 50)

    def test_tier_40(self):
        self.assertEqual(get_aggressive_concurrency(-63), 40)

    def test_tier_25(self):
        self.assertEqual(get_aggressive_concurrency(-69), 25)

    def test_tier_15(self):
        self.assertEqual(get_aggressive_concurrency(-74), 15)

    def test_tier_min(self):
        self.assertEqual(get_aggressive_concurrency(-85), 8)

    def test_turbo_mode(self):
        normal = get_aggressive_concurrency(-58, turbo_mode=False)
        turbo = get_aggressive_concurrency(-58, turbo_mode=True)
        self.assertEqual(normal, 50)
        self.assertEqual(turbo, 62)  # 50 * 1.25

    def test_sustained_rate(self):
        self.assertAlmostEqual(get_sustained_rate(50), 30.0)

    def test_burst_capacity(self):
        self.assertEqual(get_burst_capacity(50), 120)


class TestNetworkHealth(unittest.TestCase):
    """NetworkHealth dataclass."""

    def test_healthy(self):
        h = NetworkHealth(healthy=True, signal_dbm=-55, max_concurrency=60,
                          sustained_req_per_sec=36.0, burst_capacity=144,
                          turbocharger_running=True)
        self.assertTrue(h.healthy)
        self.assertEqual(h.max_concurrency, 60)

    def test_recommendations(self):
        h = NetworkHealth(healthy=False, signal_dbm=-80, max_concurrency=8,
                          sustained_req_per_sec=5.0, burst_capacity=20,
                          turbocharger_running=False,
                          recommendations=["Signal critically weak"])
        self.assertFalse(h.healthy)
        self.assertEqual(len(h.recommendations), 1)


class TestSwarmNetworkBridge(unittest.TestCase):
    """Bridge integration tests."""

    def test_bridge_creation(self):
        bridge = SwarmNetworkBridge()
        self.assertIsNotNone(bridge)
        self.assertFalse(bridge._started)

    def test_initialize(self):
        bridge = SwarmNetworkBridge()
        asyncio.run(bridge.initialize())
        self.assertTrue(bridge._started)

    def test_health_check(self):
        bridge = SwarmNetworkBridge()
        asyncio.run(bridge.initialize())
        health = asyncio.run(bridge.health_check())
        self.assertIsInstance(health, NetworkHealth)
        self.assertIsInstance(health.max_concurrency, int)
        self.assertGreater(health.max_concurrency, 0)

    def test_turbo_mode_toggle(self):
        bridge = SwarmNetworkBridge()
        asyncio.run(bridge.initialize())
        normal = bridge.max_concurrency
        turbo = bridge.enable_turbo()
        self.assertGreaterEqual(turbo, normal)
        back = bridge.disable_turbo()
        self.assertEqual(back, normal)

    def test_status_dict(self):
        bridge = SwarmNetworkBridge()
        asyncio.run(bridge.initialize())
        status = bridge.status
        self.assertIn("signal_dbm", status)
        self.assertIn("concurrency", status)
        self.assertIn("turbocharger_running", status)
        self.assertIn("turbo_tier", status)

    def test_shutdown(self):
        bridge = SwarmNetworkBridge()
        asyncio.run(bridge.initialize())
        asyncio.run(bridge.shutdown())
        self.assertFalse(bridge._started)


class TestWiFiReader(unittest.TestCase):
    """WiFiReader low-level tests."""

    def test_reader_creation(self):
        reader = WiFiReader()
        self.assertEqual(reader.interface, "wlp4s0")
        self.assertEqual(reader.signal_dbm, -60)

    def test_read_signal(self):
        reader = WiFiReader()
        signal = reader.read_signal()
        self.assertLess(signal, 0)  # dBm is always negative

    def test_check_turbocharger(self):
        reader = WiFiReader()
        reader.turbo_port = 8922
        running = reader.check_turbocharger()
        # May or may not be running — just verify it doesn't crash
        self.assertIsInstance(running, bool)

    def test_get_concurrency(self):
        reader = WiFiReader()
        c = reader.get_concurrency()
        self.assertGreater(c, 0)


if __name__ == "__main__":
    unittest.main()