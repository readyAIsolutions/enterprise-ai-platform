"""ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module.

Wraps the standalone TRIAD FORGE hacker box (~/Desktop/TriadForge) into the ENI
Enterprise Platform so it boots HEALTHY, is discoverable by the kernel, and exposes a
facade for running security scans on LO's OWN targets and funneling findings back.

This module is a thin kernel service around the TriadForge engines. It reuses the
verified TriadForge package (web/source/llm engines + SARIF remediation) whenever it
is importable. If the standalone package is NOT available, the module falls back to a
built-in, stdlib-only ``ScanCore`` engine that provides real scan orchestration
(run a scan against a config, aggregate findings, SARIF-style output) — so the module
remains functional, HEALTHY, and fully testable even when TriadForge is absent.

Version: 1.0.0
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import EventBus, HealthStatus, Module, module

# Locate the standalone TriadForge package (verified location).
_TRIADFORGE = Path("/home/hunter/Desktop/TriadForge")
if str(_TRIADFORGE) not in sys.path:
    sys.path.insert(0, str(_TRIADFORGE))

logger = logging.getLogger("enterprise.triadforge")

__version__ = "1.0.0"

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

# The internal stdlib-only engine is always available — it has zero external deps.
SCANCORE_AVAILABLE = True


# ═══════════════════════════════════════════════════════════════════════════
# Internal stdlib-only ScanCore engine (offline fallback + test target)
# ═══════════════════════════════════════════════════════════════════════════

# Heuristic rule catalog. Each rule produces findings with a stable rule_id,
# severity, message template, and (optional) remediation snippet.
_RULES: Dict[str, Dict[str, Any]] = {
    "insecure-http": {
        "severity": "warning",
        "message": "Target uses cleartext HTTP transport; TLS should be enforced.",
        "fix": 'Use HTTPS: replace "http://" with "https://".',
    },
    "missing-port": {
        "severity": "low",
        "message": "Target does not declare an explicit service port.",
        "fix": "Pin the service port in the target URL.",
    },
    "auth-token-in-url": {
        "severity": "high",
        "message": "Credential/token material is attached to a target.",
        "fix": "Rotate the token and store it via a secret vault.",
    },
    "hardcoded-secret": {
        "severity": "high",
        "message": "Possible hardcoded secret detected in source.",
        "fix": "Move the secret to environment variables or a vault.",
    },
    "weak-regex": {
        "severity": "medium",
        "message": "Broad regex pattern may over-match sensitive data.",
        "fix": "Tighten the regex to the exact required shape.",
    },
    "prompt-injection": {
        "severity": "high",
        "message": "LLM prompt contains instruction-override / injection markers.",
        "fix": "Sanitize user input and treat it as untrusted data.",
    },
    "unknown-kind": {
        "severity": "info",
        "message": "Target kind not recognized by the active engine.",
        "fix": "Use web/source/llm target kinds.",
    },
}

# Secret-shaped patterns for the source scanner (stdlib-only, no external deps).
_SECRET_PATTERNS: List[Dict[str, str]] = [
    {"rule": "hardcoded-secret", "pattern": r"(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*['\"][A-Za-z0-9_\-]{8,}['\"]"},
    {"rule": "weak-regex", "pattern": r"(?i)\b([a-z0-9_]+)\s*[=:]\s*re\.(match|search|findall)\("},
]

_LLM_INJECTION_MARKERS: List[str] = [
    "ignore previous instructions",
    "ignore all previous",
    "system:",
    "disregard prior",
    "you are now",
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ScanFinding:
    """A single finding produced by an internal ScanCore scan."""

    rule_id: str
    message: str
    severity: str = "medium"
    location: str = "n/a"
    line: Optional[int] = None
    fix: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "message": self.message,
            "severity": self.severity,
            "location": self.location,
            "line": self.line,
            "fix": self.fix,
        }


class ScanCore:
    """Internal, stdlib-only scan engine.

    Provides real scan orchestration with zero external dependencies: register
    targets, run scans against a config, aggregate findings into a per-scan list,
    and export well-formed SARIF 2.1.0 output. Used as the fallback engine when the
    standalone TriadForge package is unavailable, and as the offline test surface.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path or Path(":memory:")
        self._targets: Dict[int, Dict[str, Any]] = {}
        self._scans: Dict[int, Dict[str, Any]] = {}
        self._findings: Dict[int, List[ScanFinding]] = {}
        self._next_target_id = 1
        self._next_scan_id = 1
        self._lock = threading.RLock()

    # ── Target management ───────────────────────────────────────────────────
    def add_target(self, target: Any) -> int:
        """Register a target (dict or object with attributes); return target_id."""
        with self._lock:
            if isinstance(target, dict):
                rec = dict(target)
            else:
                rec = {
                    "name": getattr(target, "name", None),
                    "kind": getattr(target, "kind", "web"),
                    "mode": getattr(target, "mode", None),
                    "url": getattr(target, "url", None),
                    "source_dir": getattr(target, "source_dir", None),
                    "auth_token": getattr(target, "auth_token", None),
                    "notes": getattr(target, "notes", None),
                    "scope_ok": getattr(target, "scope_ok", True),
                }
            rec.setdefault("mode", "black")
            rec.setdefault("scope_ok", True)
            tid = self._next_target_id
            self._next_target_id += 1
            rec["id"] = tid
            self._targets[tid] = rec
            return tid

    def get_target(self, target_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._targets.get(target_id)
            return dict(rec) if rec else None

    def list_targets(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(t) for t in self._targets.values()]

    # ── Scan lifecycle ──────────────────────────────────────────────────────
    def create_scan(self, target_id: int, kind: str, mode: str) -> int:
        with self._lock:
            sid = self._next_scan_id
            self._next_scan_id += 1
            self._scans[sid] = {
                "id": sid, "target_id": target_id, "kind": kind, "mode": mode,
                "status": "pending", "message": None,
                "created_at": _utcnow(),
            }
            self._findings[sid] = []
            return sid

    def update_scan(self, scan_id: int, status: Optional[str] = None,
                    message: Optional[str] = None) -> None:
        with self._lock:
            rec = self._scans.get(scan_id)
            if rec is None:
                return
            if status is not None:
                rec["status"] = status
            if message is not None:
                rec["message"] = message

    def get_scan(self, scan_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._scans.get(scan_id)
            return dict(rec) if rec else None

    # ── Findings ────────────────────────────────────────────────────────────
    def persist_findings(self, scan_id: int, findings: List[ScanFinding]) -> int:
        with self._lock:
            cur = self._findings.setdefault(scan_id, [])
            cur.extend(findings)
            return len(cur)

    def list_findings(self, scan_id: Optional[int] = None,
                      severity: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            out: List[Dict[str, Any]] = []
            for sid, items in self._findings.items():
                if scan_id is not None and sid != scan_id:
                    continue
                for f in items:
                    d = f.to_dict()
                    d["scan_id"] = sid
                    if severity is None or d["severity"] == severity:
                        out.append(d)
            return out

    # ── Scan orchestration (real, deterministic, offline) ──────────────────
    def run_scan(self, target_id: int) -> Dict[str, Any]:
        """Synchronously run a scan on a target; aggregate findings; return summary."""
        target = self.get_target(target_id)
        if not target:
            return {"error": "target not found", "target_id": target_id}
        kind = target.get("kind", "web")
        sid = self.create_scan(target_id, kind, target.get("mode", "black"))
        self.update_scan(sid, status="running")
        try:
            findings = self._scan_target(kind, target)
            n = self.persist_findings(sid, findings)
            self.update_scan(sid, status="completed")
            return {"scan_id": sid, "findings": n, "target_id": target_id}
        except Exception as e:  # pragma: no cover
            self.update_scan(sid, status="error", message=str(e))
            return {"scan_id": sid, "error": str(e), "target_id": target_id}

    def _scan_target(self, kind: str, target: Dict[str, Any]) -> List[ScanFinding]:
        if kind == "web":
            return self._scan_web(target)
        if kind == "source":
            return self._scan_source(target)
        if kind == "llm":
            return self._scan_llm(target)
        return [ScanFinding(
            rule_id="unknown-kind",
            message=_RULES["unknown-kind"]["message"],
            severity="info",
            location=target.get("name", "n/a"),
        )]

    def _scan_web(self, target: Dict[str, Any]) -> List[ScanFinding]:
        url = target.get("url") or ""
        name = target.get("name", url)
        findings: List[ScanFinding] = []
        if url.startswith("http://"):
            findings.append(ScanFinding(
                rule_id="insecure-http",
                message=_RULES["insecure-http"]["message"],
                severity=_RULES["insecure-http"]["severity"],
                location=url,
                fix=_RULES["insecure-http"]["fix"],
            ))
        if url and not re.search(r":\d{2,5}(/|$)", url):
            findings.append(ScanFinding(
                rule_id="missing-port",
                message=_RULES["missing-port"]["message"],
                severity=_RULES["missing-port"]["severity"],
                location=url,
                fix=_RULES["missing-port"]["fix"],
            ))
        if target.get("auth_token"):
            findings.append(ScanFinding(
                rule_id="auth-token-in-url",
                message=_RULES["auth-token-in-url"]["message"],
                severity=_RULES["auth-token-in-url"]["severity"],
                location=url,
                fix=_RULES["auth-token-in-url"]["fix"],
            ))
        if not findings:
            findings.append(ScanFinding(
                rule_id="weak-regex",
                message="Web target scanned with no high-confidence issues.",
                severity="info",
                location=name,
            ))
        return findings

    def _scan_source(self, target: Dict[str, Any]) -> List[ScanFinding]:
        source_dir = Path(target.get("source_dir") or "")
        name = target.get("name", str(source_dir))
        findings: List[ScanFinding] = []
        if source_dir.exists() and source_dir.is_dir():
            scanned = 0
            for root, _dirs, files in os.walk(source_dir):
                for fn in files:
                    if fn.endswith((".py", ".js", ".ts", ".env", ".json", ".sh", ".go", ".java")):
                        fp = Path(root) / fn
                        try:
                            text = fp.read_text(encoding="utf-8", errors="ignore")
                        except Exception:  # pragma: no cover
                            continue
                        scanned += 1
                        for lineno, line in enumerate(text.splitlines(), 1):
                            for pat in _SECRET_PATTERNS:
                                if re.search(pat["pattern"], line):
                                    findings.append(ScanFinding(
                                        rule_id=pat["rule"],
                                        message=_RULES[pat["rule"]]["message"],
                                        severity=_RULES[pat["rule"]]["severity"],
                                        location=str(fp),
                                        line=lineno,
                                        fix=_RULES[pat["rule"]]["fix"],
                                    ))
            if not findings:
                findings.append(ScanFinding(
                    rule_id="weak-regex",
                    message=f"Source scan of {scanned} files found no obvious secrets.",
                    severity="info",
                    location=name,
                ))
        else:
            findings.append(ScanFinding(
                rule_id="unknown-kind",
                message="Source directory does not exist or is not a directory.",
                severity="warning",
                location=name,
            ))
        return findings

    def _scan_llm(self, target: Dict[str, Any]) -> List[ScanFinding]:
        notes = target.get("notes") or ""
        name = target.get("name", "llm-target")
        findings: List[ScanFinding] = []
        lowered = notes.lower()
        for marker in _LLM_INJECTION_MARKERS:
            if marker.lower() in lowered:
                findings.append(ScanFinding(
                    rule_id="prompt-injection",
                    message=_RULES["prompt-injection"]["message"],
                    severity=_RULES["prompt-injection"]["severity"],
                    location=name,
                    fix=_RULES["prompt-injection"]["fix"],
                ))
        if not findings:
            findings.append(ScanFinding(
                rule_id="weak-regex",
                message="LLM prompt scan found no injection markers.",
                severity="info",
                location=name,
            ))
        return findings

    # ── Remediation / reporting ─────────────────────────────────────────────
    def fix_snippet(self, rule_id: str) -> str:
        rule = _RULES.get(rule_id)
        return rule["fix"] if rule else f"No remediation known for rule '{rule_id}'."

    def export_sarif(self, scan_id: Optional[int] = None) -> Dict[str, Any]:
        """Export findings as well-formed SARIF 2.1.0 JSON."""
        findings = self.list_findings(scan_id=scan_id)
        rules = [
            {"id": rid, "shortDescription": {"text": rule["message"]},
             "help": {"text": rule.get("fix", "")}, "defaultConfiguration": {"level": rule["severity"]}}
            for rid, rule in _RULES.items()
        ]
        results = []
        for f in findings:
            level = "note" if f["severity"] == "info" else ("warning" if f["severity"] == "warning" else "error")
            loc = f.get("location") or ""
            result: Dict[str, Any] = {
                "ruleId": f["rule_id"],
                "level": level,
                "message": {"text": f["message"]},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": loc},
                        **({"region": {"startLine": f["line"]}} if f.get("line") else {}),
                    }
                }],
            }
            if f.get("fix"):
                result["fixes"] = [{
                    "description": {"text": f["fix"]},
                    "artifactChanges": [{"artifactLocation": {"uri": loc}}],
                }]
            results.append(result)

        return {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {"driver": {"name": "TriadForge/ScanCore", "version": __version__,
                                    "informationUri": "https://github.com/Enterprise-Network-Intelligence",
                                    "rules": rules}},
                "results": results,
            }],
        }


