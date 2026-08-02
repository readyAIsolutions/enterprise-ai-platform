"""
Feature flag management system with targeting rules and dependency resolution.

Supports:
    - Boolean and multivariate flags
    - Percentage-based rollout
    - User/group targeting
    - Environment targeting
    - Flag dependencies (flag A requires flag B to be enabled)
    - Kill switches (emergency off)
    - Flag evaluation caching
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class FlagType(Enum):
    """The kind of flag."""
    BOOLEAN = auto()
    MULTIVARIATE = auto()


class TargetOperator(Enum):
    """Comparison operators for targeting rules."""
    EQUALS = auto()
    NOT_EQUALS = auto()
    IN = auto()
    NOT_IN = auto()
    CONTAINS = auto()
    STARTS_WITH = auto()
    ENDS_WITH = auto()
    GREATER_THAN = auto()
    LESS_THAN = auto()
    REGEX = auto()


@dataclass
class FlagTargetingRule:
    """A single targeting condition evaluated against user attributes.

    Attributes:
        attribute: The user attribute key to evaluate (e.g., 'country',
                   'plan', 'user_id').
        operator: Comparison operator.
        value: The value to compare against.
        weight: Rule weight for priority ordering (higher = evaluated first).
    """

    attribute: str
    operator: TargetOperator
    value: Any
    weight: int = 0

    def evaluate(self, user_context: Dict[str, Any]) -> bool:
        """Return True if this rule matches the given user context."""
        attr_value = user_context.get(self.attribute)
        if attr_value is None:
            return False

        op = self.operator

        if op == TargetOperator.EQUALS:
            return attr_value == self.value
        elif op == TargetOperator.NOT_EQUALS:
            return attr_value != self.value
        elif op == TargetOperator.IN:
            return attr_value in (self.value if isinstance(self.value, (list, set, tuple)) else [self.value])
        elif op == TargetOperator.NOT_IN:
            return attr_value not in (self.value if isinstance(self.value, (list, set, tuple)) else [self.value])
        elif op == TargetOperator.CONTAINS:
            return str(self.value) in str(attr_value)
        elif op == TargetOperator.STARTS_WITH:
            return str(attr_value).startswith(str(self.value))
        elif op == TargetOperator.ENDS_WITH:
            return str(attr_value).endswith(str(self.value))
        elif op == TargetOperator.GREATER_THAN:
            return attr_value > self.value
        elif op == TargetOperator.LESS_THAN:
            return attr_value < self.value
        elif op == TargetOperator.REGEX:
            import re
            return bool(re.search(str(self.value), str(attr_value)))
        return False


@dataclass
class Flag:
    """A feature flag definition.

    Attributes:
        name: Unique flag identifier (e.g., 'new-checkout-flow').
        description: Human-readable description.
        flag_type: BOOLEAN or MULTIVARIATE.
        enabled: Master on/off switch.
        default_value: Value returned when flag is off or no rules match.
        targeting_rules: Ordered list of targeting rules (evaluated
                         by weight descending, then order).
        percentage: Rollout percentage (0-100). Uses hash-based
                    consistent assignment against user_id.
        environments: Set of environments where this flag can be active.
                      Empty means all environments.
        variants: For MULTIVARIATE flags, mapping of variant_name -> value.
        dependencies: Set of flag names that must be enabled for this
                      flag to be active.
        kill_switch: If True, the flag is forcibly disabled regardless
                     of all other settings (emergency override).
        created_at: Unix timestamp of creation.
        updated_at: Unix timestamp of last update.
        metadata: Arbitrary key-value metadata.
    """

    name: str
    description: str = ""
    flag_type: FlagType = FlagType.BOOLEAN
    enabled: bool = False
    default_value: Any = False
    targeting_rules: List[FlagTargetingRule] = field(default_factory=list)
    percentage: int = 0
    environments: Set[str] = field(default_factory=set)
    variants: Dict[str, Any] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set)
    kill_switch: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.percentage < 0 or self.percentage > 100:
            raise ValueError("percentage must be between 0 and 100")

    @property
    def is_active(self) -> bool:
        """Return True if the flag is not killed and is enabled."""
        return not self.kill_switch and self.enabled


@dataclass
class FlagEvaluationResult:
    """Result of evaluating a feature flag.

    Attributes:
        flag_name: The flag that was evaluated.
        value: The resolved value.
        matched: Whether any targeting rule matched.
        matched_rule_index: Index of the matched rule, or -1.
        reason: Human-readable explanation of why this value was returned.
        evaluated_at: Unix timestamp of evaluation.
    """

    flag_name: str
    value: Any
    matched: bool = False
    matched_rule_index: int = -1
    reason: str = ""
    evaluated_at: float = field(default_factory=time.time)


@dataclass
class FlagEvaluationContext:
    """Context for evaluating a feature flag.

    Attributes:
        user_id: A stable user identifier (used for percentage hashing).
        user_attributes: Arbitrary key-value attributes about the user.
        environment: Current environment name.
        flags_snapshot: Optional snapshot of all flag states for
                        dependency checking.
    """

    user_id: str = ""
    user_attributes: Dict[str, Any] = field(default_factory=dict)
    environment: str = "dev"
    flags_snapshot: Optional[Dict[str, Flag]] = None


# ---------------------------------------------------------------------------
# FeatureFlagManager
# ---------------------------------------------------------------------------


class FeatureFlagManager:
    """Central feature flag manager.

    Usage::

        mgr = FeatureFlagManager()

        # Define a flag
        mgr.register(Flag(
            name="dark-mode",
            enabled=True,
            percentage=25,
            targeting_rules=[
                FlagTargetingRule("plan", TargetOperator.EQUALS, "premium"),
            ],
        ))

        # Evaluate
        ctx = FlagEvaluationContext(
            user_id="user-123",
            user_attributes={"plan": "premium"},
            environment="production",
        )
        result = mgr.evaluate("dark-mode", ctx)
    """

    def __init__(self):
        self._flags: Dict[str, Flag] = {}
        self._evaluation_cache: Dict[str, Any] = {}
        self._cache_ttl: float = 30.0  # seconds

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, flag: Flag) -> None:
        """Register (or update) a feature flag."""
        if flag.name in self._flags:
            flag.created_at = self._flags[flag.name].created_at
        flag.updated_at = time.time()
        self._flags[flag.name] = flag

    def unregister(self, name: str) -> None:
        """Remove a feature flag."""
        self._flags.pop(name, None)
        self._evaluation_cache.pop(name, None)

    def get_flag(self, name: str) -> Optional[Flag]:
        """Return a flag definition by name, or None."""
        return self._flags.get(name)

    def list_flags(self) -> List[Flag]:
        """Return all registered flags."""
        return list(self._flags.values())

    def get_active_flags(self) -> List[Flag]:
        """Return flags that are enabled and not kill-switched."""
        return [f for f in self._flags.values() if f.is_active]

    def set_kill_switch(self, name: str, killed: bool = True) -> None:
        """Enable or disable the kill switch on a flag."""
        flag = self._flags.get(name)
        if flag is None:
            raise KeyError(f"Flag not found: {name}")
        flag.kill_switch = killed
        flag.updated_at = time.time()
        self._evaluation_cache.pop(name, None)

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        name: str,
        context: FlagEvaluationContext,
        *,
        use_cache: bool = True,
    ) -> FlagEvaluationResult:
        """Evaluate a feature flag for the given context.

        Resolution order:
            1. Kill switch   -> return default_value immediately
            2. Dependencies   -> if deps not enabled, return default_value
            3. Disabled       -> return default_value
            4. Environment    -> if flag has envs set & context.env not in set
            5. Targeting rules -> evaluate in order; first match wins
            6. Percentage     -> hash-based consistent rollout
            7. Default value

        Args:
            name: Flag name.
            context: Evaluation context (user, environment).
            use_cache: Whether to use the evaluation cache.

        Returns:
            FlagEvaluationResult with the resolved value and reasoning.
        """
        flag = self._flags.get(name)
        if flag is None:
            return FlagEvaluationResult(
                flag_name=name,
                value=False,
                reason=f"Flag '{name}' not found",
            )

        # Kill switch: immediate return
        if flag.kill_switch:
            return FlagEvaluationResult(
                flag_name=name,
                value=flag.default_value,
                reason="Flag is kill-switched",
            )

        # Dependency check
        if flag.dependencies:
            deps_context = context.flags_snapshot or {}
            for dep_name in flag.dependencies:
                dep_flag = deps_context.get(dep_name) or self._flags.get(dep_name)
                if dep_flag is None or not dep_flag.is_active:
                    return FlagEvaluationResult(
                        flag_name=name,
                        value=flag.default_value,
                        reason=f"Dependency '{dep_name}' is not enabled",
                    )

        # Master enabled check
        if not flag.enabled:
            return FlagEvaluationResult(
                flag_name=name,
                value=flag.default_value,
                reason="Flag is disabled",
            )

        # Environment check
        if flag.environments and context.environment not in flag.environments:
            return FlagEvaluationResult(
                flag_name=name,
                value=flag.default_value,
                reason=f"Environment '{context.environment}' not in allowed set",
            )

        # Targeting rules (sorted by weight desc, then insertion order)
        sorted_rules = sorted(
            enumerate(flag.targeting_rules),
            key=lambda x: x[1].weight,
            reverse=True,
        )
        for idx, rule in sorted_rules:
            if rule.evaluate(context.user_attributes):
                return FlagEvaluationResult(
                    flag_name=name,
                    value=True if flag.flag_type == FlagType.BOOLEAN else self._resolve_variant(flag, context),
                    matched=True,
                    matched_rule_index=idx,
                    reason=f"Rule {idx} matched: {rule.attribute} {rule.operator.name} {rule.value}",
                )

        # Percentage rollout
        if flag.percentage > 0:
            in_rollout = self._is_in_percentage(flag.name, context.user_id, flag.percentage)
            if in_rollout:
                value = True if flag.flag_type == FlagType.BOOLEAN else self._resolve_variant(flag, context)
                return FlagEvaluationResult(
                    flag_name=name,
                    value=value,
                    matched=True,
                    reason=f"User in {flag.percentage}% rollout",
                )
            else:
                return FlagEvaluationResult(
                    flag_name=name,
                    value=flag.default_value,
                    reason=f"User not in {flag.percentage}% rollout",
                )

        # Fall through to default
        # For boolean flags that are enabled with no restrictions at all
        # (no targeting rules, no percentage), the flag value is simply True.
        if (
            flag.flag_type == FlagType.BOOLEAN
            and flag.enabled
            and not flag.targeting_rules
            and flag.percentage <= 0
        ):
            return FlagEvaluationResult(
                flag_name=name,
                value=True,
                reason="Flag enabled with no restrictions; returning True",
            )
        return FlagEvaluationResult(
            flag_name=name,
            value=flag.default_value,
            reason="No rules or percentage matched; using default",
        )

    def evaluate_all(
        self, context: FlagEvaluationContext
    ) -> Dict[str, FlagEvaluationResult]:
        """Evaluate all registered flags for *context*."""
        results: Dict[str, FlagEvaluationResult] = {}
        for name in self._flags:
            results[name] = self.evaluate(name, context, use_cache=False)
        return results

    def is_enabled(self, name: str, context: FlagEvaluationContext) -> bool:
        """Convenience: evaluate flag and return boolean."""
        result = self.evaluate(name, context)
        return bool(result.value)

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def clear_cache(self) -> None:
        """Clear the evaluation cache."""
        self._evaluation_cache.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_in_percentage(
        flag_name: str, user_id: str, percentage: int
    ) -> bool:
        """Consistent hash-based percentage assignment.

        Uses SHA-256 of ``flag_name:user_id``, maps to 0-100 range.
        """
        if percentage <= 0:
            return False
        if percentage >= 100:
            return True

        seed = f"{flag_name}:{user_id}".encode("utf-8")
        digest = hashlib.sha256(seed).digest()
        # Use first 8 bytes as an integer, mod 100
        bucket = int.from_bytes(digest[:8], "big") % 100
        return bucket < percentage

    @staticmethod
    def _resolve_variant(flag: Flag, context: FlagEvaluationContext) -> Any:
        """For multivariate flags, select a variant using consistent hashing."""
        if not flag.variants:
            return flag.default_value

        variant_names = sorted(flag.variants.keys())
        seed = f"{flag.name}:{context.user_id}:variant".encode("utf-8")
        digest = hashlib.sha256(seed).digest()
        bucket = int.from_bytes(digest[:8], "big") % len(variant_names)
        chosen = variant_names[bucket]
        return flag.variants[chosen]


# ---------------------------------------------------------------------------
# Utility: build dependency graph for validation
# ---------------------------------------------------------------------------

def validate_flag_dependencies(flags: Dict[str, Flag]) -> List[str]:
    """Validate that all flag dependencies exist and there are no cycles.

    Returns a list of error strings (empty if valid).
    """
    errors: List[str] = []

    # Check all referenced dependencies exist
    for name, flag in flags.items():
        for dep in flag.dependencies:
            if dep not in flags:
                errors.append(
                    f"Flag '{name}' depends on '{dep}', which does not exist"
                )

    # Cycle detection via DFS
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {name: WHITE for name in flags}

    def dfs(node: str) -> bool:
        """Return True if a cycle is detected."""
        color[node] = GRAY
        for dep in flags[node].dependencies:
            if dep not in color:
                # Already reported in the initial check above; skip
                continue
            if color[dep] == GRAY:
                errors.append(
                    f"Circular dependency detected: {node} -> {dep}"
                )
                return True
            if color[dep] == WHITE:
                if dfs(dep):
                    return True
        color[node] = BLACK
        return False

    for name in flags:
        if color[name] == WHITE:
            dfs(name)

    return errors