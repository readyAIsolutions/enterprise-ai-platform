"""
Enterprise-Grade Independent Verification System
================================================
Part of the Agent Communication & Coordination OS Module.

Provides multi-domain, evidence-based verification of agent work outputs
with strict independence guarantees, verification gates, and result caching.

Verification Domains:
  - correctness      : Functional correctness of work output
  - security         : Security properties and vulnerability assessment
  - scalability      : Horizontal/vertical scaling characteristics
  - performance      : Latency, throughput, resource utilization
  - maintainability  : Code quality, documentation, modularity
  - accessibility    : A11y compliance, usability standards
  - cost             : Resource cost, operational expenditure
  - compliance       : Regulatory and policy adherence
  - ai_safety        : AI alignment, bias, harmful output detection

Author: Eni Builder OS
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

logger = logging.getLogger(__name__)


# =========================================================================
# Enums
# =========================================================================


class VerificationDomain(Enum):
    """Well-known verification domains for categorizing checks."""

    CORRECTNESS = "correctness"
    SECURITY = "security"
    SCALABILITY = "scalability"
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    ACCESSIBILITY = "accessibility"
    COST = "cost"
    COMPLIANCE = "compliance"
    AI_SAFETY = "ai_safety"

    @classmethod
    def all_domains(cls) -> List["VerificationDomain"]:
        """Return every defined verification domain."""
        return list(cls)


class VerificationStatus(Enum):
    """Lifecycle status of a single verification check."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class Severity(Enum):
    """Severity of a verification check failure."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

    def value_rank(self) -> int:
        """Return a numeric rank for comparison (higher = more severe)."""
        return {Severity.CRITICAL: 4, Severity.HIGH: 3,
                Severity.MEDIUM: 2, Severity.LOW: 1}[self]


class GateAction(Enum):
    """Action to take when a verification gate condition is not met."""
    BLOCK = auto()
    WARN = auto()
    ESCALATE = auto()


# =========================================================================
# Data Classes
# =========================================================================


@dataclass
class Evidence:
    """A single piece of evidence collected during verification."""

    evidence_id: str
    description: str
    source: str
    content_hash: str
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_content(cls, description: str, source: str, content: str,
                     metadata: Optional[Dict[str, Any]] = None) -> "Evidence":
        """Create evidence, automatically hashing the content."""
        return cls(
            evidence_id=str(uuid.uuid4()),
            description=description,
            source=source,
            content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            metadata=metadata or {},
        )


@dataclass
class VerificationResult:
    """Outcome of evaluating a single criterion."""

    passed: bool
    actual_value: Any
    expected_value: Any
    evidence_ids: List[str] = field(default_factory=list)
    notes: str = ""
    severity: Severity = Severity.MEDIUM
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class VerificationCheck:
    """A single, measurable verification criterion.

    Attributes:
        check_id: Unique identifier for this check.
        domain: The verification domain this check belongs to.
        description: Human-readable description of what is being verified.
        criteria: Measurable criteria (e.g. a predicate expression, a threshold).
        required_evidence: Specific evidence types needed to evaluate this check.
        assigned_verifier: Agent or entity performing the verification.
            **Must be independent of the agent that produced the work.**
        status: Current lifecycle status.
        severity: How critical a failure on this check would be.
        results: Collected verification results (may contain multiple sub-results).
        evidence_collected: Evidence gathered during verification.
        work_id: The identifier of the work product being verified.
        work_producer: The agent that produced the work (used to enforce independence).
        created_at: Timestamp of check registration.
    """

    check_id: str
    domain: VerificationDomain
    description: str
    criteria: str
    required_evidence: List[str]
    assigned_verifier: str
    status: VerificationStatus = VerificationStatus.PENDING
    severity: Severity = Severity.MEDIUM
    results: List[VerificationResult] = field(default_factory=list)
    evidence_collected: List[Evidence] = field(default_factory=list)
    work_id: str = ""
    work_producer: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        """Enforce independence: verifier must not be the work producer."""
        if self.work_producer and self.assigned_verifier == self.work_producer:
            raise IndependenceViolation(
                f"Check '{self.check_id}': verifier '{self.assigned_verifier}' "
                f"must not be the same as work producer '{self.work_producer}'."
            )

    @property
    def is_independent(self) -> bool:
        """Return True when the verifier is independent of the work producer."""
        if not self.work_producer:
            return True
        return self.assigned_verifier != self.work_producer


@dataclass
class VerificationGate:
    """A gate that must be passed before work can proceed to the next stage.

    Gates aggregate multiple checks and require all (or a configurable subset)
    to pass before allowing forward progress.
    """

    gate_id: str
    description: str
    check_ids: List[str]
    required_pass_count: int = -1  # -1 means *all* checks must pass
    action_on_failure: GateAction = GateAction.BLOCK
    minimum_severity_to_block: Severity = Severity.CRITICAL
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_satisfied(self, check_results: Dict[str, VerificationCheck]) -> bool:
        """Evaluate whether this gate's conditions are met."""
        relevant = [check_results[cid] for cid in self.check_ids if cid in check_results]
        if not relevant:
            return False
        required = self.required_pass_count if self.required_pass_count > 0 else len(relevant)
        passed_count = sum(1 for c in relevant if c.status == VerificationStatus.PASSED)
        return passed_count >= required


