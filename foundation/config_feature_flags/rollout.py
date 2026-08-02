"""
Gradual rollout management with staged rollouts, canary releases,
and automatic rollback on error thresholds.

Stages follow a predefined sequence:
    1% -> 10% -> 25% -> 50% -> 100%

Canary releases deploy to a small subset first; if error rates are
acceptable, the canary is promoted to a full rollout.

Automatic rollback: if the error rate exceeds a configurable threshold,
the rollout is rolled back to the previous stable stage.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class RolloutStage(Enum):
    """Predefined rollout stages with percentage values."""
    STAGE_0 = 0      # 0%
    STAGE_1 = 1      # 1%
    STAGE_10 = 10    # 10%
    STAGE_25 = 25    # 25%
    STAGE_50 = 50    # 50%
    STAGE_100 = 100  # 100% (fully rolled out)

    @classmethod
    def from_percentage(cls, pct: int) -> "RolloutStage":
        """Return the closest stage for a given percentage."""
        for stage in cls:
            if stage.value >= pct:
                return stage
        return cls.STAGE_100


class RolloutStatus(Enum):
    """Current status of a rollout."""
    PENDING = auto()       # Not yet started
    IN_PROGRESS = auto()   # Actively rolling out
    PAUSED = auto()        # Temporarily paused
    COMPLETED = auto()     # Fully rolled out
    ROLLED_BACK = auto()   # Rolled back to previous stage
    FAILED = auto()        # Irrecoverable failure


@dataclass
class RolloutConfig:
    """Configuration for a rollout.

    Attributes:
        name: Rollout identifier (e.g., 'payment-v2').
        stages: Ordered list of stages to progress through.
        pause_duration: Seconds to wait between stage promotions
                        (cooldown / observation period).
        error_threshold: Error rate (0.0-1.0) above which automatic
                         rollback is triggered.
        canary_percentage: Percentage for the initial canary deployment
                           (default 1%).
        canary_duration: How long the canary runs before promotion decision.
        health_check: Optional callable that returns (healthy: bool, details: str).
        metadata: Arbitrary key-value metadata.
    """

    name: str
    stages: List[RolloutStage] = field(default_factory=lambda: [
        RolloutStage.STAGE_1,
        RolloutStage.STAGE_10,
        RolloutStage.STAGE_25,
        RolloutStage.STAGE_50,
        RolloutStage.STAGE_100,
    ])
    pause_duration: float = 300.0  # 5 minutes default
    error_threshold: float = 0.05  # 5%
    canary_percentage: int = 1
    canary_duration: float = 600.0  # 10 minutes
    health_check: Optional[Callable[[], Tuple[bool, str]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 <= self.error_threshold <= 1.0:
            raise ValueError("error_threshold must be between 0.0 and 1.0")
        if not 0 <= self.canary_percentage <= 100:
            raise ValueError("canary_percentage must be between 0 and 100")


@dataclass
class CanaryRelease:
    """A canary release running alongside the stable version.

    Attributes:
        name: Identifier.
        percentage: Traffic percentage routed to the canary.
        started_at: Unix timestamp when the canary was started.
        duration: How long the canary should run.
        metrics: Collected metrics during the canary period
                 (e.g., {"error_rate": 0.01, "latency_p99": 250}).
    """

    name: str
    percentage: int = 1
    started_at: float = field(default_factory=time.time)
    duration: float = 600.0
    metrics: Dict[str, float] = field(default_factory=dict)

    @property
    def elapsed(self) -> float:
        """Seconds since the canary started."""
        return time.time() - self.started_at

    @property
    def is_complete(self) -> bool:
        """Whether the canary duration has elapsed."""
        return self.elapsed >= self.duration

    def record_metric(self, key: str, value: float) -> None:
        """Record a metric reading."""
        self.metrics[key] = value


@dataclass
class RolloutState:
    """Current state of a rollout.

    Attributes:
        name: Rollout name.
        status: Current status.
        current_stage: Currently active stage.
        target_stage: The stage being rolled toward.
        current_percentage: Actual traffic percentage.
        started_at: When the rollout began.
        stage_promoted_at: When the current stage was promoted.
        error_rate: Current observed error rate.
        error_count: Total errors observed in the current stage.
        request_count: Total requests in the current stage.
        history: List of (timestamp, from_stage, to_stage, reason) tuples.
    """

    name: str
    status: RolloutStatus = RolloutStatus.PENDING
    current_stage: RolloutStage = RolloutStage.STAGE_0
    target_stage: RolloutStage = RolloutStage.STAGE_100
    current_percentage: int = 0
    started_at: float = field(default_factory=time.time)
    stage_promoted_at: float = field(default_factory=time.time)
    error_rate: float = 0.0
    error_count: int = 0
    request_count: int = 0
    history: List[Tuple[float, RolloutStage, RolloutStage, str]] = field(
        default_factory=list
    )


# ---------------------------------------------------------------------------
# RolloutManager
# ---------------------------------------------------------------------------


class RolloutManager:
    """Manages gradual rollouts, canary releases, and automatic rollback.

    Usage::

        mgr = RolloutManager()

        # Start a rollout
        state = mgr.start_rollout(RolloutConfig(name="search-v2"))

        # Report results as they come in
        mgr.report_result("search-v2", success=True)

        # Advance to next stage (may happen automatically based on thresholds)
        mgr.advance_stage("search-v2")

        # Or start a canary first
        canary = mgr.start_canary("search-v2-canary", percentage=5)
        if mgr.should_promote_canary(canary):
            mgr.promote_canary(canary, "search-v2")
    """

    def __init__(self):
        self._rollouts: Dict[str, RolloutState] = {}
        self._configs: Dict[str, RolloutConfig] = {}
        self._canaries: Dict[str, CanaryRelease] = {}
        self._on_rollback: List[Callable[[str, RolloutState], None]] = []
        self._on_promote: List[Callable[[str, RolloutStage], None]] = []

    # ------------------------------------------------------------------
    # Rollout lifecycle
    # ------------------------------------------------------------------

    def start_rollout(self, config: RolloutConfig) -> RolloutState:
        """Begin a new rollout for *config*.

        Raises ValueError if a rollout with the same name is already active.
        """
        if config.name in self._rollouts:
            existing = self._rollouts[config.name]
            if existing.status in (RolloutStatus.IN_PROGRESS, RolloutStatus.PAUSED):
                raise ValueError(f"Rollout '{config.name}' is already active")

        self._configs[config.name] = config

        state = RolloutState(
            name=config.name,
            status=RolloutStatus.IN_PROGRESS,
            current_stage=config.stages[0] if config.stages else RolloutStage.STAGE_0,
            target_stage=config.stages[-1] if config.stages else RolloutStage.STAGE_100,
            current_percentage=config.stages[0].value if config.stages else 0,
            started_at=time.time(),
            stage_promoted_at=time.time(),
        )
        self._rollouts[config.name] = state
        state.history.append(
            (time.time(), RolloutStage.STAGE_0, state.current_stage, "Rollout started")
        )
        return state

    def advance_stage(self, name: str) -> RolloutState:
        """Advance *name* to the next stage in its sequence.

        Returns the updated state.
        Raises KeyError if the rollout is not found.
        """
        state = self._get_state(name)
        config = self._configs.get(name)
        if config is None:
            raise KeyError(f"No config found for rollout '{name}'")

        # Find the index of the current stage
        try:
            idx = config.stages.index(state.current_stage)
        except ValueError:
            # Current stage not in the configured stages; find next available
            idx = -1
            for i, s in enumerate(config.stages):
                if s.value > state.current_percentage:
                    idx = i - 1
                    break

        next_idx = idx + 1
        if next_idx >= len(config.stages):
            # Already at final stage
            state.status = RolloutStatus.COMPLETED
            state.current_percentage = 100
            state.history.append(
                (time.time(), state.current_stage, state.current_stage, "Rollout complete")
            )
            return state

        prev_stage = state.current_stage
        next_stage = config.stages[next_idx]

        # Check error threshold before promoting
        if state.request_count > 0 and state.error_rate > config.error_threshold:
            state.status = RolloutStatus.PAUSED
            state.history.append(
                (time.time(), prev_stage, prev_stage,
                 f"Paused: error rate {state.error_rate:.2%} exceeds threshold "
                 f"{config.error_threshold:.2%}")
            )
            return state

        state.current_stage = next_stage
        state.current_percentage = next_stage.value
        state.stage_promoted_at = time.time()
        state.history.append(
            (time.time(), prev_stage, next_stage,
             f"Advanced to {next_stage.value}%")
        )

        if next_stage == config.stages[-1]:
            state.status = RolloutStatus.COMPLETED

        # Fire promotion callbacks
        for cb in self._on_promote:
            cb(name, next_stage)

        return state

    def rollback(self, name: str, reason: str = "") -> RolloutState:
        """Roll back *name* to the previous stage.

        If already at the first stage, sets percentage to 0 and status
        to ROLLED_BACK.
        """
        state = self._get_state(name)
        config = self._configs.get(name)

        prev_stage = state.current_stage

        if config and state.current_stage in config.stages:
            idx = config.stages.index(state.current_stage)
            if idx > 0:
                state.current_stage = config.stages[idx - 1]
                state.current_percentage = state.current_stage.value
            else:
                state.current_stage = RolloutStage.STAGE_0
                state.current_percentage = 0
        else:
            state.current_stage = RolloutStage.STAGE_0
            state.current_percentage = 0

        state.status = RolloutStatus.ROLLED_BACK
        state.history.append(
            (time.time(), prev_stage, state.current_stage,
             f"Rolled back: {reason}" if reason else "Rolled back")
        )

        # Reset error counters on rollback
        state.error_count = 0
        state.request_count = 0
        state.error_rate = 0.0

        # Fire rollback callbacks
        for cb in self._on_rollback:
            cb(name, state)

        return state

    def pause(self, name: str) -> RolloutState:
        """Pause a rollout at its current stage."""
        state = self._get_state(name)
        state.status = RolloutStatus.PAUSED
        state.history.append(
            (time.time(), state.current_stage, state.current_stage, "Paused")
        )
        return state

    def resume(self, name: str) -> RolloutState:
        """Resume a paused rollout."""
        state = self._get_state(name)
        if state.status == RolloutStatus.PAUSED:
            state.status = RolloutStatus.IN_PROGRESS
            state.history.append(
                (time.time(), state.current_stage, state.current_stage, "Resumed")
            )
        return state

    # ------------------------------------------------------------------
    # Error tracking
    # ------------------------------------------------------------------

    def report_result(
        self, name: str, success: bool, count: int = 1
    ) -> Optional[RolloutState]:
        """Report outcome(s) for a rollout.

        If the cumulative error rate exceeds the threshold, an automatic
        rollback is triggered.  Returns the (possibly updated) state.
        """
        state = self._get_state(name)
        config = self._configs.get(name)

        state.request_count += count
        if not success:
            state.error_count += count

        if state.request_count > 0:
            state.error_rate = state.error_count / state.request_count

        # Automatic rollback check
        if config and state.request_count > 10:  # minimum sample
            if state.error_rate > config.error_threshold:
                return self.rollback(
                    name,
                    f"Auto-rollback: error rate {state.error_rate:.2%} "
                    f"exceeds threshold {config.error_threshold:.2%}",
                )

        return state

    def reset_metrics(self, name: str) -> None:
        """Reset error counters for a new stage observation period."""
        state = self._get_state(name)
        state.error_count = 0
        state.request_count = 0
        state.error_rate = 0.0

    # ------------------------------------------------------------------
    # Canary releases
    # ------------------------------------------------------------------

    def start_canary(
        self, name: str, percentage: int = 1, duration: float = 600.0
    ) -> CanaryRelease:
        """Start a new canary release.

        Args:
            name: Canary identifier.
            percentage: Traffic percentage for the canary.
            duration: How long to run before promotion decision.

        Returns:
            The CanaryRelease object.
        """
        if name in self._canaries:
            raise ValueError(f"Canary '{name}' already exists")
        canary = CanaryRelease(
            name=name, percentage=percentage, duration=duration
        )
        self._canaries[name] = canary
        return canary

    def get_canary(self, name: str) -> Optional[CanaryRelease]:
        """Return a canary by name, or None."""
        return self._canaries.get(name)

    def should_promote_canary(
        self, canary: CanaryRelease, error_threshold: float = 0.05
    ) -> Tuple[bool, str]:
        """Determine whether a canary should be promoted to full rollout.

        Returns (should_promote: bool, reason: str).
        """
        if not canary.is_complete:
            return False, f"Canary still running ({canary.elapsed:.0f}s / {canary.duration:.0f}s)"

        error_rate = canary.metrics.get("error_rate", 0.0)
        if error_rate > error_threshold:
            return False, f"Error rate {error_rate:.2%} exceeds threshold {error_threshold:.2%}"

        return True, "Canary metrics acceptable"

    def promote_canary(self, canary: CanaryRelease, rollout_name: str) -> RolloutState:
        """Promote a successful canary into a rollout.

        If the rollout does not exist, one is created automatically.
        """
        if rollout_name not in self._rollouts:
            config = RolloutConfig(
                name=rollout_name,
                canary_percentage=canary.percentage,
            )
            self.start_rollout(config)

        state = self._get_state(rollout_name)
        state.current_percentage = canary.percentage
        state.history.append(
            (time.time(), state.current_stage, state.current_stage,
             f"Canary '{canary.name}' promoted at {canary.percentage}%")
        )

        # Clean up the canary
        self._canaries.pop(canary.name, None)
        return state

    def abort_canary(self, name: str) -> None:
        """Abort a canary release."""
        self._canaries.pop(name, None)

    def list_canaries(self) -> List[CanaryRelease]:
        """Return all active canaries."""
        return list(self._canaries.values())

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_state(self, name: str) -> Optional[RolloutState]:
        """Return rollout state by name, or None."""
        return self._rollouts.get(name)

    def list_rollouts(self) -> List[RolloutState]:
        """Return all rollout states."""
        return list(self._rollouts.values())

    def list_active_rollouts(self) -> List[RolloutState]:
        """Return rollouts that are in progress or paused."""
        return [
            s for s in self._rollouts.values()
            if s.status in (RolloutStatus.IN_PROGRESS, RolloutStatus.PAUSED)
        ]

    def need_stage_advancement(self, name: str) -> bool:
        """Check if enough time has passed to advance to the next stage."""
        state = self._get_state(name)
        config = self._configs.get(name)
        if config is None:
            return False
        if state.status != RolloutStatus.IN_PROGRESS:
            return False
        elapsed = time.time() - state.stage_promoted_at
        return elapsed >= config.pause_duration

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_rollback(self, callback: Callable[[str, RolloutState], None]) -> None:
        """Register a callback invoked when any rollout is rolled back."""
        self._on_rollback.append(callback)

    def on_promote(self, callback: Callable[[str, RolloutStage], None]) -> None:
        """Register a callback invoked when any rollout advances a stage."""
        self._on_promote.append(callback)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_state(self, name: str) -> RolloutState:
        """Get rollout state, raising KeyError if not found."""
        state = self._rollouts.get(name)
        if state is None:
            raise KeyError(f"Rollout not found: {name}")
        return state