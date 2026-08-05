"""ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module.

Wraps the standalone TRIAD FORGE hacker box (~/Desktop/TriadForge) into the ENI
Enterprise Platform so it boots HEALTHY, is discoverable by the kernel, and exposes a
facade for running security scans on LO's OWN targets and funneling findings back.

This module is a thin kernel service around the TriadForge engines. It intentionally
reuses the verified TriadForge package (web/source/llm engines + SARIF remediation)
rather than duplicating them. If the standalone package is not importable it degrades
gracefully to UNHEALTHY with an explanatory message (no crash).

Version: 1.0.0
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import EventBus, HealthStatus, Module, module

# Locate the standalone TriadForge package (verified location).
_TRIADFORGE = Path("/home/hunter/Desktop/TriadForge")
if str(_TRIADFORGE) not in sys.path:
    sys.path.insert(0, str(_TRIADFORGE))

logger = logging.getLogger("enterprise.triadforge")

_IMPORT_ERROR: Optional[str] = None
try:
    from triadforge.db import Store  # noqa: F401
    from triadforge.engine import persist_findings  # noqa: F401
    from triadforge.engines.web import WebEngine  # noqa: F401
    from triadforge.engines.source import SourceEngine  # noqa: F401
    from triadforge.engines.llm import LlmEngine  # noqa: F401
    from triadforge.engines.adversary import AdversaryEngine  # noqa: F401
    from triadforge.models import Target, TargetMode  # noqa: F401
    from triadforge.remediation import export_sarif, fix_snippet  # noqa: F401

    TRIADFORGE_AVAILABLE = True
except Exception as e:  # pragma: no cover - degrade gracefully
    TRIADFORGE_AVAILABLE = False
    _IMPORT_ERROR = str(e)


@module(name="triadforge", version="1.0.0")
class TriadForgeModule(Module):
    """
    Enterprise TriadForge Module — run black/grey/white security scans on LO's own
    targets, store findings in the TriadForge sqlite DB, export SARIF, and drive the
    remediation funnel.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._lock = threading.RLock()
        self._event_bus: Optional[EventBus] = None
        self._store = None
        self._runnable: bool = TRIADFORGE_AVAILABLE
        self._available: bool = TRIADFORGE_AVAILABLE

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            cfg = self._config or {}
            if not self._runnable:
                self._status = HealthStatus.UNHEALTHY
                logger.warning("TriadForge unavailable (%s)", _IMPORT_ERROR)
                return
            db_path = cfg.get("db_path") or str(Path(_TRIADFORGE) / "enterprise_triadforge.db")
            if self._store is None:
                self._store = Store(Path(db_path))
            self._status = HealthStatus.HEALTHY
            logger.info("TriadForge module initialized (db=%s)", db_path)

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._available and self._store is not None:
                return HealthStatus.HEALTHY
            return HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._status = HealthStatus.HEALTHY

    def set_event_bus(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    # ── Facade: scanning ──────────────────────────────────────────────────────
    def add_web_target(self, name: str, url: str, mode: str = "black",
                       auth_token: Optional[str] = None) -> int:
        return self._add_target(Target(
            name=name, kind="web", mode=TargetMode(mode), url=url,
            auth_token=auth_token, scope_ok=True))

    def add_source_target(self, name: str, source_dir: str) -> int:
        return self._add_target(Target(
            name=name, kind="source", mode=TargetMode.WHITE,
            source_dir=source_dir, scope_ok=True))

    def add_adversary_target(self, name: str, url: str,
                             profile: str = "balanced",
                             auth_path: Optional[str] = None,
                             model_path: Optional[str] = None,
                             content_path: Optional[str] = None) -> int:
        """Register a live site to attack with AI/agent vectors (deployed-gate test)."""
        notes = f"profile={profile}"
        if auth_path:
            notes += f",auth_path={auth_path}"
        if model_path:
            notes += f",model_path={model_path}"
        if content_path:
            notes += f",content_path={content_path}"
        return self._add_target(Target(
            name=name, kind="adversary", mode=TargetMode.BLACK, url=url,
            notes=notes, scope_ok=True))

    def _add_target(self, t: Target) -> int:
        self._require()
        return self._store.add_target(t)

    def run_scan(self, target_id: int) -> Dict[str, Any]:
        """Synchronously run a scan on a target; returns a summary dict."""
        self._require()
        target = self._store.get_target(target_id)
        if not target:
            return {"error": "target not found", "target_id": target_id}
        kind = target.get("kind", "web")
        engine_cls = {"web": WebEngine, "source": SourceEngine,
                      "llm": LlmEngine, "adversary": AdversaryEngine}.get(kind)
        if engine_cls is None:
            return {"error": f"unknown target kind {kind}"}
        scan_id = self._store.create_scan(target_id, kind, target.get("mode", "black"))
        self._store.update_scan(scan_id, status="running")
        # Rebuild Target from the dict (facade works on the DB layer).
        t = Target(**{k: v for k, v in target.items() if k != "id" or v is not None})
        t.id = target_id
        # Adversary engine reads profile from notes; keep notes intact.
        if kind == "adversary":
            t.notes = target.get("notes") or t.notes
        try:
            engine = engine_cls(self._store, t)
            coro = engine.run(scan_id, {})
            # Robust in BOTH contexts: run the sync engine coro in a dedicated
            # thread with its own event loop so it never clashes with a running
            # loop (Hermes async scope) or a fresh one (sync CLI).
            import concurrent.futures
            out: List[Any] = []

            def _run() -> None:
                out.append(asyncio.run(coro))

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                ex.submit(_run).result(timeout=300)
            findings = out[0] if out else []
            n = persist_findings(self._store, scan_id, findings)
            return {"scan_id": scan_id, "findings": n, "target_id": target_id}
        except Exception as e:  # pragma: no cover
            self._store.update_scan(scan_id, status="error", message=str(e))
            return {"scan_id": scan_id, "error": str(e), "target_id": target_id}

    def list_findings(self, scan_id: Optional[int] = None,
                      severity: Optional[str] = None) -> List[Dict[str, Any]]:
        self._require()
        return self._store.list_findings(scan_id=scan_id, severity=severity)

    def export_sarif(self, scan_id: Optional[int] = None) -> Dict[str, Any]:
        self._require()
        return export_sarif(self._store, scan_id=scan_id)

    def fix_snippet(self, rule_id: str) -> str:
        self._require()
        return fix_snippet(rule_id)

    def _require(self) -> None:
        if not self._available or self._store is None:
            raise RuntimeError(
                "TriadForge module not available/initialized (%s)" % (_IMPORT_ERROR or "uninitialized"))


def create_triadforge_module(config: Optional[Dict[str, Any]] = None) -> TriadForgeModule:
    return TriadForgeModule(config)


__all__ = ["TriadForgeModule", "create_triadforge_module", "TRIADFORGE_AVAILABLE"]
