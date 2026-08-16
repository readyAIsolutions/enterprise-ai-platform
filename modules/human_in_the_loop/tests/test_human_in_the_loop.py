"""Unit tests for the human_in_the_loop module (network-free)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from enterprise.modules.human_in_the_loop import (
    ApprovalPolicy,
    Action,
    Escalation,
    EscalationQueue,
    HumanInTheLoop,
    make_human_in_the_loop,
    create_human_in_the_loop_module,
)

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def now():
    return NOW


# ------------------------------------------------------------- approval policy
def test_policy_auto_proceeds_on_high_confidence_low_stakes():
    policy = ApprovalPolicy()
    act = Action(action_id="a1", description="rename file", confidence=0.95,
                 stakes="low", at=NOW)
    d = policy.evaluate(act)
    assert d["verdict"] == "auto"
    assert d["approvers_needed"] == 0


def test_policy_escalates_on_low_confidence():
    policy = ApprovalPolicy(review_confidence=0.62)
    act = Action(action_id="a2", description="draft contract clause",
                 confidence=0.40, stakes="medium", at=NOW)
    d = policy.evaluate(act)
    assert d["verdict"] == "escalate"
    assert d["approvers_needed"] == policy.max_reviewers


def test_policy_requires_signoff_for_high_stakes_moderate_confidence():
    policy = ApprovalPolicy(high_stake_review_threshold=0.90)
    act = Action(action_id="a3", description="delete production database",
                 confidence=0.70, stakes="high", at=NOW)
    d = policy.evaluate(act)
    assert d["verdict"] == "review"
    assert d["approvers_needed"] == 1


def test_policy_rejects_out_of_range_confidence():
    with pytest.raises(ValueError):
        Action(action_id="bad", description="x", confidence=1.5, stakes="low",
               at=NOW)


# ------------------------------------------------------- confidence-based routing
def test_routing_auto_when_confident():
    h = make_human_in_the_loop()
    out = h.route(Action(action_id="r1", description="summarize doc",
                         confidence=0.95, stakes="low", at=NOW))
    assert out["verdict"] == "auto"
    assert out["escalation_id"] is None
    assert h.queue_stats()["human_in_loop"] == 0


def test_routing_escalates_when_uncertain():
    h = make_human_in_the_loop()
    out = h.route(Action(action_id="r2", description="approve invoice",
                         confidence=0.30, stakes="medium", at=NOW))
    assert out["verdict"] == "escalate"
    assert out["escalation_id"] is not None
    assert len(h.pending()) == 1


@pytest.mark.asyncio
async def test_module_initialize_and_route(tmp_path: Path):
    m = create_human_in_the_loop_module({"auto_confidence": 0.80})
    await m.initialize()
    assert m.engine is not None
    hs = await m.health_check()
    assert "HEALTHY" in str(hs) or hs.value in ("healthy", "HEALTHY")

    # low confidence -> escalates to a human
    out = m.route_action("r3", "send email to client", confidence=0.50,
                         stakes="high")
    assert out["verdict"] == "escalate"
    pending = m.pending_escalations()
    assert len(pending) == 1
    assert pending[0]["action_id"] == "r3"

    # high confidence low stakes -> auto
    out2 = m.route_action("r4", "log metrics", confidence=0.99, stakes="low")
    assert out2["verdict"] == "auto"

    # resolve the escalation with a human sign-off
    result = m.resolve_action(pending[0]["id"], approver="bryson",
                              approved=True, note="looks correct")
    assert result["status"] == "approved"
    assert m.queue_stats()["queue"]["approved"] == 1
    # every routing was recorded in the audit log
    assert len(m.audit_log()) >= 3

    await m.shutdown()
    assert m.engine is None


# ---------------------------------------------------------------- queue ordering
def test_queue_orders_by_priority_then_deadline():
    q = EscalationQueue()
    now = NOW
    hi = q.add(Action(action_id="h", description="high", confidence=0.2,
                      stakes="high", at=now),
               reason="high stakes low conf", priority=310, deadline=now)
    lo = q.add(Action(action_id="l", description="low", confidence=0.5,
                      stakes="low", at=now),
               reason="low stakes", priority=55, deadline=now + timedelta(hours=3))
    med = q.add(Action(action_id="m", description="med", confidence=0.3,
                       stakes="medium", at=now),
                reason="medium", priority=170, deadline=now + timedelta(hours=1))
    ordered = q.ordered()
    assert [e.id for e in ordered] == [hi.id, med.id, lo.id]
    assert q.next().id == hi.id


def test_queue_deadline_tiebreak_and_expiry():
    q = EscalationQueue()
    now = NOW
    a = q.add(Action(action_id="a", description="a", confidence=0.1,
                     stakes="high", at=now),
              reason="x", priority=300, deadline=now + timedelta(hours=4))
    b = q.add(Action(action_id="b", description="b", confidence=0.1,
                     stakes="high", at=now),
              reason="x", priority=300, deadline=now + timedelta(hours=1))
    # same priority -> sooner deadline first
    assert q.ordered()[0].id == b.id

    # expire overdue item
    overdue = q.add(Action(action_id="o", description="old", confidence=0.1,
                           stakes="low", at=now),
                    reason="old", priority=1, deadline=now - timedelta(hours=1))
    n = q.expire_overdue(now=now)
    assert n == 1
    assert overdue.status == "expired"
    assert q.pending_count() == 2


def test_audit_log_records_all_verdicts():
    h = make_human_in_the_loop()
    h.route(Action(action_id="a", description="auto", confidence=0.98,
                   stakes="low", at=NOW))
    res = h.route(Action(action_id="b", description="esc", confidence=0.3,
                         stakes="high", at=NOW))
    h.resolve(res["escalation_id"], approver="carla", approved=True,
              note="ok")
    log = h.audit_log()
    verdicts = {e["verdict"] for e in log}
    assert {"auto", "escalate", "approved"} <= verdicts
    assert log[-1]["approver"] == "carla"
    assert log[-1]["approved"] is True


def test_priority_rises_with_stakes_and_uncertainty():
    from enterprise.modules.human_in_the_loop.human_in_the_loop import (
        _priority_for,
    )
    assert _priority_for(confidence=0.2, stakes="high") > \
        _priority_for(confidence=0.5, stakes="low")


def test_asyncio_run_shutdown_idempotent():
    async def run():
        m = make_human_in_the_loop()
        return m
    m = asyncio.run(run())
    assert m.queue_stats()["total_actions_routed"] == 0