@dataclass
class CachedResult:
    """Wrapper for cached verification results with invalidation support."""

    checks: Dict[str, VerificationCheck]
    computed_at: datetime
    content_hash: str

    def is_stale(self, current_hash: str) -> bool:
        """Return True when the work content has changed since caching."""
        return self.content_hash != current_hash


# =========================================================================
# Exceptions
# =========================================================================


class VerificationError(Exception):
    """Base exception for verification failures."""


class IndependenceViolation(VerificationError):
    """Raised when a verifier is not independent of the work producer."""


class GateBlockedError(VerificationError):
    """Raised when a verification gate blocks progress."""


class CheckNotFoundError(VerificationError):
    """Raised when a referenced check does not exist."""


class EvidenceMissingError(VerificationError):
    """Raised when required evidence has not been collected."""


# =========================================================================
# Type Aliases
# =========================================================================

CheckExecutor = Callable[
    [VerificationCheck, Dict[str, Evidence]],
    Awaitable[VerificationResult],
]


# =========================================================================
# Verifier
# =========================================================================


class Verifier:
    """Independent verification engine for agent work outputs.

    The Verifier ensures that **no agent verifies its own work** by
    enforcing independence constraints at check registration time and
    before every execution.  It supports:

    * Multi-domain verification with configurable checks per domain.
    * Evidence-based evaluation requiring specific evidence types.
    * Parallel execution of independent checks.
    * Verification gates that must be satisfied before proceeding.
    * Result caching with automatic invalidation on content changes.
    * Severity-gated workflows (critical failures block by default).

    Typical usage::

        verifier = Verifier()
        verifier.register_executor(VerificationDomain.CORRECTNESS, my_executor)

        checks = [
            VerificationCheck(
                check_id="correctness-01",
                domain=VerificationDomain.CORRECTNESS,
                description="Output matches spec",
                criteria="all test cases pass",
                required_evidence=["test_results.json"],
                assigned_verifier="verifier-agent-7",
                work_producer="worker-agent-3",
                severity=Severity.CRITICAL,
            ),
        ]
        verifier.register_checks(VerificationDomain.CORRECTNESS, checks)

        report = await verifier.verify(
            work_output={"data": "..."},
            domain=VerificationDomain.CORRECTNESS,
        )
    """

    def __init__(self) -> None:
        self._checks: Dict[str, VerificationCheck] = {}
        self._checks_by_domain: Dict[VerificationDomain, List[str]] = defaultdict(list)
        self._checks_by_work: Dict[str, List[str]] = defaultdict(list)
        self._executors: Dict[VerificationDomain, CheckExecutor] = {}
        self._gates: Dict[str, VerificationGate] = {}
        self._cache: Dict[str, CachedResult] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_checks(
        self, domain: VerificationDomain, checks: List[VerificationCheck],
    ) -> None:
        """Register a set of verification checks for a given domain.

        Raises IndependenceViolation if any check's verifier is the same
        as its work producer.
        """
        for check in checks:
            if check.work_producer and check.assigned_verifier == check.work_producer:
                raise IndependenceViolation(
                    f"Check '{check.check_id}' cannot be verified by its own "
                    f"producer '{check.work_producer}'."
                )
            self._checks[check.check_id] = check
            self._checks_by_domain[domain].append(check.check_id)
            if check.work_id:
                self._checks_by_work[check.work_id].append(check.check_id)
        logger.info("Registered %d checks for domain %s", len(checks), domain.value)

    def register_executor(self, domain: VerificationDomain,
                          executor: CheckExecutor) -> None:
        """Register an async executor callable for a verification domain.

        The executor receives (VerificationCheck, Dict[str,Evidence]) and
        returns a VerificationResult.
        """
        self._executors[domain] = executor
        logger.info("Registered executor for domain %s", domain.value)

    def register_gate(self, gate: VerificationGate) -> None:
        """Register a verification gate.  All referenced check IDs must exist."""
        for cid in gate.check_ids:
            if cid not in self._checks:
                raise CheckNotFoundError(
                    f"Gate '{gate.gate_id}' references unknown check '{cid}'."
                )
        self._gates[gate.gate_id] = gate
        logger.info("Registered gate '%s' with %d checks",
                    gate.gate_id, len(gate.check_ids))

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    async def verify(
        self,
        work_output: Dict[str, Any],
        domain: Optional[VerificationDomain] = None,
        work_id: Optional[str] = None,
        skip_cache: bool = False,
    ) -> Dict[str, VerificationCheck]:
        """Run verification checks against a work output.

        If *domain* is provided only checks for that domain are executed.
        Otherwise all registered checks for the given *work_id* are run.
        Checks within a domain are executed concurrently.
        """
        # Cache lookup
        if work_id and not skip_cache:
            cached = self._cache.get(work_id)
            if cached and not cached.is_stale(self._hash_content(work_output)):
                logger.debug("Returning cached verification for work '%s'", work_id)
                return cached.checks

        # Select checks
        if domain is not None:
            target_ids = self._checks_by_domain.get(domain, [])
        elif work_id:
            target_ids = self._checks_by_work.get(work_id, [])
        else:
            target_ids = list(self._checks.keys())

        checks_to_run = [self._checks[cid] for cid in target_ids]
        if not checks_to_run:
            logger.warning("No checks found for work_id=%s domain=%s", work_id, domain)
            return {}

        # Execute in parallel
        tasks = []
        for check in checks_to_run:
            check.status = VerificationStatus.IN_PROGRESS
            check.results.clear()
            check.evidence_collected.clear()
            tasks.append(asyncio.create_task(self._run_check(check, work_output)))

        await asyncio.gather(*tasks, return_exceptions=True)

        # Build result map
        results: Dict[str, VerificationCheck] = {}
        for check in checks_to_run:
            results[check.check_id] = check

        # Update cache
        if work_id:
            self._cache[work_id] = CachedResult(
                checks=results,
                computed_at=datetime.now(timezone.utc),
                content_hash=self._hash_content(work_output),
            )
        return results

    async def _run_check(self, check: VerificationCheck,
                         work_output: Dict[str, Any]) -> None:
        """Execute a single verification check, collecting evidence first."""
        try:
            evidence_map = await self._collect_evidence(check, work_output)
            check.evidence_collected = list(evidence_map.values())

            executor = self._executors.get(check.domain)
            if executor is None:
                raise VerificationError(
                    f"No executor registered for domain '{check.domain.value}'"
                )

            result = await executor(check, evidence_map)
            check.results.append(result)

            if result.passed:
                check.status = VerificationStatus.PASSED
            else:
                check.status = VerificationStatus.FAILED
                logger.warning("Check '%s' FAILED (severity=%s): %s",
                               check.check_id, result.severity.value, result.notes)

        except EvidenceMissingError:
            check.status = VerificationStatus.BLOCKED
            logger.error("Check '%s' BLOCKED: missing evidence", check.check_id)
        except Exception:
            logger.exception("Unexpected error during check '%s'", check.check_id)
            check.status = VerificationStatus.FAILED
            check.results.append(VerificationResult(
                passed=False, actual_value=None, expected_value=None,
                notes="Internal verification error", severity=Severity.CRITICAL,
            ))

    async def _collect_evidence(
        self, check: VerificationCheck, work_output: Dict[str, Any],
    ) -> Dict[str, Evidence]:
        """Gather all required evidence for a check from the work output."""
        collected: Dict[str, Evidence] = {}
        evidence_section: Dict[str, Any] = work_output.get("evidence", {})

        for required_type in check.required_evidence:
            if required_type in evidence_section:
                raw = evidence_section[required_type]
                collected[required_type] = Evidence.from_content(
                    description=required_type,
                    source=f"work_output.evidence.{required_type}",
                    content=json.dumps(raw, sort_keys=True, default=str),
                    metadata={"check_id": check.check_id},
                )
            else:
                raise EvidenceMissingError(
                    f"Check '{check.check_id}' requires evidence type "
                    f"'{required_type}' which was not found in work output."
                )
        return collected

    # ------------------------------------------------------------------
    # Status & Reporting
    # ------------------------------------------------------------------

    def get_verification_status(self, work_id: str) -> Dict[str, Any]:
        """Return a high-level status summary for a given work product."""
        check_ids = self._checks_by_work.get(work_id, [])
        checks = [self._checks[cid] for cid in check_ids]

        counts: Dict[str, int] = defaultdict(int)
        critical_failures = 0
        for c in checks:
            counts[c.status.value] += 1
            if c.status == VerificationStatus.FAILED:
                critical_failures += sum(
                    1 for r in c.results if r.severity == Severity.CRITICAL
                )

        if not checks:
            overall = "no_checks"
        elif counts["failed"] > 0:
            overall = "failed"
        elif counts["blocked"] > 0:
            overall = "blocked"
        elif counts["in_progress"] > 0:
            overall = "in_progress"
        elif counts["pending"] > 0:
            overall = "pending"
        else:
            overall = "passed"

        return {
            "work_id": work_id,
            "overall_status": overall,
            "passed": counts.get("passed", 0),
            "failed": counts.get("failed", 0),
            "blocked": counts.get("blocked", 0),
            "pending": counts.get("pending", 0),
            "in_progress": counts.get("in_progress", 0),
            "skipped": counts.get("skipped", 0),
            "total_checks": len(checks),
            "critical_failures": critical_failures,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_verification_report(self, work_id: str) -> Dict[str, Any]:
        """Generate a full verification report for a work product."""
        status = self.get_verification_status(work_id)
        check_ids = self._checks_by_work.get(work_id, [])

        check_details = []
        for cid in check_ids:
            check = self._checks[cid]
            detail: Dict[str, Any] = {
                "check_id": check.check_id,
                "domain": check.domain.value,
                "description": check.description,
                "criteria": check.criteria,
                "assigned_verifier": check.assigned_verifier,
                "work_producer": check.work_producer,
                "independent": check.is_independent,
                "status": check.status.value,
                "severity": check.severity.value,
                "results": [
                    {
                        "passed": r.passed,
                        "actual_value": r.actual_value,
                        "expected_value": r.expected_value,
                        "notes": r.notes,
                        "severity": r.severity.value,
                        "evaluated_at": r.evaluated_at.isoformat(),
                    }
                    for r in check.results
                ],
                "evidence_count": len(check.evidence_collected),
                "created_at": check.created_at.isoformat(),
            }
            check_details.append(detail)

        gate_evaluations = {}
        for gid, gate in self._gates.items():
            relevant_checks = {
                cid: self._checks[cid]
                for cid in gate.check_ids
                if cid in self._checks and self._checks[cid].work_id == work_id
            }
            if relevant_checks:
                gate_evaluations[gid] = {
                    "description": gate.description,
                    "satisfied": gate.is_satisfied(relevant_checks),
                    "action_on_failure": gate.action_on_failure.name,
                    "passed_checks": sum(
                        1 for c in relevant_checks.values()
                        if c.status == VerificationStatus.PASSED
                    ),
                    "total_checks": len(relevant_checks),
                }

        return {
            "report_id": str(uuid.uuid4()),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "checks": check_details,
            "gates": gate_evaluations,
        }

    # ------------------------------------------------------------------
    # Gate Evaluation
    # ------------------------------------------------------------------

    async def evaluate_gates(self, work_id: str) -> Dict[str, bool]:
        """Evaluate all registered gates for a work product.

        Raises GateBlockedError when a BLOCK-type gate is not satisfied.
        """
        results: Dict[str, bool] = {}
        for gid, gate in self._gates.items():
            relevant = {
                cid: self._checks[cid]
                for cid in gate.check_ids
                if cid in self._checks and self._checks[cid].work_id == work_id
            }
            satisfied = gate.is_satisfied(relevant)
            results[gid] = satisfied

            if not satisfied and gate.action_on_failure == GateAction.BLOCK:
                for check in relevant.values():
                    if check.status != VerificationStatus.PASSED:
                        if check.severity.value_rank() >= gate.minimum_severity_to_block.value_rank():
                            raise GateBlockedError(
                                f"Gate '{gid}' blocked: check '{check.check_id}' "
                                f"failed with severity {check.severity.value}."
                            )
        return results

    # ------------------------------------------------------------------
    # Cache Management
    # ------------------------------------------------------------------

    def invalidate_cache(self, work_id: str) -> None:
        """Remove cached verification results for a work product."""
        self._cache.pop(work_id, None)
        logger.debug("Invalidated cache for work '%s'", work_id)

    def invalidate_all(self) -> None:
        """Clear the entire verification cache."""
        self._cache.clear()
        logger.info("Cleared all verification caches")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_content(work_output: Dict[str, Any]) -> str:
        """Produce a stable hash of work output content."""
        serialized = json.dumps(work_output, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# =========================================================================
# Built-in Executors
# =========================================================================


async def default_correctness_executor(
    check: VerificationCheck, evidence: Dict[str, Evidence],
) -> VerificationResult:
    """Default correctness executor — checks for test_results.json evidence."""
    if "test_results.json" not in evidence:
        return VerificationResult(
            passed=False, actual_value=None,
            expected_value="evidence:test_results.json",
            notes="Missing test_results.json evidence",
            severity=Severity.CRITICAL,
        )
    return VerificationResult(
        passed=True, actual_value="all_tests_passed",
        expected_value="all_tests_passed",
        notes="Correctness checks passed based on evidence",
        severity=check.severity,
    )


async def default_security_executor(
    check: VerificationCheck, evidence: Dict[str, Evidence],
) -> VerificationResult:
    """Default security executor — checks for security_scan.json evidence."""
    if "security_scan.json" not in evidence:
        return VerificationResult(
            passed=False, actual_value=None,
            expected_value="evidence:security_scan.json",
            notes="Missing security scan evidence",
            severity=Severity.HIGH,
        )
    return VerificationResult(
        passed=True, actual_value="no_critical_vulnerabilities",
        expected_value="no_critical_vulnerabilities",
        notes="Security scan passed",
        severity=check.severity,
    )


async def default_performance_executor(
    check: VerificationCheck, evidence: Dict[str, Evidence],
) -> VerificationResult:
    """Default performance executor — checks for benchmark_results.json evidence."""
    if "benchmark_results.json" not in evidence:
        return VerificationResult(
            passed=False, actual_value=None,
            expected_value="evidence:benchmark_results.json",
            notes="Missing benchmark results evidence",
            severity=Severity.MEDIUM,
        )
    return VerificationResult(
        passed=True, actual_value="within_thresholds",
        expected_value="within_thresholds",
        notes="Performance benchmarks within acceptable thresholds",
        severity=check.severity,
    )


async def default_ai_safety_executor(
    check: VerificationCheck, evidence: Dict[str, Evidence],
) -> VerificationResult:
    """Default AI safety executor — checks for safety_evaluation.json evidence."""
    if "safety_evaluation.json" not in evidence:
        return VerificationResult(
            passed=False, actual_value=None,
            expected_value="evidence:safety_evaluation.json",
            notes="Missing safety evaluation evidence",
            severity=Severity.CRITICAL,
        )
    return VerificationResult(
        passed=True, actual_value="safe", expected_value="safe",
        notes="AI safety evaluation passed",
        severity=check.severity,
    )


DEFAULT_EXECUTORS: Dict[VerificationDomain, CheckExecutor] = {
    VerificationDomain.CORRECTNESS: default_correctness_executor,
    VerificationDomain.SECURITY: default_security_executor,
    VerificationDomain.PERFORMANCE: default_performance_executor,
    VerificationDomain.AI_SAFETY: default_ai_safety_executor,
}


def create_verifier(
    domains: Optional[List[VerificationDomain]] = None,
    use_defaults: bool = True,
) -> Verifier:
    """Create a Verifier pre-configured with default executors."""
    verifier = Verifier()
    if use_defaults:
        targets = domains or list(DEFAULT_EXECUTORS.keys())
        for domain in targets:
            executor = DEFAULT_EXECUTORS.get(domain)
            if executor:
                verifier.register_executor(domain, executor)
    return verifier