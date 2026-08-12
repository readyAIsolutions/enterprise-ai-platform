"""Tests for the Canary Manager rollout state machine."""

from modules.mlops_lifecycle.canary_manager import (
    CanaryManager,
    CanaryMetrics,
    RolloutPhase,
    RolloutStrategy,
    create_canary_manager,
)


def test_create_canary_manager_returns_default_instance():
    mgr = create_canary_manager()
    assert isinstance(mgr, CanaryManager)


def test_default_canary_starts_at_initial_percentage():
    mgr = CanaryManager()
    dep = mgr.create_deployment("v1.2", initial_percentage=5.0)
    assert dep.phase is RolloutPhase.PENDING
    assert mgr.start(dep.deployment_id) is True
    assert dep.phase is RolloutPhase.DEPLOYING
    assert dep.current_percentage == 5.0


def test_canary_state_machine_promote():
    mgr = CanaryManager()
    dep = mgr.create_deployment("v2.0")
    mgr.start(dep.deployment_id)
    # Move from DEPLOYING -> RUNNING (indirect: advancing requires RUNNING)
    dep.phase = RolloutPhase.RUNNING
    mgr.record_metrics(
        dep.deployment_id,
        CanaryMetrics(total_requests=500, error_requests=2, latency_p99_ms=120.0),
    )
    assert mgr.can_promote(dep.deployment_id, max_error_rate=0.02, min_requests=100) is True
    assert mgr.promote(dep.deployment_id) is True
    assert dep.phase is RolloutPhase.PROMOTED
    assert dep.current_percentage == 100.0


def test_canary_promotion_blocked_by_high_error_rate():
    mgr = CanaryManager()
    dep = mgr.create_deployment("v3.0")
    mgr.start(dep.deployment_id)
    dep.phase = RolloutPhase.RUNNING
    mgr.record_metrics(
        dep.deployment_id,
        CanaryMetrics(total_requests=200, error_requests=80, latency_p99_ms=200.0),
    )
    # error_rate = 0.4 > 0.05 threshold
    assert mgr.can_promote(dep.deployment_id, max_error_rate=0.05, min_requests=50) is False


def test_canary_promotion_blocked_by_insufficient_traffic():
    mgr = CanaryManager()
    dep = mgr.create_deployment("v4.0")
    mgr.start(dep.deployment_id)
    dep.phase = RolloutPhase.RUNNING
    mgr.record_metrics(dep.deployment_id, CanaryMetrics(total_requests=10, error_requests=0))
    assert mgr.can_promote(dep.deployment_id, min_requests=100) is False


def test_rollback_zeroes_traffic():
    mgr = CanaryManager()
    dep = mgr.create_deployment("v5.0")
    mgr.start(dep.deployment_id)
    dep.phase = RolloutPhase.RUNNING
    assert mgr.rollback(dep.deployment_id) is True
    assert dep.phase is RolloutPhase.ROLLED_BACK
    assert dep.current_percentage == 0.0


def test_advance_increments_percentage_up_to_100():
    mgr = CanaryManager()
    dep = mgr.create_deployment("v6.0", step_percentage=30.0)
    mgr.start(dep.deployment_id)
    dep.phase = RolloutPhase.RUNNING
    mgr.advance(dep.deployment_id)  # 5 + 30 = 35
    mgr.advance(dep.deployment_id)  # 65
    mgr.advance(dep.deployment_id)  # 95
    mgr.advance(dep.deployment_id)  # capped at 100
    assert dep.current_percentage == 100.0


def test_blue_green_starts_at_full_traffic():
    mgr = CanaryManager()
    dep = mgr.create_deployment("v7.0", strategy=RolloutStrategy.BLUE_GREEN)
    assert dep.current_percentage == 100.0
