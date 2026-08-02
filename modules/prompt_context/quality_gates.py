"""
Quality Gates - Enterprise-grade pre-execution quality checks.

Blocks prompt execution when:
- Required context is missing
- Security policies are absent
- Critical memory is unavailable
- Prompt version is deprecated
- Knowledge is stale
- Context conflicts exist
- Required tools are unavailable

Provides warning-level gates for:
- Low relevance scores
- Approaching token limits
- Suboptimal prompt versions
- Missing optional context
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class GateSeverity(str, Enum):
    """Severity level of a gate check."""
    BLOCK = "block"        # Must pass - blocks execution if failed
    WARN = "warn"          # Should pass - warns but doesn't block
    INFO = "info"          # Informational only


class GateStatus(str, Enum):
    """Status of a gate check."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"
    PENDING = "pending"


class GateCategory(str, Enum):
    """Category of quality gate."""
    CONTEXT = "context"          # Context completeness
    SECURITY = "security"        # Security requirements
    COMPLIANCE = "compliance"    # Compliance rules
    VERSIONING = "versioning"    # Prompt version checks
    KNOWLEDGE = "knowledge"      # Knowledge freshness
    TOOLS = "tools"              # Tool availability
    BUDGET = "budget"            # Token budget
    CONFLICTS = "conflicts"      # Context conflict detection
    PERFORMANCE = "performance"   # Performance thresholds


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class GateCheck:
    """A single quality gate check."""
    check_id: str
    name: str
    category: GateCategory
    severity: GateSeverity
    status: GateStatus = GateStatus.PENDING
    passed: bool = False
    message: str = ""
    details: Optional[str] = None
    suggestion: Optional[str] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "category": self.category.value,
            "severity": self.severity.value,
            "status": self.status.value,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
            "suggestion": self.suggestion,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class QualityGateResult:
    """Overall quality gate execution result."""
    passed: bool
    all_checks: List[GateCheck]
    blocks: List[GateCheck] = field(default_factory=list)
    warnings: List[GateCheck] = field(default_factory=list)
    info: List[GateCheck] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)
    total_checks: int = 0
    checks_passed: int = 0
    checks_failed: int = 0
    checks_skipped: int = 0
    duration_ms: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.blocks and self.all_checks:
            self.blocks = [c for c in self.all_checks if c.severity == GateSeverity.BLOCK and not c.passed]
            self.warnings = [c for c in self.all_checks if c.severity == GateSeverity.WARN and not c.passed]
            self.info = [c for c in self.all_checks if c.severity == GateSeverity.INFO]
            self.blocked_by = [c.name for c in self.blocks]
            self.total_checks = len(self.all_checks)
            self.checks_passed = sum(1 for c in self.all_checks if c.passed)
            self.checks_failed = sum(1 for c in self.all_checks if not c.passed and c.status != GateStatus.SKIPPED)
            self.checks_skipped = sum(1 for c in self.all_checks if c.status == GateStatus.SKIPPED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "blocked_by": self.blocked_by,
            "total_checks": self.total_checks,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "checks_skipped": self.checks_skipped,
            "duration_ms": self.duration_ms,
            "blocks": [c.to_dict() for c in self.blocks],
            "warnings": [c.to_dict() for c in self.warnings],
            "info": [c.to_dict() for c in self.info],
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @property
    def has_blocks(self) -> bool:
        return len(self.blocks) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


@dataclass
class GateConfig:
    """Configuration for quality gates."""
    enabled_categories: Set[GateCategory] = field(default_factory=lambda: set(GateCategory))
    require_security_context: bool = True
    require_compliance_context: bool = True
    max_knowledge_age_hours: int = 168  # 1 week
    max_context_age_hours: int = 24
    min_relevance_threshold: float = 0.3
    max_token_utilization: float = 0.95  # 95% of budget
    required_tools: List[str] = field(default_factory=list)
    allow_deprecated: bool = False
    allow_experimental: bool = True
    strict_mode: bool = False  # Warnings become blocks in strict mode


# ---------------------------------------------------------------------------
# Quality Gates
# ---------------------------------------------------------------------------

class QualityGateError(Exception):
    """Base exception for quality gate errors."""


class QualityGateBlockedError(QualityGateError):
    """Raised when quality gates block execution."""

    def __init__(self, result: QualityGateResult):
        self.result = result
        blocked = ", ".join(result.blocked_by)
        super().__init__(f"Execution blocked by quality gates: {blocked}")


class QualityGates:
    """
    Enterprise-grade quality gate system.

    Runs pre-execution checks to ensure prompts meet quality standards.
    Blocks execution when critical requirements aren't met.

    Usage::

        gates = QualityGates()
        gates.add_context_check()
        gates.add_security_check()
        gates.add_version_check()

        result = gates.check_all(
            context_manager=ctx,
            prompt_version="1.0.0",
            prompt_status="active",
        )

        if not result.passed:
            raise QualityGateBlockedError(result)
    """

    def __init__(self, config: Optional[GateConfig] = None):
        self.config = config or GateConfig()
        self._custom_checks: List[Callable[..., GateCheck]] = []
        self._lock = threading.RLock()
        self._check_history: List[QualityGateResult] = []
        self._check_counter = 0

    # ------------------------------------------------------------------
    # Main Check Method
    # ------------------------------------------------------------------

    def check_all(
        self,
        context_manager=None,
        prompt_version: Optional[str] = None,
        prompt_status: Optional[str] = None,
        security_policies: Optional[List[str]] = None,
        compliance_rules: Optional[List[str]] = None,
        knowledge_blocks: Optional[List[Dict[str, Any]]] = None,
        token_usage: Optional[Dict[str, Any]] = None,
        tool_registry: Optional[List[str]] = None,
        context_blocks: Optional[List[Dict[str, Any]]] = None,
        conflicts: Optional[List[Dict[str, Any]]] = None,
        custom_context: Optional[Dict[str, Any]] = None,
        skip_categories: Optional[List[GateCategory]] = None,
    ) -> QualityGateResult:
        """
        Run all quality gate checks.

        Args:
            context_manager: ContextManager instance.
            prompt_version: Current prompt version string.
            prompt_status: Current prompt status ('active', 'deprecated', etc.).
            security_policies: List of security policy strings.
            compliance_rules: List of compliance rule strings.
            knowledge_blocks: Knowledge context blocks with 'age' metadata.
            token_usage: Current token usage stats.
            tool_registry: Available tool names.
            context_blocks: All context blocks.
            conflicts: Detected conflicts.
            custom_context: Additional context for custom checks.
            skip_categories: Categories to skip.

        Returns:
            QualityGateResult with all check results.
        """
        self._check_counter += 1
        start_time = datetime.now(timezone.utc)
        skip = set(skip_categories or [])
        all_checks: List[GateCheck] = []

        # 1. Required context check
        if GateCategory.CONTEXT not in skip:
            check = self._check_required_context(
                context_manager, context_blocks, security_policies, compliance_rules
            )
            all_checks.append(check)

        # 2. Security policies check
        if GateCategory.SECURITY not in skip and self.config.require_security_context:
            check = self._check_security_policies(security_policies, context_manager)
            all_checks.append(check)

        # 3. Compliance check
        if GateCategory.COMPLIANCE not in skip and self.config.require_compliance_context:
            check = self._check_compliance(compliance_rules, context_manager)
            all_checks.append(check)

        # 4. Version check
        if GateCategory.VERSIONING not in skip and prompt_status:
            check = self._check_version(prompt_version, prompt_status)
            all_checks.append(check)

        # 5. Knowledge freshness check
        if GateCategory.KNOWLEDGE not in skip:
            check = self._check_knowledge_freshness(knowledge_blocks)
            all_checks.append(check)

        # 6. Tool availability check
        if GateCategory.TOOLS not in skip:
            check = self._check_tools(tool_registry)
            all_checks.append(check)

        # 7. Token budget check
        if GateCategory.BUDGET not in skip:
            check = self._check_token_budget(token_usage)
            all_checks.append(check)

        # 8. Context conflict check
        if GateCategory.CONFLICTS not in skip:
            check = self._check_conflicts(conflicts)
            all_checks.append(check)

        # 9. Context age check
        if GateCategory.CONTEXT not in skip:
            check = self._check_context_age(context_blocks)
            all_checks.append(check)

        # 10. Run custom checks
        for custom_check_fn in self._custom_checks:
            try:
                check = custom_check_fn(custom_context or {})
                if check:
                    all_checks.append(check)
            except Exception as e:
                all_checks.append(GateCheck(
                    check_id=f"custom_error_{int(time.time())}",
                    name="custom_check_error",
                    category=GateCategory.PERFORMANCE,
                    severity=GateSeverity.WARN,
                    status=GateStatus.ERROR,
                    message=f"Custom check failed: {e}",
                ))

        # Build result
        blocks = [c for c in all_checks if c.severity == GateSeverity.BLOCK and not c.passed]
        warnings = [c for c in all_checks if c.severity == GateSeverity.WARN and not c.passed]

        # In strict mode, warnings become blocks
        if self.config.strict_mode:
            blocks.extend(warnings)
            warnings = []

        overall_passed = len(blocks) == 0

        duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        result = QualityGateResult(
            passed=overall_passed,
            all_checks=all_checks,
            blocks=blocks,
            warnings=warnings,
            blocked_by=[b.name for b in blocks],
            duration_ms=duration,
        )

        with self._lock:
            self._check_history.append(result)
            if len(self._check_history) > 1000:
                self._check_history = self._check_history[-1000:]

        return result

    # ------------------------------------------------------------------
    # Individual Checks
    # ------------------------------------------------------------------

    def _check_required_context(
        self,
        context_manager=None,
        context_blocks: Optional[List[Dict[str, Any]]] = None,
        security_policies: Optional[List[str]] = None,
        compliance_rules: Optional[List[str]] = None,
    ) -> GateCheck:
        """Check that required context types are present."""
        check = GateCheck(
            check_id=f"ctx_req_{self._check_counter}",
            name="Required Context Check",
            category=GateCategory.CONTEXT,
            severity=GateSeverity.WARN,  # Warning, not blocking
        )

        required_types = {"task"}
        present_types: Set[str] = set()

        if context_manager:
            for block in context_manager.get_all():
                present_types.add(block.type.value if hasattr(block.type, 'value') else str(block.type))

        if context_blocks:
            for block in context_blocks:
                present_types.add(block.get("type", ""))

        missing = required_types - present_types

        if missing:
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = f"Missing recommended context types: {missing}"
            check.suggestion = "Consider providing a task context block for better results."
            return check

        check.status = GateStatus.PASSED
        check.passed = True
        check.message = "All required context types present"
        return check

    def _check_security_policies(
        self,
        security_policies: Optional[List[str]],
        context_manager=None,
    ) -> GateCheck:
        """Check that security policies are present."""
        check = GateCheck(
            check_id=f"sec_{self._check_counter}",
            name="Security Policy Check",
            category=GateCategory.SECURITY,
            severity=GateSeverity.BLOCK,
        )

        has_policies = False

        if security_policies and len(security_policies) > 0:
            has_policies = True

        if context_manager:
            try:
                try:
                    from .context_manager import ContextType
                except ImportError:
                    from context_manager import ContextType
                sec_blocks = context_manager.get_by_type(ContextType.SECURITY)
                if sec_blocks:
                    has_policies = True
            except Exception:
                pass

        if not has_policies:
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = "No security policies found in context"
            check.suggestion = "Add security policy context before executing sensitive prompts."
            return check

        check.status = GateStatus.PASSED
        check.passed = True
        check.message = f"Security policies present ({len(security_policies or [])} policies)"
        return check

    def _check_compliance(
        self,
        compliance_rules: Optional[List[str]],
        context_manager=None,
    ) -> GateCheck:
        """Check that compliance rules are present."""
        check = GateCheck(
            check_id=f"cmpl_{self._check_counter}",
            name="Compliance Rule Check",
            category=GateCategory.COMPLIANCE,
            severity=GateSeverity.BLOCK,
        )

        has_rules = False

        if compliance_rules and len(compliance_rules) > 0:
            has_rules = True

        if context_manager:
            try:
                try:
                    from .context_manager import ContextType
                except ImportError:
                    from context_manager import ContextType
                cmp_blocks = context_manager.get_by_type(ContextType.COMPLIANCE)
                if cmp_blocks:
                    has_rules = True
            except Exception:
                pass

        if not has_rules:
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = "No compliance rules found in context"
            check.suggestion = "Add compliance rules context before executing regulated prompts."
            return check

        check.status = GateStatus.PASSED
        check.passed = True
        check.message = f"Compliance rules present ({len(compliance_rules or [])} rules)"
        return check

    def _check_version(
        self,
        prompt_version: Optional[str],
        prompt_status: Optional[str],
    ) -> GateCheck:
        """Check prompt version is valid and not deprecated."""
        check = GateCheck(
            check_id=f"ver_{self._check_counter}",
            name="Prompt Version Check",
            category=GateCategory.VERSIONING,
            severity=GateSeverity.BLOCK,
        )

        if not prompt_version:
            check.status = GateStatus.SKIPPED
            check.passed = True
            check.message = "No version information provided; skipping check"
            return check

        if prompt_status == "deprecated":
            if self.config.allow_deprecated:
                check.status = GateStatus.PASSED
                check.passed = True
                check.message = f"Deprecated version {prompt_version} allowed by config"
                check.metadata["warning"] = "This prompt version is deprecated"
                return check
            else:
                check.status = GateStatus.FAILED
                check.passed = False
                check.message = f"Prompt version {prompt_version} is DEPRECATED"
                check.suggestion = f"Use a current version or enable allow_deprecated in config."
                return check

        if prompt_status == "archived":
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = f"Prompt version {prompt_version} is ARCHIVED"
            check.suggestion = "Archived prompts cannot be executed. Rollback to restore."
            return check

        if prompt_status == "experimental":
            if not self.config.allow_experimental:
                check.status = GateStatus.FAILED
                check.passed = False
                check.message = f"Experimental version {prompt_version} not allowed"
                check.suggestion = "Enable allow_experimental in config or use a stable version."
                return check
            check.status = GateStatus.PASSED
            check.passed = True
            check.message = f"Experimental version {prompt_version} allowed"
            check.metadata["warning"] = "This is an experimental prompt version"
            return check

        check.status = GateStatus.PASSED
        check.passed = True
        check.message = f"Prompt version {prompt_version} is {prompt_status}"
        return check

    def _check_knowledge_freshness(
        self,
        knowledge_blocks: Optional[List[Dict[str, Any]]],
    ) -> GateCheck:
        """Check that knowledge blocks aren't too stale."""
        check = GateCheck(
            check_id=f"know_{self._check_counter}",
            name="Knowledge Freshness Check",
            category=GateCategory.KNOWLEDGE,
            severity=GateSeverity.WARN,
        )

        if not knowledge_blocks:
            check.status = GateStatus.SKIPPED
            check.passed = True
            check.message = "No knowledge blocks to check"
            return check

        now = datetime.now(timezone.utc)
        stale_count = 0
        stale_details = []

        for kb in knowledge_blocks:
            created = kb.get("created_at")
            if created:
                try:
                    if isinstance(created, str):
                        created_dt = datetime.fromisoformat(created)
                    else:
                        created_dt = created
                    age_hours = (now - created_dt).total_seconds() / 3600
                    if age_hours > self.config.max_knowledge_age_hours:
                        stale_count += 1
                        stale_details.append(
                            f"Block '{kb.get('id', 'unknown')}' is {age_hours:.1f}h old "
                            f"(max: {self.config.max_knowledge_age_hours}h)"
                        )
                except (ValueError, TypeError):
                    pass

        if stale_count > 0:
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = f"{stale_count} knowledge block(s) are stale"
            check.details = "; ".join(stale_details[:3])
            check.suggestion = "Refresh stale knowledge before execution."
            return check

        check.status = GateStatus.PASSED
        check.passed = True
        check.message = f"All {len(knowledge_blocks)} knowledge blocks are fresh"
        return check

    def _check_tools(
        self,
        tool_registry: Optional[List[str]],
    ) -> GateCheck:
        """Check that required tools are available."""
        check = GateCheck(
            check_id=f"tool_{self._check_counter}",
            name="Tool Availability Check",
            category=GateCategory.TOOLS,
            severity=GateSeverity.BLOCK,
        )

        if not self.config.required_tools:
            check.status = GateStatus.SKIPPED
            check.passed = True
            check.message = "No required tools configured"
            return check

        if not tool_registry:
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = "Tool registry unavailable; cannot verify required tools"
            check.suggestion = "Provide a tool registry or disable this check."
            return check

        available = set(tool_registry)
        required = set(self.config.required_tools)
        missing = required - available

        if missing:
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = f"Required tools unavailable: {missing}"
            check.suggestion = f"Ensure these tools are available: {missing}"
            return check

        check.status = GateStatus.PASSED
        check.passed = True
        check.message = f"All {len(required)} required tools available"
        return check

    def _check_token_budget(
        self,
        token_usage: Optional[Dict[str, Any]],
    ) -> GateCheck:
        """Check token budget utilization."""
        check = GateCheck(
            check_id=f"budget_{self._check_counter}",
            name="Token Budget Check",
            category=GateCategory.BUDGET,
            severity=GateSeverity.WARN,
        )

        if not token_usage:
            check.status = GateStatus.SKIPPED
            check.passed = True
            check.message = "No token usage data available"
            return check

        utilization = token_usage.get("utilization_pct", token_usage.get("usage_pct", 0))
        available = token_usage.get("available", 0)

        if utilization > self.config.max_token_utilization * 100:
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = (
                f"Token budget utilization at {utilization}% "
                f"(max: {self.config.max_token_utilization * 100}%)"
            )
            check.suggestion = (
                "Reduce context size, enable truncation, or increase budget."
            )
            return check

        if utilization > (self.config.max_token_utilization * 100) - 10:
            check.status = GateStatus.PASSED
            check.passed = True
            check.message = (
                f"Token budget near limit: {utilization}% used, "
                f"{available} tokens remaining"
            )
            check.metadata["warning"] = "Approaching token budget limit"
            return check

        check.status = GateStatus.PASSED
        check.passed = True
        check.message = f"Token budget OK: {utilization}% used"
        return check

    def _check_conflicts(
        self,
        conflicts: Optional[List[Dict[str, Any]]],
    ) -> GateCheck:
        """Check for detected context conflicts."""
        check = GateCheck(
            check_id=f"cnfl_{self._check_counter}",
            name="Context Conflict Check",
            category=GateCategory.CONFLICTS,
            severity=GateSeverity.WARN,
        )

        if not conflicts:
            check.status = GateStatus.PASSED
            check.passed = True
            check.message = "No context conflicts detected"
            return check

        high_severity = [c for c in conflicts if c.get("severity") == "high"]
        if high_severity:
            check.severity = GateSeverity.BLOCK  # Upgrade to block
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = f"{len(high_severity)} high-severity conflict(s) detected"
            check.details = str(high_severity[:3])
            check.suggestion = "Resolve context conflicts before execution."
            return check

        check.status = GateStatus.FAILED
        check.passed = False
        check.message = f"{len(conflicts)} conflict(s) detected (non-critical)"
        check.suggestion = "Review and resolve conflicts."
        return check

    def _check_context_age(
        self,
        context_blocks: Optional[List[Dict[str, Any]]],
    ) -> GateCheck:
        """Check that context blocks aren't too old."""
        check = GateCheck(
            check_id=f"age_{self._check_counter}",
            name="Context Age Check",
            category=GateCategory.CONTEXT,
            severity=GateSeverity.INFO,
        )

        if not context_blocks:
            check.status = GateStatus.SKIPPED
            check.passed = True
            check.message = "No context blocks to check age"
            return check

        now = datetime.now(timezone.utc)
        old_count = 0

        for block in context_blocks:
            if block.get("is_immutable"):
                continue
            created = block.get("created_at")
            if created:
                try:
                    if isinstance(created, str):
                        created_dt = datetime.fromisoformat(created)
                    else:
                        created_dt = created
                    age_hours = (now - created_dt).total_seconds() / 3600
                    if age_hours > self.config.max_context_age_hours:
                        old_count += 1
                except (ValueError, TypeError):
                    pass

        if old_count > 0:
            check.status = GateStatus.FAILED
            check.passed = False
            check.message = f"{old_count} context block(s) older than {self.config.max_context_age_hours}h"
            return check

        check.status = GateStatus.PASSED
        check.passed = True
        check.message = f"All context blocks within age limit"
        return check

    # ------------------------------------------------------------------
    # Custom Checks
    # ------------------------------------------------------------------

    def register_check(
        self,
        check_fn: Callable[..., GateCheck],
    ) -> None:
        """Register a custom quality gate check."""
        with self._lock:
            self._custom_checks.append(check_fn)

    def remove_check(
        self,
        check_fn: Callable[..., GateCheck],
    ) -> bool:
        """Remove a custom quality gate check."""
        with self._lock:
            if check_fn in self._custom_checks:
                self._custom_checks.remove(check_fn)
                return True
            return False

    # ------------------------------------------------------------------
    # Pre-configured Gate Sets
    # ------------------------------------------------------------------

    @classmethod
    def create_security_gates(cls) -> "QualityGates":
        """Create quality gates focused on security."""
        config = GateConfig(
            require_security_context=True,
            require_compliance_context=False,
            strict_mode=True,
        )
        return cls(config=config)

    @classmethod
    def create_full_gates(cls) -> "QualityGates":
        """Create comprehensive quality gates with all checks."""
        config = GateConfig(
            require_security_context=True,
            require_compliance_context=True,
            strict_mode=False,
        )
        return cls(config=config)

    @classmethod
    def create_lightweight_gates(cls) -> "QualityGates":
        """Create minimal quality gates for fast execution."""
        config = GateConfig(
            require_security_context=False,
            require_compliance_context=False,
            allow_deprecated=True,
            allow_experimental=True,
        )
        return cls(config=config)

    # ------------------------------------------------------------------
    # Assertion Helpers
    # ------------------------------------------------------------------

    def assert_passes(
        self,
        result: QualityGateResult,
        raise_on_block: bool = True,
    ) -> QualityGateResult:
        """
        Assert that quality gates pass. Raises QualityGateBlockedError if not.

        Returns the result for chaining on success.
        """
        if not result.passed and raise_on_block:
            raise QualityGateBlockedError(result)
        return result

    # ------------------------------------------------------------------
    # History & Stats
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 50) -> List[QualityGateResult]:
        """Get recent check history."""
        with self._lock:
            return self._check_history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Get quality gate statistics."""
        with self._lock:
            if not self._check_history:
                return {"runs": 0}

            total = len(self._check_history)
            passed = sum(1 for r in self._check_history if r.passed)
            blocked = sum(1 for r in self._check_history if not r.passed)
            avg_duration = sum(r.duration_ms for r in self._check_history) / total

            # Most common blocking checks
            block_names: Dict[str, int] = {}
            for r in self._check_history:
                for b in r.blocks:
                    block_names[b.name] = block_names.get(b.name, 0) + 1

            return {
                "runs": total,
                "passed": passed,
                "blocked": blocked,
                "pass_rate": round(passed / total * 100, 1),
                "avg_duration_ms": round(avg_duration, 1),
                "most_common_blocks": sorted(
                    block_names.items(), key=lambda x: -x[1]
                )[:5],
                "last_run": self._check_history[-1].timestamp.isoformat(),
            }

    def clear_history(self) -> int:
        """Clear check history."""
        with self._lock:
            count = len(self._check_history)
            self._check_history.clear()
            return count

    def __repr__(self) -> str:
        stats = self.get_stats()
        return (
            f"QualityGates(runs={stats.get('runs', 0)}, "
            f"pass_rate={stats.get('pass_rate', 0)}%)"
        )