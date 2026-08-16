# SQLite-backed durable task scheduler + message bus (Temporal-style)

Reusable design for adding a *durable execution* layer to an ENI Enterprise module
with only the stdlib (sqlite3 + time). Built and proven green in the
`agent_coordination` module upgrade. Master-class = durable, leases, retries,
no stubs.

## The Temporal pattern to rip
- Work is persisted (write-ahead) BEFORE it is handed to a worker.
- The **lease**, not the worker process, is the liveness signal. A worker owns a
  unit of work only for `lease_seconds`; it must keep it alive with `heartbeat`.
  Expired leases are reclaimed so a crashed worker's work is retried by a live one.
- Failure is expressed as **bounded retry** (return to pending, increment a budget
  counter) then terminal **dead-letter**, never silent data loss.
- Everything is restart-safe: reopening the same `db_path` reloads every pending /
  in-flight / dead-lettered unit.

## SQLite schema essentials
- `tasks` table with a partial unique index on `dedupe_key` (`WHERE dedupe_key IS
  NOT NULL`) so NULL dedupe keys don't collide. Idempotent `schedule`: on INSERT
  IntegrityError with a dedupe_key, SELECT the existing row and return its id.
- claim ordering: `WHERE status='pending' AND eta<=now ORDER BY priority DESC,
  eta ASC, rowid ASC LIMIT 1` inside a transaction so two workers can't grab the
  same task. `recover_expired_leases()` resets `claimed` rows with
  `lease_until <= now` to `pending`; call it at the top of `claim_next`.
- Lease ownership: `complete/retry/fail/heartbeat` take an optional `worker_id`
  and raise a `LeaseError` when it doesn't match `row['worker_id']` (worker_id
  may be NULL for unclaimed transitions — allow None).
- retry semantics: increment `retry_count`; if `retry_count > max_retries` ->
  `failed`, else back to `pending` (optionally at a future `eta` for backoff).
  A `fail()` convenience that respects the retry budget first is a nice escape
  hatch.

## Injectable clock (deterministic tests)
Accept a zero-arg callable OR an object with a `now()` method. Order of checks in
the normalizer matters — check `hasattr(clock,'now') and callable(...)` FIRST,
then plain `callable(clock)`. A FakeClock with only `.now()` and `.tick()` is NOT
callable, so checking `callable(clock)` first raises TypeError on it. Default to a
thin `_RealClock` wrapping `time.time`. Always compute `now` once per operation.

## db_path config (tests vs prod)
- `db_path=None`  -> `':memory:'` (tests)
- a directory      -> `<dir>/tasks.sqlite`
- a `.db/.sqlite` file -> that exact file
This is what lets the same test code exercise persistence round-trips with a
`tmp_path` file AND fast in-memory unit tests.

## Wiring into the module
- New file, e.g. `durable_scheduler.py`, exports its own `__all__`.
- Re-export from the module `__init__.py` (imports + `__all__`) so it becomes
  public API. Additive only — never touch existing exports.
- Keep the existing `scheduler.py` / `fault_tolerance.py` names untouched; the new
  file complements, it does not replace.

## Pitfalls hit (all resolved)
- FakeClock that only has `.now()` is not `callable()` -> must duck-type now()
  before the callable check (see injectable clock above).
- Pyright optional-member-access on a `row` that is `None` at some call site:
  make the row->record converter take a non-optional row and guard `None` at the
  call sites instead.
- Test-logic bugs vs implementation bugs: an "unclaimed complete" error and a
  deadline test that expired BOTH items were test bugs, not code bugs. When a
  green-intent test fails, double-check the test's own arithmetic (number of
  items enqueued, tick distance past deadline) before touching the impl.

## SchedulerBus (scheduling + resilient dispatch)
Combine the scheduler with a handler registry:
`publish(topic,payload)` schedules a message task; `register_handler(topic,fn)`;
`process(worker_id,lease)` claims -> runs handler -> complete on success, on
exception bounded-retry then insert into a durable `dead_letters` table. Mark a
message as a dict `{"__topic__":..., "__message__":...}`. Unregistered topics are
consumed (completed) without retry. `publish` supports `dedupe_key` for
at-least-once without duplicate spam.

## Test coverage target (12-20 green)
schedule+claim lease; lease expiry/ownership; retry increments + max_retries
exhaustion; dedupe idempotency; priority ordering + ETA tiebreak; deadline;
cancel; stats by status; queue enqueue/dequeue/peek; persistence round-trip;
restart reload + lease recovery. Run the whole module suite after (not just the
new file) to prove no existing test broke.
