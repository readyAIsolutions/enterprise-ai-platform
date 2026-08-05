"""
swarm_network.mux — Connection Multiplexing & Scoring
=====================================================
Master-class connection multiplexer with graceful automatic fallback.

Provides:
  - Link            : a single connection (id, type, name, metric, up, last_test)
  - ConnectionScorer: score a link 0-100 from signal/bandwidth/latency/reliability
  - LinkManager     : register/update/test links, mark up/down, best_link()
  - Muxer           : route() picks the best UP link and auto-falls-back on failure
  - select_route    : deterministic tie-break route selection

Stdlib only.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

__all__ = [
    "Link",
    "ConnectionScorer",
    "LinkManager",
    "Muxer",
    "select_route",
    "MUX_NOT_AVAILABLE",
]

# Sentinel returned by route() when no link is up.
MUX_NOT_AVAILABLE = None


# ═══════════════════════════════════════════════════════════════════════════
# Link
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Link:
    """A single routable connection.

    Attributes:
        id:       Stable identifier for the link (unique within a LinkManager).
        type:     Link type, e.g. 'wifi', 'ethernet', 'cellular', 'vpn', 'proxy'.
        name:     Human-readable name.
        metric:   Intrinsic priority (lower = preferred). Used as a tie-break
                  AFTER score so admins can bias equal-score links.
        up:       Whether the link is currently considered reachable.
        last_test: Monotonic timestamp of the last successful test (0 = never).
    """

    id: str
    type: str = "wifi"
    name: str = ""
    metric: int = 0
    up: bool = True
    last_test: float = 0.0

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.id


# ═══════════════════════════════════════════════════════════════════════════
# ConnectionScorer
# ═══════════════════════════════════════════════════════════════════════════

class ConnectionScorer:
    """Score a link 0-100 from weighted signal/bandwidth/latency/reliability.

    Signals are all *injectable* so tests and callers can drive the scorer
    deterministically without real hardware. Each component is normalised to
    0-100, then combined with the configured weights.

    Signals (each 0-1 normalised internally):
        signal:      link quality / signal strength, 0.0 (dead) .. 1.0 (perfect)
        bandwidth:   throughput as a fraction of the link's potential, 0..1
        latency:     FRACTION OF BUDGET used; 0.0 = no latency, 1.0 = at/over budget
        reliability: fraction of probes that succeeded, 0..1
    """

    DEFAULT_WEIGHTS = {
        "signal": 0.25,
        "bandwidth": 0.25,
        "latency": 0.20,
        "reliability": 0.30,
    }

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        latency_budget_ms: float = 150.0,
    ) -> None:
        self.weights = dict(weights or self.DEFAULT_WEIGHTS)
        self.latency_budget_ms = float(latency_budget_ms)
        # Normalise weights so they sum to 1.0.
        total = sum(self.weights.values()) or 1.0
        self.weights = {k: v / total for k, v in self.weights.items()}

    # -- individual component scores (0-100) -------------------------------

    @staticmethod
    def _clip(x: float) -> float:
        return max(0.0, min(1.0, float(x)))

    def score_signal(self, signal: float) -> float:
        return self._clip(signal) * 100.0

    def score_bandwidth(self, bandwidth: float) -> float:
        return self._clip(bandwidth) * 100.0

    def score_latency(self, latency_ms: float) -> float:
        # Lower latency is better. At/over budget → 0; 0ms → 100.
        if latency_ms <= 0:
            return 100.0
        frac = min(1.0, latency_ms / self.latency_budget_ms)
        return (1.0 - frac) * 100.0

    def score_reliability(self, reliability: float) -> float:
        return self._clip(reliability) * 100.0

    # -- combined score ----------------------------------------------------

    def score(
        self,
        signal: float = 1.0,
        bandwidth: float = 1.0,
        latency_ms: float = 0.0,
        reliability: float = 1.0,
    ) -> float:
        """Return a combined score in [0, 100]."""
        components = {
            "signal": self.score_signal(signal),
            "bandwidth": self.score_bandwidth(bandwidth),
            "latency": self.score_latency(latency_ms),
            "reliability": self.score_reliability(reliability),
        }
        score = 0.0
        for name, weight in self.weights.items():
            score += components.get(name, 0.0) * weight
        return round(max(0.0, min(100.0, score)), 2)


# ═══════════════════════════════════════════════════════════════════════════
# LinkManager
# ═══════════════════════════════════════════════════════════════════════════

class LinkManager:
    """Register, update, and probe links; pick the best one by score."""

    def __init__(
        self,
        scorer: Optional[ConnectionScorer] = None,
        probe_fn: Optional[Callable[[Link], bool]] = None,
    ) -> None:
        self.scorer = scorer or ConnectionScorer()
        self.probe_fn = probe_fn
        self._links: Dict[str, Link] = {}
        self._lock = threading.RLock()

    # -- registration ------------------------------------------------------

    def register(self, link: Link) -> Link:
        """Register (or replace) a link. Returns the stored link."""
        with self._lock:
            # Preserve metric tie-break and up-state on replace.
            self._links[link.id] = link
            return link

    def register_new(
        self,
        link_id: str,
        link_type: str = "wifi",
        name: str = "",
        metric: int = 0,
        up: bool = True,
    ) -> Link:
        return self.register(
            Link(id=link_id, type=link_type, name=name, metric=metric, up=up)
        )

    def unregister(self, link_id: str) -> Optional[Link]:
        with self._lock:
            return self._links.pop(link_id, None)

    def get(self, link_id: str) -> Optional[Link]:
        with self._lock:
            return self._links.get(link_id)

    def links(self) -> List[Link]:
        with self._lock:
            return list(self._links.values())

    # -- state transitions -------------------------------------------------

    def mark_up(self, link_id: str) -> bool:
        link = self.get(link_id)
        if link is None:
            return False
        link.up = True
        link.last_test = time.monotonic()
        return True

    def mark_down(self, link_id: str) -> bool:
        link = self.get(link_id)
        if link is None:
            return False
        link.up = False
        return True

    def test(self, link_id: str) -> bool:
        """Probe a link using probe_fn (or a basic check), update up-state."""
        link = self.get(link_id)
        if link is None:
            return False
        ok = bool(self.probe_fn(link)) if self.probe_fn else True
        link.up = ok
        if ok:
            link.last_test = time.monotonic()
        return ok

    def test_all(self) -> Dict[str, bool]:
        results = {}
        for link in self.links():
            results[link.id] = self.test(link.id)
        return results

    # -- scoring & selection ----------------------------------------------

    def score_link(self, link: Link, **signals) -> float:
        """Score a specific link. Provider signals override defaults."""
        if not link.up:
            return 0.0
        sig = signals.pop("signal", 1.0)
        bw = signals.pop("bandwidth", 1.0)
        lat = signals.pop("latency_ms", 0.0)
        rel = signals.pop("reliability", 1.0)
        return self.scorer.score(signal=sig, bandwidth=bw, latency_ms=lat, reliability=rel)

    def best_link(
        self,
        signals: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> Optional[Link]:
        """Return the best UP link by score (lower metric breaks ties).

        ``signals`` maps link_id -> {signal, bandwidth, latency_ms, reliability}
        and lets callers supply per-link provider data. Links without an entry
        default to perfect signals.
        """
        signals = signals or {}
        best: Optional[Link] = None
        best_score = -1.0
        for link in self.links():
            if not link.up:
                continue
            score = self.score_link(link, **signals.get(link.id, {}))
            if score > best_score or (
                score == best_score and (best is None or link.metric < best.metric)
            ):
                best = link
                best_score = score
        return best


# ═══════════════════════════════════════════════════════════════════════════
# Muxer
# ═══════════════════════════════════════════════════════════════════════════

class Muxer:
    """Route through the best UP link, auto-falling back on failure.

    ``route()`` resolves the preferred target to the best UP link, invokes the
    link's send function, and — on failure — marks that link down and retries
    the next-best link automatically, until a send succeeds or no link remains.
    """

    def __init__(
        self,
        manager: Optional[LinkManager] = None,
        send_fns: Optional[Dict[str, Callable[..., object]]] = None,
        scorer: Optional[ConnectionScorer] = None,
    ) -> None:
        self.manager = manager or LinkManager(scorer=scorer)
        self.send_fns: Dict[str, Callable[..., object]] = dict(send_fns or {})
        self._stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"ok": 0, "fail": 0, "fallback": 0}
        )
        self.total_fallbacks = 0
        self.total_routes = 0
        self.total_success = 0
        self.total_failures = 0
        self._lock = threading.RLock()

    # -- wiring ------------------------------------------------------------

    def attach_send(self, link_id: str, fn: Callable[[object], object]) -> None:
        self.send_fns[link_id] = fn

    def stats(self, link_id: Optional[str] = None) -> Dict:
        with self._lock:
            if link_id is not None:
                return dict(self._stats[link_id])
            return {k: dict(v) for k, v in self._stats.items()}

    def fallback_count(self, link_id: Optional[str] = None) -> int:
        """Number of times a link was used as a fallback target."""
        with self._lock:
            if link_id is not None:
                return self._stats[link_id]["fallback"]
            return sum(v["fallback"] for v in self._stats.values())

    # -- routing -----------------------------------------------------------

    def resolve_order(self, prefer: Optional[str] = None, **signals) -> List[Link]:
        """Deterministic candidate order: preferred first, then by score, then metric."""
        scored = []
        for link in self.manager.links():
            if not link.up:
                continue
            score = self.manager.score_link(link, **signals.get(link.id, {}))
            scored.append((link, score, link.metric))
        # Preferred link bubbles to the front.
        scored.sort(key=lambda t: (0 if t[0].id == prefer else 1, -t[1], t[2]))
        return [link for link, _, _ in scored]

    def route(
        self,
        data: object = b"",
        prefer: Optional[str] = None,
        task: Optional[str] = None,
        **signals,
    ) -> object:
        """Route ``data`` through the best UP link, auto-falling back on failure.

        Returns the send-fn return value, or MUX_NOT_AVAILABLE if every link
        failed. Raises RuntimeError if no link is even configured/registered.
        """
        with self._lock:
            self.total_routes += 1
            order = self.resolve_order(prefer=prefer, **signals)
            if not order:
                raise RuntimeError("No link available to route")

            last_error: Optional[Exception] = None
            for index, link in enumerate(order):
                fn = self.send_fns.get(link.id)
                attempt_label = "preferred" if (index == 0 and link.id == prefer) else (
                    "primary" if index == 0 else "fallback"
                )
                try:
                    if fn is None:
                        # No sender wired — treat a configured, UP link as routable
                        # and pass the payload straight through.
                        self._stats[link.id]["ok"] += 1
                        self.total_success += 1
                        return data
                    if task is not None:
                        result = fn(data, task=task)
                    else:
                        result = fn(data)
                    self._stats[link.id]["ok"] += 1
                    self.total_success += 1
                    return result
                except Exception as exc:  # noqa: BLE001 - fallback on any failure
                    last_error = exc
                    self.manager.mark_down(link.id)
                    self._stats[link.id]["fail"] += 1
                    self.total_failures += 1
                    if index + 1 < len(order):
                        self._stats[order[index + 1].id]["fallback"] += 1
                        self.total_fallbacks += 1

            # All links failed.
            if last_error is not None:
                raise RuntimeError(f"All links failed, last error: {last_error}") from last_error
            return MUX_NOT_AVAILABLE


def select_route(
    candidates: List[Link],
    prefer: Optional[str] = None,
    signals: Optional[Dict[str, Dict[str, float]]] = None,
    scorer: Optional[ConnectionScorer] = None,
) -> Optional[Link]:
    """Deterministic, side-effect-free route selection over a list of links.

    Only UP links are considered. The preferred link (if UP) wins outright on
    a perfect score tie; otherwise the highest score wins, with the lower
    ``metric`` breaking equal scores, then alphabetical id as a final
    deterministic tie-break.

    Returns the winning Link or None if no candidate is UP.
    """
    scorer = scorer or ConnectionScorer()
    signals = signals or {}
    up = [l for l in candidates if l.up]
    if not up:
        return None

    best: Optional[Link] = None
    best_score = -1.0
    for link in up:
        sig = signals.get(link.id, {})
        score = scorer.score(
            signal=sig.get("signal", 1.0),
            bandwidth=sig.get("bandwidth", 1.0),
            latency_ms=sig.get("latency_ms", 0.0),
            reliability=sig.get("reliability", 1.0),
        )
        if score > best_score or (
            score == best_score
            and (
                best is None
                or (link.id == prefer)
                or (best.id != prefer and link.metric < best.metric)
                or (best.id != prefer and link.metric == best.metric and link.id < best.id)
            )
        ):
            best = link
            best_score = score
    return best
