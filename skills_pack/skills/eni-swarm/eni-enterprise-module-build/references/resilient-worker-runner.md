# Resilient worker runner (retry / deadline / heartbeat) + deterministic testing

Session: upgraded `modules/task_harness/` with a master-class execution layer on
top of the existing SQLite task-card store. `runner.py` added a resilient
WorkerRunner; `tests/test_runner.py` added 18 deterministic tests. Whole module
47 green (29 original + 18 new), no regressions, no real work ever executed.
The umbrella's module-build workflow + ENI-file-read gotcha (see
integrity-ledger-and-eni-file-read.md) carried over unchanged.

## The resilient-runner pattern (reusable class, not task_harness-specific)

When you need to execute queued work with robustness, split responsibility into
small single-purpose, fully-injectable components:

- **RetryPolicy** — `max_attempts` + backoff. Backoff accepts a float (then
  exponential `2^(attempt-1)`) OR a callable `(attempt) -> seconds`. Provide
  `exhausted(attempt)` so the loop has a single source of truth for "give up".
- **Deathline → Deadline** — enforce a max wall-clock runtime per task. Store the
  start time at claim; `is_expired` compares against the injected clock. Check
  it at the TOP of every attempt so long-running/progressing tasks still expire.
- **Heartbeat** — per-task liveness: `start/beat/last_beat/is_stalled` + a
  `watchdog(task_ids)` that reaps the subset that has gone silent past `timeout`.
  A task that has NEVER beaten is conservatively stalled.
- **ErrorClassifier** — split errors into RETRYABLE (network/timeout/OSError —
  transient, worth retrying) vs PERMANENT (ValueError/TypeError/KeyError/bad
  input — logic bugs, retry is pointless/dangerous). CRITICAL default: unknown
  exceptions classify as PERMANENT. Never spin forever on an unexpected error.
- **RunningStatus** — outcome enum (running / running_retry / running_permanent
  / expired) so the loop and its callers share a vocabulary.
- **WorkerRunner** — the loop. `claim()` pulls from the store's runnable
  ordering (respects deps+priority, so reuse that — don't reimplement ordering).
  `run_task(id)` drives ONE task through the attempt loop; `run_once()` =
  claim+run_task; `run()` = drain loop with optional `max_iterations` cap.

### Per-attempt order (the crux — see pitfall below)

For each attempt, in THIS order:
1. Deadline check (still within runtime?) — else mark EXPIRED + fail.
2. **Stall check** (was the PREVIOUS cycle silent past heartbeat timeout?) — if
   so, it's a retryable condition: push backoff, restore liveness, continue.
3. Emit heartbeat (liveness for the CURRENT unit of work).
4. Execute the injected task function; on success complete, on retryable error
   sleep(backoff) + retry, on permanent error fail.

## Pitfall: stall-check MUST run BEFORE the heartbeat emit — else it's dead code

First implementation emitted the heartbeat, THEN checked `is_stalled`. Because
the emit just refreshed the timestamp, `is_stalled` was always False and the
stall-retry path was unreachable (caught by tests only after thinking it was
correct). Fix: evaluate liveness from the PREVIOUS cycle before refreshing for
the current one. Step order above is the durable lesson — heartbeat-emit is the
START of a unit of work, so the stall question must be answered about the
freshest PAST timestamp, not the one you are about to write.

## Deterministic testing without ever running real work

The whole point of injectable clock/sleep/executor is that tests control time
and behavior exactly — no wall-clock sleeps, no real I/O, no sleeps/network.

- **FakeClock** — callable object with `__call__()` returning current time and
  `advance(seconds)`. Injected wherever a `clock` is expected.
- **RecordingSleep** — callable that appends requested delays to a list instead
  of sleeping. Assert exact backoff sequences (e.g. `[1.0, 2.0]`) to prove the
  retry schedule, not just that "some retry happened".
- **Injected executor** — pass a closure mapping task → behaviour per call count
  (e.g. fail first N calls with ConnectionError, then return "ok"). Track call
  counts to assert exact attempt numbers (permanent error ⇒ exactly 1 call,
  no backoff sleep at all).
- **Driver pattern for timing-sensitive cases**: `runner.claim()` (records the
  start/heartbeat timestamp), THEN `clock.advance(...)` past a timeout/deadline,
  THEN `run_task(id)` — this simulates "worker went quiet mid-task" without a
  real hang.

## Other concrete choices that worked

- Default executor raises `PermanentError("no executor configured")` — fail
  fast, never silent no-op.
- Aggregate `RunnerStats` (claimed/completed/failed/expired/retried/stalled/
  stalled_failed/attempts) + `snapshot()`; the loop returns it, `run_once`
  returns the outcome or None when idle.
- `build_runner(harness, *, executor, max_attempts, backoff, max_runtime,
  heartbeat_timeout, clock, sleep)` convenience factory wires retry+deadline+
  heartbeat from flat args. NOTE: it builds its own RetryPolicy from
  max_attempts/backoff, so it does NOT take a RetryPolicy directly — if a test
  needs a custom policy, construct WorkerRunner directly.
- Preserve the module contract: extend `__all__` in `__init__.py` with the new
  exports; keep all old exports and the original tests untouched.
- Health check: import via a script that verifies the @module factory still
  subclasses `enterprise.platform_kernel.Module` and that the new imports land.
