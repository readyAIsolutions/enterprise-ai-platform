"""Tests for the durable task scheduler + message bus (MASTER CLASS).

Covers: schedule+claim lease, expired-lease reclaim, bounded retry,
dedupe idempotency, priority ordering, deadlines, stats, persistence
round-trip and restart reload. Uses an injectable fake clock and in-memory
or temp-file SQLite for determinism and durability checks.
"""

from __future__ import annotations

from typing import Never

import pytest
from enterprise.modules.agent_coordination.durable_scheduler import (
    DurableScheduler,
    LeaseError,
    SchedulerBus,
    SchedulerError,
    TaskNotFoundError,
    TaskQueue,
    TaskStatus,
)

# ---------------------------------------------------------------------------
# Fake clock
# ---------------------------------------------------------------------------


class FakeClock:
    """Deterministic injectable clock (now() -> TICK)."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self._t = start

    def tick(self, delta: float = 1.0) -> float:
        self._t += delta
        return self._t

    def set(self, value: float) -> None:
        self._t = value

    def now(self) -> float:
        return self._t


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def sched(clock):
    s = DurableScheduler(db_path=None, clock=clock)
    yield s
    s.close()


# ---------------------------------------------------------------------------
# schedule + claim lease
# ---------------------------------------------------------------------------


def test_schedule_and_claim_lease(clock, sched) -> None:
    sched.schedule("t1", {"op": "sum", "args": [1, 2]}, max_retries=2)
    claimed = sched.claim_next("worker-1", lease_seconds=30)
    assert claimed is not None
    assert claimed.task_id == "t1"
    assert claimed.status == TaskStatus.CLAIMED.value
    assert claimed.worker_id == "worker-1"
    assert claimed.lease_until == clock.now() + 30
    assert claimed.payload == {"op": "sum", "args": [1, 2]}


def test_claim_respects_eta(clock, sched) -> None:
    sched.schedule("future", "work", eta=clock.now() + 100)
    # ETA not yet reached -> nothing to claim.
    assert sched.claim_next("w1") is None
    clock.tick(101)
    assert sched.claim_next("w1") is not None


def test_claim_is_exclusive_until_lease_expires(clock, sched) -> None:
    sched.schedule("t1", "work")
    first = sched.claim_next("worker-a", lease_seconds=30)
    assert first is not None
    # A second worker cannot claim the same leased task.
    assert sched.claim_next("worker-b", lease_seconds=30) is None
    # The claiming worker sees it in-flight.
    st = sched.stats()
    assert st[TaskStatus.CLAIMED.value] == 1
    assert st[TaskStatus.PENDING.value] == 0


# ---------------------------------------------------------------------------
# expired lease reclaimed
# ---------------------------------------------------------------------------


def test_expired_lease_reclaimed(clock, sched) -> None:
    sched.schedule("t1", "work", max_retries=5)
    sched.claim_next("worker-a", lease_seconds=10)
    # Lease expires after 10s.
    clock.tick(11)
    recovered = sched.recover_expired_leases()
    assert recovered == 1
    # Now another worker can pick it up.
    claimed = sched.claim_next("worker-b", lease_seconds=10)
    assert claimed is not None
    assert claimed.task_id == "t1"
    assert claimed.worker_id == "worker-b"


def test_claim_next_auto_reclaims_expired(clock, sched) -> None:
    sched.schedule("t1", "work")
    sched.claim_next("worker-a", lease_seconds=10)
    clock.tick(11)
    # claim_next internally reclaims the stale lease.
    claimed = sched.claim_next("worker-b", lease_seconds=10)
    assert claimed is not None
    assert claimed.worker_id == "worker-b"


def test_active_lease_not_reclaimed(clock, sched) -> None:
    sched.schedule("t1", "work")
    sched.claim_next("worker-a", lease_seconds=60)
    clock.tick(10)  # still within lease
    assert sched.recover_expired_leases() == 0
    assert sched.claim_next("worker-b", lease_seconds=60) is None


# ---------------------------------------------------------------------------
# retry increments and max_retries
# ---------------------------------------------------------------------------


def test_retry_increments_and_stays_pending(clock, sched) -> None:
    sched.schedule("t1", "work", max_retries=3)
    sched.claim_next("w1")
    outcome = sched.retry("t1", "w1", error="boom")
    assert outcome == TaskStatus.PENDING.value
    task = sched.get_task("t1")
    assert task.retry_count == 1
    assert task.last_error == "boom"
    assert task.worker_id is None  # released back to pool


def test_retry_exhausts_to_failed(clock, sched) -> None:
    sched.schedule("t1", "work", max_retries=2)
    for _ in range(3):  # attempt + 2 retries -> exhaust on 3rd
        claimed = sched.claim_next("w1")
        assert claimed is not None
        if claimed.retry_count >= 2:
            outcome = sched.retry("t1", "w1", error="give up")
            assert outcome == TaskStatus.FAILED.value
        else:
            sched.retry("t1", "w1", error="nope")
    task = sched.get_task("t1")
    assert task.status == TaskStatus.FAILED.value
    assert task.retry_count == 3
    assert sched.claim_next("w1") is None  # no longer schedulable


def test_fail_respects_retry_budget(clock, sched) -> None:
    sched.schedule("t1", "work", max_retries=1)
    sched.claim_next("w1")
    # Still has budget -> fail() retries instead of terminal-failing.
    assert sched.fail("t1", "w1", error="x") == TaskStatus.PENDING.value
    assert sched.get_task("t1").retry_count == 1


# ---------------------------------------------------------------------------
# lease ownership enforcement
# ---------------------------------------------------------------------------


def test_lease_ownership_enforced_on_heartbeat(clock, sched) -> None:
    sched.schedule("t1", "work")
    sched.claim_next("worker-a")
    with pytest.raises(LeaseError):
        sched.heartbeat("t1", "intruder", 10)


def test_lease_ownership_enforced_on_complete(clock, sched) -> None:
    sched.schedule("t1", "work")
    sched.claim_next("worker-a")
    with pytest.raises(LeaseError):
        sched.complete("t1", "intruder")


def test_heartbeat_extends_lease(clock, sched) -> None:
    sched.schedule("t1", "work")
    sched.claim_next("worker-a", lease_seconds=10)
    clock.tick(5)
    assert sched.heartbeat("t1", "worker-a", 10) is True
    assert sched.get_task("t1").lease_until == clock.now() + 10


# ---------------------------------------------------------------------------
# dedupe
# ---------------------------------------------------------------------------


def test_dedupe_key_is_idempotent(clock, sched) -> None:
    first = sched.schedule("t1", "work", dedupe_key="unique-key")
    second = sched.schedule("t2", "work", dedupe_key="unique-key")
    assert first == "t1"
    assert second == "t1"  # deduped back to the original task_id
    assert sched.stats()[TaskStatus.PENDING.value] == 1


def test_no_dedupe_when_key_absent(clock, sched) -> None:
    sched.schedule("t1", "work")
    sched.schedule("t2", "work")
    assert sched.stats()[TaskStatus.PENDING.value] == 2


# ---------------------------------------------------------------------------
# priority ordering
# ---------------------------------------------------------------------------


def test_priority_order(clock, sched) -> None:
    sched.schedule("low", "work", priority=1)
    sched.schedule("high", "work", priority=10)
    sched.schedule("mid", "work", priority=5)
    order = []
    for _ in range(3):
        order.append(sched.claim_next("w").task_id)
    assert order == ["high", "mid", "low"]


def test_eta_tiebreak_within_priority(clock, sched) -> None:
    sched.schedule("b", "work", priority=1, eta=clock.now() + 5)
    sched.schedule("a", "work", priority=1, eta=clock.now())
    clock.tick(6)
    first = sched.claim_next("w")
    assert first.task_id == "a"


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------


def test_cancel_pending_task(clock, sched) -> None:
    sched.schedule("t1", "work")
    assert sched.cancel("t1") is True
    assert sched.get_task("t1").status == TaskStatus.CANCELLED.value
    assert sched.claim_next("w") is None


def test_cancel_only_pending(clock, sched) -> None:
    sched.schedule("t1", "work")
    sched.claim_next("w")
    assert sched.cancel("t1") is False  # claimed, not pending


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_stats_counts_by_status(clock, sched) -> None:
    sched.schedule("t1", "work", max_retries=1)
    sched.schedule("t2", "work")
    sched.claim_next("w")  # claims highest priority; ties -> t1 first
    t2 = sched.claim_next("w")
    assert t2 is not None
    assert t2.task_id == "t2"
    sched.complete("t2", "w")
    st = sched.stats()
    assert st[TaskStatus.PENDING.value] == 0
    assert st[TaskStatus.CLAIMED.value] == 1
    assert st[TaskStatus.COMPLETED.value] == 1


# ---------------------------------------------------------------------------
# TaskQueue
# ---------------------------------------------------------------------------


def test_task_queue_enqueue_dequeue_peek(clock) -> None:
    q = TaskQueue(db_path=None, clock=clock)
    q.enqueue("a", "A", priority=1)
    q.enqueue("b", "B", priority=10)
    assert q.peek() == ("b", "B")  # highest priority first
    assert q.dequeue("w") == ("b", "B")
    assert q.dequeue("w") == ("a", "A")
    assert q.dequeue("w") is None
    q.close()


def test_task_queue_deadline(clock) -> None:
    q = TaskQueue(db_path=None, clock=clock)
    q.enqueue("due", "work", deadline=clock.now() + 100)
    q.enqueue("late", "work", deadline=clock.now())
    clock.tick(6)
    assert q.peek() == ("due", "work")  # 'late' past deadline excluded
    assert q.expire_overdue() == 1
    assert q.stats()["timed_out"] == 1
    q.close()


def test_task_queue_stats(clock) -> None:
    q = TaskQueue(db_path=None, clock=clock)
    q.enqueue("a", "A")
    q.enqueue("b", "B")
    q.enqueue("c", "C")
    q.dequeue("w")  # leases 'a'
    q.ack("a", "w")  # 'a' completed
    q.dequeue("w")  # leases 'b' -> remains leased
    st = q.stats()
    assert st["pending"] == 1
    assert st["leased"] == 1
    assert st["completed"] == 1
    q.close()


def test_task_queue_duplicate_id_rejected(clock) -> None:
    q = TaskQueue(db_path=None, clock=clock)
    q.enqueue("a", "A")
    with pytest.raises(SchedulerError):
        q.enqueue("a", "A")
    q.close()


# ---------------------------------------------------------------------------
# SchedulerBus
# ---------------------------------------------------------------------------


def test_bus_dispatch_success(clock, sched) -> None:
    bus = SchedulerBus(db_path=None, clock=clock, scheduler=sched)
    seen = []
    bus.register_handler("sum", lambda msg: seen.append(msg))
    bus.publish("sum", {"a": 1, "b": 2})
    processed = bus.process("w", lease_seconds=30)
    assert processed == 1
    assert seen == [{"a": 1, "b": 2}]
    assert len(bus.dead_letters()) == 0
    bus.close()


def test_bus_retries_then_dead_letters(clock, sched) -> None:
    bus = SchedulerBus(db_path=None, clock=clock, scheduler=sched)
    calls = {"n": 0}

    def flaky(msg) -> Never:
        calls["n"] += 1
        msg_0 = "transient"
        raise RuntimeError(msg_0)

    bus.register_handler("flaky", flaky)
    bus.publish("flaky", "x", max_retries=2)
    bus.process("w", lease_seconds=30)
    # max_retries=2 -> attempts: 1 success-less run + 2 retries = 3 total calls,
    # then dead-lettered.
    assert calls["n"] == 3
    assert sched.get_task.__self__.stats()[TaskStatus.FAILED.value] == 1
    letters = bus.dead_letters()
    assert len(letters) == 1
    assert letters[0]["topic"] == "flaky"
    assert letters[0]["attempts"] == 3
    bus.close()


def test_bus_publish_dedupe(clock, sched) -> None:
    bus = SchedulerBus(db_path=None, clock=clock, scheduler=sched)
    bus.publish("t", "x", dedupe_key="dk")
    bus.publish("t", "x", dedupe_key="dk")
    assert sched.stats()[TaskStatus.PENDING.value] == 1
    bus.close()


def test_bus_unregistered_topic_completed(clock, sched) -> None:
    bus = SchedulerBus(db_path=None, clock=clock, scheduler=sched)
    bus.publish("ghost", "x")
    assert bus.process("w", lease_seconds=30) == 1
    # No handler -> treated as consumed (no retries, no dead letter).
    assert len(bus.dead_letters()) == 0
    bus.close()


# ---------------------------------------------------------------------------
# persistence round-trip + restart reload
# ---------------------------------------------------------------------------


def test_persistence_round_trip(tmp_path, clock) -> None:
    db = tmp_path / "tasks.sqlite"
    s1 = DurableScheduler(db_path=db, clock=clock)
    s1.schedule("t1", {"k": "v"}, max_retries=3)
    s1.schedule("t2", "other")
    s1.claim_next("w1", lease_seconds=30)
    s1.close()

    # Reopen from disk in a fresh instance -> data survives.
    s2 = DurableScheduler(db_path=db, clock=clock)
    assert s2.get_task("t1").payload == {"k": "v"}
    st = s2.stats()
    assert st[TaskStatus.CLAIMED.value] == 1
    assert st[TaskStatus.PENDING.value] == 1
    s2.close()


def test_restart_reload_and_recovery(tmp_path, clock) -> None:
    db = tmp_path / "tasks.sqlite"
    s1 = DurableScheduler(db_path=db, clock=clock)
    s1.schedule("crash", "work", max_retries=5)
    s1.claim_next("dead-worker", lease_seconds=10)
    s1.close()  # simulate crash: no complete/retry

    # Restart; the old worker's lease is long gone.
    clock.tick(100)
    s2 = DurableScheduler(db_path=db, clock=clock)
    # Task survived restart and is still claimed (in-flight) until reclaimed.
    assert s2.get_task("crash").status == TaskStatus.CLAIMED.value
    # Recovery path reclaims it for a live worker.
    assert s2.recover_expired_leases() == 1
    reclaimed = s2.claim_next("fresh-worker", lease_seconds=30)
    assert reclaimed is not None
    assert reclaimed.task_id == "crash"
    assert reclaimed.worker_id == "fresh-worker"
    s2.close()


def test_bus_survives_restart(tmp_path, clock) -> None:
    db = tmp_path / "tasks.sqlite"
    bus1 = SchedulerBus(db_path=db, clock=clock)
    bus1.publish("job", {"step": 1}, dedupe_key="restart-key")
    bus1.close()

    # A new bus on the same db still sees the message.
    bus2 = SchedulerBus(db_path=db, clock=clock)
    seen = []
    bus2.register_handler("job", seen.append)
    assert bus2.process("w", lease_seconds=30) == 1
    assert seen == [{"step": 1}]
    bus2.close()


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


def test_unknown_task_raises(clock, sched) -> None:
    with pytest.raises(TaskNotFoundError):
        sched.heartbeat("missing", "w", 10)


def test_duplicate_task_id_rejected(clock, sched) -> None:
    sched.schedule("t1", "work")
    with pytest.raises(SchedulerError):
        sched.schedule("t1", "work")
