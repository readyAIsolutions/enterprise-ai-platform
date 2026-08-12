"""Tests for the Rollback Controller (plans, safety checks, execution)."""

import pytest

from modules.mlops_lifecycle.rollback_controller import (
    ActionStatus,
    PlanStatus,
    RollbackAction,
    RollbackController,
    RollbackPlan,
    SafetyCheck,
    create_rollback_controller,
)


def test_create_rollback_controller_returns_default_instance():
    ctrl = create_rollback_controller()
    assert isinstance(ctrl, RollbackController)


def test_create_and_finalize_plan():
    ctrl = RollbackController()
    plan = ctrl.create_plan(deployment_id="dep-1", reason="error spike", source="canary")
    assert isinstance(plan, RollbackPlan)
    assert plan.status is PlanStatus.DRAFT
    assert ctrl.finalize_plan(plan.plan_id) is True
    assert plan.status is PlanStatus.READY


def test_execute_plan_runs_actions_in_order():
    ctrl = RollbackController()
    plan = ctrl.create_plan("dep-2", "p1 regression")
    plan.add_safety_check(SafetyCheck(name="traffic_stopped", check=True))
    order = []
    plan.add_action(RollbackAction(action_type="disable_flag", description="disable candidate"))
    plan.add_action(RollbackAction(action_type="restore_model", description="restore stable"))

    handler = RollbackAction(action_type="notify", description="notify on-call")
    handler.handler = lambda: order.append("notify")
    plan.add_action(handler)

    assert ctrl.execute_plan(plan.plan_id) is True
    assert plan.status is PlanStatus.COMPLETE
    assert all(a.status is ActionStatus.EXECUTED for a in plan.actions)
    assert order == ["notify"]


def test_execute_plan_blocked_when_safety_check_fails():
    ctrl = RollbackController()
    plan = ctrl.create_plan("dep-3", "unsafe")
    plan.add_safety_check(SafetyCheck(name="peer_alive", check=False))
    plan.add_action(RollbackAction(action_type="disable_flag"))
    with pytest.raises(RuntimeError, match="safety"):
        ctrl.execute_plan(plan.plan_id)
    assert plan.status is PlanStatus.FAILED


def test_execute_plan_fails_if_an_action_handler_raises():
    ctrl = RollbackController()
    plan = ctrl.create_plan("dep-4", "boom")
    bad = RollbackAction(action_type="update_ledger")
    bad.handler = lambda: (_ for _ in ()).throw(RuntimeError("db down"))
    plan.add_action(bad)
    with pytest.raises(RuntimeError, match="db down"):
        ctrl.execute_plan(plan.plan_id)
    assert plan.status is PlanStatus.FAILED
    assert bad.status is ActionStatus.FAILED


def test_abort_plan_skips_pending_actions():
    ctrl = RollbackController()
    plan = ctrl.create_plan("dep-5", "abort")
    plan.add_action(RollbackAction(action_type="stop_traffic"))
    assert ctrl.abort_plan(plan.plan_id) is True
    assert plan.status is PlanStatus.ABORTED
    assert plan.actions[0].status is ActionStatus.SKIPPED


def test_plans_for_deployment_and_completed():
    ctrl = RollbackController()
    p1 = ctrl.create_plan("dep-6", "a")
    ctrl.create_plan("dep-7", "b")
    assert len(ctrl.plans_for_deployment("dep-6")) == 1
    p1.add_safety_check(SafetyCheck(name="ok", check=True))
    ctrl.execute_plan(p1.plan_id)
    assert len(ctrl.completed_plans()) == 1
