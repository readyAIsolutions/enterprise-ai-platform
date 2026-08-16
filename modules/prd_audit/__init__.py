"""prd_audit — PRD-gated build workflow: write the PRD, audit it with a second
instance, then gate execution until it clears a threshold. Grounded in
JEVanClief's "I'm Building a Custom Front End for Claude Code" (J2GLzkaUrBc).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .prd_audit import (
    AuditFinding,
    AuditReport,
    AuditSeverity,
    Auditor,
    GateDecision,
    PrdDocument,
    PrdGate,
    PrdGateBlocked,
    PrdValidator,
    Task,
    audit_prd,
)

logger = logging.getLogger("eni.prd_audit")
__version__ = "1.0.0"

__all__ = [
    "__version__",
    "PrdAuditModule",
    "create_prd_audit_module",
    # core
    "PrdDocument",
    "Task",
    "PrdValidator",
    "Auditor",
    "PrdGate",
    "audit_prd",
    # types
    "AuditFinding",
    "AuditReport",
    "AuditSeverity",
    "GateDecision",
    "PrdGateBlocked",
]


@module(
    name="prd_audit",
    version="1.0.0",
    config_defaults={
        # Gate threshold: an unsound PRD blocks execution until revised.
        "max_errors": 0,
        "max_warnings": 10,
        "min_score": 0.6,
    },
)
class PrdAuditModule(Module):
    """Enterprise facade for the PRD-gated workflow.

    Lifecycle: ``initialize()`` -> HEALTHY on success, UNHEALTHY (+ re-raise)
    on failure.  When an event bus is wired via ``set_event_bus`` (never
    assumed), audit/gate events are published defensively — a missing or
    failing bus never breaks a call.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus = None  # type: ignore[assignment]
        self._ready: bool = False
        self._gate: PrdGate = PrdGate(
            max_errors=int(self.config.get("max_errors", 0)),
            max_warnings=int(self.config.get("max_warnings", 10)),
            min_score=float(self.config.get("min_score", 0.6)),
        )

    # -- lifecycle ----------------------------------------------------------

    async def initialize(self) -> None:
        try:
            # rebuild the gate from config; validate threshold inputs up front
            self._gate = PrdGate(
                max_errors=int(self.config.get("max_errors", 0)),
                max_warnings=int(self.config.get("max_warnings", 10)),
                min_score=float(self.config.get("min_score", 0.6)),
            )
            self._ready = True
            self.status = HealthStatus.HEALTHY
            logger.info("prd_audit module initialized")
        except Exception as exc:  # noqa: BLE001 - lifecycle robustness
            self._ready = False
            self.status = HealthStatus.UNHEALTHY
            logger.exception("prd_audit initialize failed")
            raise exc

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self._ready else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self._ready = False
        self.status = HealthStatus.STOPPING
        logger.info("prd_audit module shutting down")

    def set_event_bus(self, event_bus) -> None:  # type: ignore[no-untyped-def]
        self._event_bus = event_bus

    # -- facade -------------------------------------------------------------

    def parse_prd(self, markdown: str) -> PrdDocument:
        """Parse a PRD markdown document into a :class:`PrdDocument`."""
        self._ensure_ready()
        doc = PrdDocument.from_markdown(markdown)
        self._emit("prd_audit.prd.parsed", {"title": doc.title, "complete": doc.is_complete})
        return doc

    def audit(self, document: PrdDocument) -> Dict[str, Any]:
        """Run the second-instance auditor over a PRD (deterministic)."""
        self._ensure_ready()
        report = self._gate.validator.validate(document)
        self._emit("prd_audit.audit.done", report.to_dict())
        return report.to_dict()

    def audit_markdown(self, markdown: str) -> Dict[str, Any]:
        """Parse and audit a PRD in one call."""
        self._ensure_ready()
        report = audit_prd(markdown, validator=self._gate.validator)
        self._emit("prd_audit.audit.done", report.to_dict())
        return report.to_dict()

    def gate(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate an audit report dict against the gate threshold.

        Returns a decision dict.  A blocking failure is surfaced via
        ``approved=False`` (never raises across the module boundary so the
        facade stays non-throwing); the strict form is :meth:`gate_document`.
        """
        self._ensure_ready()
        decision = _report_from_dict(report)
        self._emit("prd_audit.gate.evaluated", {"approved": decision.approved})
        return {
            "approved": decision.approved,
            "score": decision.score,
            "errors": decision.errors,
            "warnings": decision.warnings,
            "reason": decision.reason,
        }

    def gate_document(self, document: PrdDocument) -> Dict[str, Any]:
        """Audit + gate a document, blocking (raising) if it fails."""
        self._ensure_ready()
        decision = self._gate.enforce_document(document)
        self._emit(
            "prd_audit.gate.passed",
            {"title": document.title, "score": decision.score},
        )
        return {
            "approved": True,
            "score": decision.score,
            "errors": decision.errors,
            "warnings": decision.warnings,
            "reason": decision.reason,
        }

    def gate_markdown(self, markdown: str) -> Dict[str, Any]:
        """Parse, audit, and gate a PRD markdown document end-to-end."""
        self._ensure_ready()
        decision = self._gate.enforce_document(PrdDocument.from_markdown(markdown))
        self._emit("prd_audit.gate.passed", {"score": decision.score})
        return {
            "approved": True,
            "score": decision.score,
            "errors": decision.errors,
            "warnings": decision.warnings,
            "reason": decision.reason,
        }

    # -- helpers ------------------------------------------------------------

    def _ensure_ready(self) -> None:
        if not self._ready:
            raise RuntimeError("prd_audit module is not initialized")

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        bus = self._event_bus
        if bus is None:
            return
        try:
            bus.publish(
                Event.create(
                    topic=topic,
                    source="prd_audit",
                    payload=payload,
                )
            )
        except Exception:  # noqa: BLE001 - publishing must never break a call
            logger.warning("failed to publish event %s", topic, exc_info=True)


def _report_from_dict(data: Dict[str, Any]) -> GateDecision:
    """Rebuild a :class:`GateDecision` from a gate() call's input dict."""
    report = AuditReport(
        document_title=str(data.get("title") or data.get("document_title") or "PRD"),
        findings=[
            AuditFinding(
                code=str(f.get("code", "UNKNOWN")),
                severity=_sev(f.get("severity")),
                section=str(f.get("section", "document")),
                message=str(f.get("message", "")),
                suggestion=str(f.get("suggestion", "")),
            )
            for f in (data.get("findings") or [])
        ],
    )
    return PrdGate().evaluate(report)


def _sev(name: Any) -> AuditSeverity:
    try:
        return AuditSeverity[name.upper()]
    except Exception:  # noqa: BLE001
        return AuditSeverity.ERROR


def create_prd_audit_module(
    config: Optional[Dict[str, Any]] = None,
) -> PrdAuditModule:
    """Create (but do not initialize) a :class:`PrdAuditModule`.

    Args:
        config: Optional dict with gate threshold keys ``max_errors``,
            ``max_warnings``, ``min_score``.

    Returns:
        An uninitialized :class:`PrdAuditModule`.  Call ``await
        module.initialize()`` (as the platform registry does) before use.
    """
    return PrdAuditModule(config=config)
