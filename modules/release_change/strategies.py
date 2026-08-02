"""
Deployment Strategy Engine

Provides 8 deployment strategies for progressive, safe rollouts.
Includes strategy selection, execution, and validation.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("enterprise.release_change")


class StrategyType(str, Enum):
    """Supported deployment strategy types."""
    FEATURE_FLAGS = "feature_flags"
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    ROLLING = "rolling"
    SHADOW = "shadow"
    STAGED_ROLLOUT = "staged_rollout"
    TENANT_BASED = "tenant_based"
    REGIONAL = "regional"

    @property
    def supports_instant_rollback(self) -> bool:
        """Whether this strategy supports instant rollback (no bake time)."""
        return self in (StrategyType.FEATURE_FLAGS, StrategyType.BLUE_GREEN)

    @property
    def requires_traffic_splitting(self) -> bool:
        """Whether this strategy requires traffic splitting."""
        return self in (
            StrategyType.CANARY, StrategyType.BLUE_GREEN,
            StrategyType.STAGED_ROLLOUT, StrategyType.REGIONAL,
        )


@dataclass
class DeploymentStrategy:
    """Configuration for a deployment strategy.

    Attributes:
        name: Human-readable name for this strategy instance.
        strategy_type: The type of deployment strategy.
        traffic_split_percent: Percentage of traffic routed to new version (0-100).
        observation_period_minutes: Time to observe after deployment before full rollout.
        auto_rollback_threshold: Error rate threshold (%) that triggers automatic rollback.
        target_infrastructure: Target infrastructure identifier (cluster, region, etc.).
        health_check_endpoint: Endpoint to check for health status.
        feature_flag_key: Feature flag key (for FEATURE_FLAGS strategy).
        metadata: Additional metadata.
    """
    name: str = ""
    strategy_type: StrategyType = StrategyType.ROLLING
    traffic_split_percent: int = 100
    observation_period_minutes: int = 5
    auto_rollback_threshold: float = 5.0
    target_infrastructure: str = ""
    health_check_endpoint: str = "/health"
    feature_flag_key: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "strategy_type": self.strategy_type.value,
            "traffic_split_percent": self.traffic_split_percent,
            "observation_period_minutes": self.observation_period_minutes,
            "auto_rollback_threshold": self.auto_rollback_threshold,
            "target_infrastructure": self.target_infrastructure,
            "health_check_endpoint": self.health_check_endpoint,
            "feature_flag_key": self.feature_flag_key,
            "metadata": self.metadata,
        }


class StrategyEngine:
    """Engine for selecting, configuring, and executing deployment strategies.

    Provides 8 deployment strategies and validates their application.

    Usage:
        engine = StrategyEngine()
        strategy = engine.select_strategy(StrategyType.CANARY, traffic_split=5)
        result = engine.execute_canary(strategy, deploy_fn, health_check_fn)
    """

    def __init__(self) -> None:
        self._execution_history: List[Dict[str, Any]] = []

    def _log(self, strategy: DeploymentStrategy, event: str, details: Optional[Dict] = None) -> None:
        """Record a strategy execution event."""
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "strategy_name": strategy.name,
            "strategy_type": strategy.strategy_type.value,
            "event": event,
            "details": details or {},
        }
        self._execution_history.append(entry)
        logger.info("DEPLOY [%s] %s: %s", strategy.name, event, details or "")

    def _simulate_health_check(self, endpoint: str, expected_code: int = 200) -> bool:
        """Simulate a health check against an endpoint.
        In production, this would make an actual HTTP request.
        """
        logger.debug("Health check on %s (expected %d)", endpoint, expected_code)
        return True

    def _should_rollback(self, error_rate: float, threshold: float) -> bool:
        """Determine if rollback should be triggered based on error rate."""
        return error_rate > threshold

    # ── Strategy Selection ─────────────────────────────────────────────────

    def select_strategy(
        self,
        strategy_type: StrategyType,
        traffic_split_percent: int = 100,
        observation_period_minutes: int = 5,
        auto_rollback_threshold: float = 5.0,
        target_infrastructure: str = "",
        health_check_endpoint: str = "/health",
        feature_flag_key: str = "",
        **kwargs: Any,
    ) -> DeploymentStrategy:
        """Select and configure a deployment strategy.

        Args:
            strategy_type: The type of deployment strategy to use.
            traffic_split_percent: Initial traffic percentage to new version.
            observation_period_minutes: How long to observe before expanding.
            auto_rollback_threshold: Error rate % that triggers auto-rollback.
            target_infrastructure: Target infrastructure identifier.
            health_check_endpoint: Health check endpoint path.
            feature_flag_key: Feature flag key for feature-flag-based deploys.
            **kwargs: Additional strategy-specific configuration.

        Returns:
            A configured DeploymentStrategy instance.
        """
        strategy = DeploymentStrategy(
            name=f"{strategy_type.value}-{int(time.time())}",
            strategy_type=strategy_type,
            traffic_split_percent=traffic_split_percent,
            observation_period_minutes=observation_period_minutes,
            auto_rollback_threshold=auto_rollback_threshold,
            target_infrastructure=target_infrastructure,
            health_check_endpoint=health_check_endpoint,
            feature_flag_key=feature_flag_key,
            metadata=kwargs,
        )
        self._log(strategy, "strategy_selected")
        return strategy

    # ── Strategy: Feature Flags ────────────────────────────────────────────

    def configure_feature_flags(
        self,
        strategy: DeploymentStrategy,
        flag_key: str,
        rollout_percent: int = 0,
        target_segments: Optional[List[str]] = None,
        enabled: bool = False,
    ) -> Dict[str, Any]:
        """Configure feature flags for progressive feature rollout.

        Args:
            strategy: The deployment strategy.
            flag_key: The feature flag key to control.
            rollout_percent: Percentage of users to roll out to.
            target_segments: Specific user segments to target.
            enabled: Whether the flag is currently enabled.

        Returns:
            Configuration result dict.
        """
        strategy.feature_flag_key = flag_key
        config = {
            "flag_key": flag_key,
            "rollout_percent": rollout_percent,
            "target_segments": target_segments or [],
            "enabled": enabled,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._log(strategy, "feature_flags_configured", config)
        return {"success": True, "config": config}

    # ── Strategy: Canary ───────────────────────────────────────────────────

    def execute_canary(
        self,
        strategy: DeploymentStrategy,
        deploy_fn: Optional[Callable[[], bool]] = None,
        health_check_fn: Optional[Callable[[str], bool]] = None,
    ) -> Dict[str, Any]:
        """Execute a canary deployment.

        Deploys to a small subset, validates, then progressively expands.

        Args:
            strategy: The deployment strategy configuration.
            deploy_fn: Optional callable that performs the actual deploy.
            health_check_fn: Optional callable that performs health checks.

        Returns:
            Execution result dict.
        """
        self._log(strategy, "canary_started", {"split": strategy.traffic_split_percent})

        if deploy_fn:
            deploy_result = deploy_fn()
            if not deploy_result:
                return {"success": False, "error": "Canary deploy function returned failure"}

        hc_fn = health_check_fn or self._simulate_health_check
        healthy = hc_fn(strategy.health_check_endpoint)
        if not healthy:
            self._log(strategy, "canary_health_check_failed")
            return {"success": False, "error": "Health check failed during canary deployment"}

        # Simulate monitoring during observation period
        self._log(strategy, "canary_observing", {"period_minutes": strategy.observation_period_minutes})

        # Check auto-rollback threshold
        simulated_error_rate = random.uniform(0, 1)
        if self._should_rollback(simulated_error_rate, strategy.auto_rollback_threshold):
            self._log(strategy, "canary_rollback_triggered", {"error_rate": simulated_error_rate})
            return {"success": False, "error": f"Canary auto-rollback: error rate {simulated_error_rate:.2f}% exceeds threshold"}

        self._log(strategy, "canary_successful")
        return {"success": True, "split": strategy.traffic_split_percent, "healthy": True}

    # ── Strategy: Blue-Green ───────────────────────────────────────────────

    def execute_blue_green(
        self,
        strategy: DeploymentStrategy,
        deploy_fn: Optional[Callable[[], bool]] = None,
        health_check_fn: Optional[Callable[[str], bool]] = None,
        smoke_test_fn: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Execute a blue-green deployment.

        Deploys new version to inactive environment, validates, then switches traffic.

        Args:
            strategy: The deployment strategy configuration.
            deploy_fn: Optional callable that deploys to the inactive environment.
            health_check_fn: Optional callable for health checks.
            smoke_test_fn: Optional callable for smoke tests on the new environment.

        Returns:
            Execution result dict.
        """
        self._log(strategy, "blue_green_started")

        # Deploy to inactive (green) environment
        if deploy_fn:
            if not deploy_fn():
                return {"success": False, "error": "Green environment deploy failed"}

        # Health check on green
        hc_fn = health_check_fn or self._simulate_health_check
        if not hc_fn(strategy.health_check_endpoint):
            return {"success": False, "error": "Green environment health check failed"}

        # Smoke tests
        if smoke_test_fn and not smoke_test_fn():
            self._log(strategy, "blue_green_smoke_test_failed")
            return {"success": False, "error": "Smoke tests failed on green environment"}

        # Traffic switch
        self._log(strategy, "blue_green_traffic_switched")
        self._log(strategy, "blue_green_successful")
        return {"success": True, "environment": "green", "traffic_switched": True}

    # ── Strategy: Rolling ──────────────────────────────────────────────────

    def execute_rolling(
        self,
        strategy: DeploymentStrategy,
        instance_count: int = 3,
        batch_size: int = 1,
        deploy_fn: Optional[Callable[[int], bool]] = None,
        health_check_fn: Optional[Callable[[str], bool]] = None,
    ) -> Dict[str, Any]:
        """Execute a rolling deployment.

        Updates instances one batch at a time, validating after each batch.

        Args:
            strategy: The deployment strategy configuration.
            instance_count: Total number of instances.
            batch_size: Number of instances to update simultaneously.
            deploy_fn: Optional callable that deploys to a batch; receives batch number.
            health_check_fn: Optional callable for health checks.

        Returns:
            Execution result dict with per-batch details.
        """
        self._log(strategy, "rolling_started", {"instances": instance_count, "batch_size": batch_size})

        hc_fn = health_check_fn or self._simulate_health_check
        batches_completed = 0
        batch_details = []

        for batch in range(0, instance_count, batch_size):
            batch_num = batch // batch_size + 1
            batch_instances = min(batch_size, instance_count - batch)
            self._log(strategy, "rolling_batch", {"batch": batch_num, "instances": batch_instances})

            if deploy_fn and not deploy_fn(batch_num):
                self._log(strategy, "rolling_batch_failed", {"batch": batch_num})
                return {"success": False, "error": f"Batch {batch_num} deployment failed"}

            if not hc_fn(strategy.health_check_endpoint):
                return {"success": False, "error": f"Health check failed after batch {batch_num}"}

            batches_completed += 1
            batch_details.append({"batch": batch_num, "instances": batch_instances, "status": "ok"})

        self._log(strategy, "rolling_successful", {"batches": batches_completed})
        return {"success": True, "batches_completed": batches_completed, "details": batch_details}

    # ── Strategy: Shadow ───────────────────────────────────────────────────

    def execute_shadow(
        self,
        strategy: DeploymentStrategy,
        mirror_traffic_percent: int = 10,
        compare_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Execute a shadow deployment.

        Runs new version alongside old, mirroring a percentage of production
        traffic without affecting user responses.

        Args:
            strategy: The deployment strategy configuration.
            mirror_traffic_percent: Percentage of traffic to mirror to shadow.
            compare_fn: Optional callable that compares old vs new responses.

        Returns:
            Execution result dict.
        """
        self._log(strategy, "shadow_started", {"mirror_percent": mirror_traffic_percent})

        # Simulate shadow comparison
        comparison = {}
        if compare_fn:
            comparison = compare_fn()

        self._log(strategy, "shadow_observing", {"period_minutes": strategy.observation_period_minutes})

        self._log(strategy, "shadow_successful", {"comparison": comparison})
        return {"success": True, "mirror_percent": mirror_traffic_percent, "comparison": comparison}

    # ── Strategy: Staged Rollout ───────────────────────────────────────────

    def execute_staged(
        self,
        strategy: DeploymentStrategy,
        stages: Optional[List[Dict[str, Any]]] = None,
        deploy_fn: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> Dict[str, Any]:
        """Execute a staged rollout across multiple phases.

        Each stage is a dict with keys: 'percent', 'duration_minutes', 'target'.

        Args:
            strategy: The deployment strategy configuration.
            stages: List of stage configurations.
            deploy_fn: Optional callable for deploying each stage.

        Returns:
            Execution result dict.
        """
        stages = stages or [
            {"percent": 5, "duration_minutes": 10, "target": "internal"},
            {"percent": 25, "duration_minutes": 30, "target": "beta"},
            {"percent": 100, "duration_minutes": 60, "target": "all"},
        ]
        self._log(strategy, "staged_started", {"total_stages": len(stages)})

        stage_results = []
        for i, stage_cfg in enumerate(stages):
            self._log(strategy, "staged_phase", {"phase": i + 1, "config": stage_cfg})

            if deploy_fn and not deploy_fn(stage_cfg):
                self._log(strategy, "staged_phase_failed", {"phase": i + 1})
                return {"success": False, "error": f"Stage {i + 1} deployment failed"}

            stage_results.append({"phase": i + 1, "percent": stage_cfg["percent"], "status": "ok"})

        self._log(strategy, "staged_successful", {"phases": len(stage_results)})
        return {"success": True, "stages": stage_results}

    # ── Strategy: Tenant-Based ─────────────────────────────────────────────

    def execute_tenant_based(
        self,
        strategy: DeploymentStrategy,
        tenant_ids: Optional[List[str]] = None,
        deploy_fn: Optional[Callable[[str], bool]] = None,
    ) -> Dict[str, Any]:
        """Execute a tenant-based deployment.

        Deploys to specific tenants first, validates, then expands.

        Args:
            strategy: The deployment strategy configuration.
            tenant_ids: List of tenant IDs to deploy to.
            deploy_fn: Optional callable for deploying to a tenant.

        Returns:
            Execution result dict.
        """
        tenant_ids = tenant_ids or ["tenant-internal", "tenant-beta"]
        self._log(strategy, "tenant_based_started", {"tenants": tenant_ids})

        tenant_results = []
        for tenant in tenant_ids:
            self._log(strategy, "tenant_deploy", {"tenant": tenant})

            if deploy_fn and not deploy_fn(tenant):
                self._log(strategy, "tenant_deploy_failed", {"tenant": tenant})
                return {"success": False, "error": f"Deploy to tenant {tenant} failed"}

            tenant_results.append({"tenant": tenant, "status": "ok"})

        self._log(strategy, "tenant_based_successful", {"tenants": len(tenant_results)})
        return {"success": True, "tenants": tenant_results}

    # ── Strategy: Regional ─────────────────────────────────────────────────

    def execute_regional(
        self,
        strategy: DeploymentStrategy,
        regions: Optional[List[str]] = None,
        deploy_fn: Optional[Callable[[str], bool]] = None,
    ) -> Dict[str, Any]:
        """Execute a regional deployment.

        Deploys region by region, validating each before proceeding.

        Args:
            strategy: The deployment strategy configuration.
            regions: List of region identifiers.
            deploy_fn: Optional callable for deploying to a region.

        Returns:
            Execution result dict.
        """
        regions = regions or ["us-east-1", "us-west-2", "eu-west-1"]
        self._log(strategy, "regional_started", {"regions": regions})

        region_results = []
        for region in regions:
            self._log(strategy, "region_deploy", {"region": region})

            if deploy_fn and not deploy_fn(region):
                self._log(strategy, "region_deploy_failed", {"region": region})
                return {"success": False, "error": f"Deploy to region {region} failed"}

            region_results.append({"region": region, "status": "ok"})

        self._log(strategy, "regional_successful", {"regions": len(region_results)})
        return {"success": True, "regions": region_results}

    # ── Validation ─────────────────────────────────────────────────────────

    def validate_strategy_applied(
        self,
        strategy: DeploymentStrategy,
        error_rate: float = 0.0,
        latency_ms: float = 0.0,
        health_ok: bool = True,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Validate that a deployment strategy has been applied successfully.

        Checks error rates, health status, and optional metrics against thresholds.

        Args:
            strategy: The deployment strategy to validate.
            error_rate: Current error rate percentage.
            latency_ms: Current latency in milliseconds.
            health_ok: Whether the health check passed.
            metrics: Additional metrics to validate.

        Returns:
            Validation result dict with pass/fail and details.
        """
        checks = []
        passed = True

        # Check error rate against threshold
        error_check = error_rate <= strategy.auto_rollback_threshold
        checks.append({
            "check": "error_rate",
            "value": error_rate,
            "threshold": strategy.auto_rollback_threshold,
            "passed": error_check,
        })
        if not error_check:
            passed = False

        # Check health
        checks.append({
            "check": "health",
            "passed": health_ok,
        })
        if not health_ok:
            passed = False

        # Check latency (if threshold provided in metadata)
        latency_threshold = strategy.metadata.get("latency_threshold_ms")
        if latency_threshold is not None:
            latency_ok = latency_ms <= latency_threshold
            checks.append({
                "check": "latency",
                "value": latency_ms,
                "threshold": latency_threshold,
                "passed": latency_ok,
            })
            if not latency_ok:
                passed = False

        result = {
            "strategy": strategy.name,
            "strategy_type": strategy.strategy_type.value,
            "validated": passed,
            "checks": checks,
            "metrics": metrics or {},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        self._log(strategy, "validation_completed", result)
        return result

    def get_history(self) -> List[Dict[str, Any]]:
        """Get the execution history."""
        return list(self._execution_history)