"""codegen_audit — audit / evaluate AI-generated code.

Grounded in three JE Van Clief coding-tool-eval transcripts:

* ``_rtyhVD4v4A`` — "One of These AI Coding Tools Failed Completely": comparing
  AI coding tools on how well they understand a technical goal and produce
  working, modular code.  Feeds the static review (hallucinated imports,
  truncation/fidelity stubs) and the task-understanding evaluator (does the
  generated code satisfy the *stated requirements*, and are claimed features
  actually verified?).

* ``nWbM9Ye2sLw`` — "Open Claw Vibe Coded an App. Real Developers Read Every
  Line and Tell You What They Found": a line-by-line team security audit of a
  vibe-coded app.  Feeds the secret/credential, redundant-reinvention, and
  unverified-auth checks.

* ``5B6W2OGfxq0`` — "How One Line of Python Triggers 12,000 Lines of Code":
  the execution-abstraction stack (source -> AST -> bytecode -> interpreter ->
  runtime).  Feeds the dependency/abstraction-depth analysis and the
  error-handling checks (every layer is engineered with error handling).

Export surface (thin facades over the pure stdlib core in
:mod:`enterprise.modules.codegen_audit.codegen_audit`):

  * ``audit_code`` / ``review_code`` — static heuristic code review.
  * ``score_code`` / ``score_checks`` — review scoring report (grade + verdict).
  * ``analyze_dependencies`` / ``analyze_blast_radius`` — dependency /
    abstraction-depth analysis.
  * ``evaluate_task`` / ``verify_features`` — task-understanding evaluator.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from enterprise.platform_kernel import (
    Event,
    EventBus,
    EventPriority,
    HealthStatus,
    Module,
    module,
)

from .codegen_audit import (  # noqa: F401
    BlastRadiusResult,
    BUILTIN_MODULES,
    CheckResult,
    CodeReview,
    DependencyDepthResult,
    EXECUTION_LAYERS,
    RequirementResult,
    ReviewScore,
    Status,
    TaskUnderstandingReport,
    audit_code,
    dependency_blast_radius,
    dependency_depth,
    evaluate_requirements,
    review_code,
    score_checks,
    verify_features,
)

logger = logging.getLogger("eni.codegen_audit")
__version__ = "1.0.0"


@module(
    name="codegen_audit",
    version="1.0.0",
    config_defaults={
        # When a delivered feature is claimed but unverifiable, emit a WARN
        # instead of silently trusting the claim (feature-verification rigor).
        "require_verification": True,
    },
)
class CodegenAuditModule(Module):
    """Enterprise facade for auditing AI-generated code.

    Lifecycle: ``initialize()`` -> HEALTHY on success, UNHEALTHY (+ re-raise)
    on failure.  When an event bus is wired via ``set_event_bus`` (never
    assumed), audit events are published defensively — publishing is guarded so
    a missing bus or a failing bus never breaks an audit call.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Optional[EventBus] = None
        self._ready: bool = False
        self._require_verification: bool = bool(
            self.config.get("require_verification", True)
        )

    # -- Lifecycle ---------------------------------------------------------

    async def initialize(self) -> None:
        try:
            self._ready = True
            self.status = HealthStatus.HEALTHY
            logger.info("codegen_audit module initialized")
        except Exception as exc:  # noqa: BLE001 - lifecycle robustness
            self._ready = False
            self.status = HealthStatus.UNHEALTHY
            logger.exception("codegen_audit initialize failed")
            raise exc

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY if self._ready else HealthStatus.UNHEALTHY

    async def shutdown(self) -> None:
        self._ready = False
        self.status = HealthStatus.UNKNOWN
        logger.info("codegen_audit module shut down")

    # -- Event bus wiring --------------------------------------------------

    def set_event_bus(self, event_bus: EventBus) -> None:
        """Wire the platform EventBus into this module (may be replaced)."""
        self._event_bus = event_bus

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish an event, guarded so a missing/failing bus is a no-op."""
        bus = self._event_bus
        if bus is None:
            return
        try:
            bus.publish(
                Event.create(
                    topic,
                    source=self.name,
                    payload=payload,
                    priority=EventPriority.NORMAL,
                )
            )
        except Exception as exc:  # noqa: BLE001 - defensive
            logger.warning("Failed to publish event %s: %s", topic, exc)

    def _ensure_ready(self) -> None:
        if not self._ready:
            raise RuntimeError("codegen_audit module is not initialized")

    # -- Public facades (thin wrappers over the pure core) ------------------

    def review(self, source: str,
               available_modules: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        """Run the pure static heuristic code review and return its dict form."""
        self._ensure_ready()
        self._emit("codegen_audit.review.run", {"source_lines": len((source or "").splitlines())})
        return review_code(source, available_modules=available_modules).to_dict()

    def score(self, review: Optional[Dict[str, Any]] = None,
              source: Optional[str] = None,
              available_modules: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        """Produce a review scoring report (grade + verdict)."""
        self._ensure_ready()
        if review is not None:
            checks = [CheckResult(**c) for c in review.get("checks", [])]
            result = score_checks(checks)
        else:
            result = score_checks(review_code(source or "", available_modules).checks)
        self._emit("codegen_audit.scored", {"grade": result.grade, "verdict": result.verdict.value})
        return result.to_dict()

    def audit(self, source: str,
              available_modules: Optional[Iterable[str]] = None,
              requirements: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        """Run the full audit pipeline: review + score + task understanding."""
        self._ensure_ready()
        self._emit("codegen_audit.audit.run", {"source_lines": len((source or "").splitlines())})
        return audit_code(source, available_modules=available_modules, requirements=requirements)

    def analyze_dependencies(self, symbol: str, graph: Dict[str, Iterable[str]],
                             blast_radius: bool = True,
                             over_broad_threshold: int = 5) -> Dict[str, Any]:
        """Dependency / abstraction-depth analysis for a symbol in its graph."""
        self._ensure_ready()
        depth = dependency_depth(symbol, graph)
        result: Dict[str, Any] = {"depth": depth.to_dict()}
        if blast_radius:
            radius = dependency_blast_radius(symbol, graph, over_broad_threshold=over_broad_threshold)
            result["blast_radius"] = radius.to_dict()
        self._emit("codegen_audit.dependency.analyzed", {"symbol": symbol})
        return result

    def evaluate_task(self, requirements: Iterable[str], delivered: str,
                      require_fidelity: bool = True) -> Dict[str, Any]:
        """Task-understanding evaluator: does delivered code satisfy the goals?"""
        self._ensure_ready()
        report = evaluate_requirements(requirements, delivered, require_fidelity)
        self._emit("codegen_audit.task.evaluated", {"overall": report.overall.value})
        return report.to_dict()


def create_codegen_audit_module(config: Optional[Dict[str, Any]] = None) -> CodegenAuditModule:
    """Create (but do not initialize) a :class:`CodegenAuditModule`.

    Args:
        config: Optional dict. Supported keys:
            - ``require_verification`` (bool): default True — require claimed
              features to be verifiable (feature-verification rigor).

    Returns:
        An uninitialized :class:`CodegenAuditModule`.  Call ``await
        initialize()`` (e.g. via the Platform Kernel lifecycle) before use.
    """
    return CodegenAuditModule(config=config or {})


__all__ = [
    "CodegenAuditModule", "create_codegen_audit_module",
    "Status", "CheckResult", "CodeReview", "ReviewScore",
    "DependencyDepthResult", "BlastRadiusResult",
    "RequirementResult", "TaskUnderstandingReport",
    "EXECUTION_LAYERS", "BUILTIN_MODULES",
    "review_code", "score_checks", "evaluate_requirements", "verify_features",
    "dependency_depth", "dependency_blast_radius", "audit_code",
    "__version__",
]