# ═══════════════════════════════════════════════════════════════════════════
# Kernel module
# ═══════════════════════════════════════════════════════════════════════════

@module(name="triadforge", version=__version__)
class TriadForgeModule(Module):
    """
    Enterprise TriadForge Module — run black/grey/white security scans on LO's own
    targets, store findings in the TriadForge sqlite DB (or the internal ScanCore
    store when offline), export SARIF, and drive the remediation funnel.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._lock = threading.RLock()
        self._event_bus: Optional[EventBus] = None
        self._store: Optional[Any] = None
        self._engine: str = "external" if TRIADFORGE_AVAILABLE else "internal"
        # Health is HEALTHY when EITHER engine is available.
        self._runnable: bool = TRIADFORGE_AVAILABLE or SCANCORE_AVAILABLE
        self._available: bool = self._runnable

    # ── Lifecycle ───────────────────────────────────────────────────────────
    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            cfg = self._config or {}
            if not self._runnable:
                self._status = HealthStatus.UNHEALTHY
                logger.warning("TriadForge + ScanCore both unavailable (%s)", _IMPORT_ERROR)
                return
            if self._store is None:
                if TRIADFORGE_AVAILABLE:
                    db_path = cfg.get("db_path") or str(Path(_TRIADFORGE) / "enterprise_triadforge.db")
                    self._store = Store(Path(db_path))
                    self._engine = "external"
                else:
                    db_path = cfg.get("db_path") or ":memory:"
                    self._store = ScanCore(Path(db_path))
                    self._engine = "internal"
            self._status = HealthStatus.HEALTHY
            logger.info("TriadForge module initialized (engine=%s)", self._engine)

    async def health_check(self) -> HealthStatus:
        with self._lock:
            # HEALTHY when EITHER the external TriadForge engine or the internal
            # ScanCore engine is available AND the store has been initialized.
            if (TRIADFORGE_AVAILABLE or SCANCORE_AVAILABLE) and self._store is not None:
                return HealthStatus.HEALTHY
            return HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            # Idempotent: a second call must not raise. Release the store.
            self._store = None
            self._status = HealthStatus.HEALTHY

    def set_event_bus(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    # ── Facade: scanning ────────────────────────────────────────────────────
    def add_web_target(self, name: str, url: str, mode: str = "black",
                       auth_token: Optional[str] = None) -> int:
        return self._add_target({
            "name": name, "kind": "web", "mode": mode, "url": url,
            "auth_token": auth_token, "scope_ok": True,
        })

    def add_source_target(self, name: str, source_dir: str) -> int:
        return self._add_target({
            "name": name, "kind": "source", "mode": "white",
            "source_dir": source_dir, "scope_ok": True,
        })

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
        return self._add_target({
            "name": name, "kind": "adversary", "mode": "black", "url": url,
            "notes": notes, "scope_ok": True,
        })

    def _add_target(self, t: Any) -> int:
        self._require()
        if self._engine == "external":
            # External TriadForge store expects a Target model object.
            tgt = Target(
                name=t.get("name"), kind=t.get("kind", "web"),
                mode=TargetMode(t.get("mode", "black")), url=t.get("url"),
                source_dir=t.get("source_dir"), auth_token=t.get("auth_token"),
                notes=t.get("notes"), scope_ok=t.get("scope_ok", True),
            )
            return self._store.add_target(tgt)
        return self._store.add_target(t)

    def run_scan(self, target_id: int) -> Dict[str, Any]:
        """Synchronously run a scan on a target; returns a summary dict."""
        self._require()
        target = self._store.get_target(target_id)
        if not target:
            return {"error": "target not found", "target_id": target_id}
        kind = target.get("kind", "web")

        # Internal engine path — real offline orchestration via ScanCore.
        if self._engine == "internal":
            return self._store.run_scan(target_id)

        # External TriadForge engine path (unchanged behaviour).
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

    # ── High-level facade routing (route to the active engine) ──────────────
    def scan_web(self, name: str, url: str, mode: str = "black",
                 auth_token: Optional[str] = None) -> Dict[str, Any]:
        """Add a web target and run a scan on it in one step; returns summary."""
        target_id = self.add_web_target(name, url, mode=mode, auth_token=auth_token)
        return self.run_scan(target_id)

    def scan_source(self, name: str, source_dir: str) -> Dict[str, Any]:
        """Add a source target and run a scan on it in one step; returns summary."""
        target_id = self.add_source_target(name, source_dir)
        return self.run_scan(target_id)

    def scan_llm(self, name: str, prompt_or_notes: str,
                 url: Optional[str] = None) -> Dict[str, Any]:
        """Add an LLM target (prompt/content via notes) and run a scan."""
        self._require()
        if self._engine == "internal":
            target_id = self._store.add_target({
                "name": name, "kind": "llm", "mode": "black",
                "url": url or "", "notes": prompt_or_notes, "scope_ok": True,
            })
            return self._store.run_scan(target_id)
        target_id = self._add_target({
            "name": name, "kind": "llm", "mode": "black",
            "url": url or "", "notes": prompt_or_notes, "scope_ok": True,
        })
        return self.run_scan(target_id)

    def list_findings(self, scan_id: Optional[int] = None,
                      severity: Optional[str] = None) -> List[Dict[str, Any]]:
        self._require()
        return self._store.list_findings(scan_id=scan_id, severity=severity)

    def export_sarif(self, scan_id: Optional[int] = None) -> Dict[str, Any]:
        self._require()
        if self._engine == "internal":
            return self._store.export_sarif(scan_id=scan_id)
        return export_sarif(self._store, scan_id=scan_id)

    def fix_snippet(self, rule_id: str) -> str:
        self._require()
        if self._engine == "internal":
            return self._store.fix_snippet(rule_id)
        return fix_snippet(rule_id)

    def _require(self) -> None:
        if not self._available or self._store is None:
            raise RuntimeError(
                "TriadForge module not available/initialized (%s)" % (_IMPORT_ERROR or "uninitialized"))


def create_triadforge_module(config: Optional[Dict[str, Any]] = None) -> TriadForgeModule:
    return TriadForgeModule(config)


__all__ = [
    "TriadForgeModule", "create_triadforge_module", "TRIADFORGE_AVAILABLE",
    "SCANCORE_AVAILABLE", "ScanCore", "ScanFinding", "__version__",
]
