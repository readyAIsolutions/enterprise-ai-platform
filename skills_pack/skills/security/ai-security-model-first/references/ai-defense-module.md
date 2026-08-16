# ai_defense module — attacker-side AI defense (Enterprise platform)

Built as `modules/ai_defense/` in the Enterprise AI Platform, stdlib-only,
kernel-registered (`ai_defense` v1.0.0, priority 15). Complements
`model_security` (model-I/O guards). 37 tests; full enterprise suite 2705 passed
with zero regressions. Two git waves: `c852519` (5 facets) then `274a7cb`
(gate + harness), both pushed. Later upgraded to MASTER CLASS with a real
rate-limiter + persistent attacker state (see "Rate limiting + attacker state").

## Facets (each own file/class, stdlib-only, injectable clock for tests)

- **BehavioralAnomalyDetector** — EWMA baseline, z-score speedup + absolute flood
  floor, burst-decoupled evolving baseline.
- **BotTrafficClassifier** — automation UA/header markers + fixed robotic pacing.
- **ModelExtractionShield** — high-volume + high-uniqueness probing + cumulative
  distinct-query floor.
- **CredentialStuffingGuard** — per-account + per-IP lockout with expiry.
- **IndirectPromptInjectionGuard** — OWASP LLM01-indirect: instruction chains,
  role-override, exfil verbs.

Facade (`AIDefenseFacade`) + `AIDefenseModule` compose all five for the kernel.

## AdversaryGate (adversary_gate.py)

- Fail-closed composition: anomaly → bot → extraction → injection. If a facet is
  unhealthy/broken → BLOCK, never ALLOW.
- `GateProfile`: conservative / balanced / aggressive (declarative thresholds).
- Full decision trail (which facet fired, evidence, rule) exposed for audit.
- `AgentForceHarness`: simulates an AI attacker across flood / stuffing /
  extraction / injection; reports honest block rate + leaks.

## Live verified run (aggressive profile)

```
flood              : 100% blocked (150/150)
credential-stuffing : 24/30 accounts locked + target account locked out
model-extraction    : 99.3% blocked (149/150)
indirect-injection  : 100% poisoned blocked / 100% benign allowed
COMBINED            : 95.2% of attack events blocked, legitimate traffic flows
```

## The EWMA burst-decoupling pitfall

Naive window-mean baseline is defeated by the flood it must detect — attack events
drag the mean up and the burst stops looking anomalous. This was the one real
design battle. The working design: an EWMA baseline that evolves slowly
(decoupled from short-term spikes), a z-score that measures deviation speedup
from that slow baseline, PLUS an absolute flood floor so a sustained burst above
the floor is blocked immediately even before the EMA catches up. Don't reuse a
naive moving mean.

## Why honest harness numbers matter to LO

LO's bar is "real verification only" — never "should work". The AgentForceHarness
reports an honest block rate and any leaks. A sub-100% extraction rate (99.3%) was
reported honestly as a leak to close, not dressed up as a pass. 100% is the floor,
not the goal.

## Rate limiting + persistent attacker state (rate_limit.py) — MASTER CLASS

Added `modules/ai_defense/rate_limit.py` (stdlib-only), wired into the facade but
**OFF by default (offline)** so legacy behaviour is unchanged; opt in via
`AIDefenseFacade.with_throttle(...)` or `config["throttle"]["enabled"]`. Module
suite went 42 → 63 tests (21 new), full green.

Three components:
- **SlidingWindowRateLimiter** — per-key exact-timestamp `deque`, pruned on each
  access (continuous slide, not fixed-bucket). Thread-safe under one lock.
  `allow(key, cost, now) -> (allowed, remaining, reset_in)` (standard gateway
  triple). Also `count/reset/reset_all/snapshot`.
- **AttackerStore** — SQLite records keyed by ip/account: `first_seen, last_seen,
  attempt_count, block_until, flags` (JSON). `db_path=None` → `:memory:`, file
  path → survives process restart. `add_attempt/bump/block/blocked/is_blocked/
  block_remaining/unblock/get/list/close`. Thread-safe via `check_same_thread=
  False` + one internal lock, `row_factory=Row`.
- **ThrottleGate** — composes limiter + store. `allow(key)`: deny if `block_until`
  in future (blocked takes priority even if under the limiter) OR over limiter;
  records every decision as an attempt; **auto-blocks after a threshold** of
  attempts for `block_seconds`, then expires. Injectable `clock` on all three.

Master-class verification (do all three, not just unit tests):
1. **Persistence**: reopen a fresh AttackerStore against the same tmp SQLite file
   → `attempt_count`/`flags` intact.
2. **Thread-safety**: blast the limiter/gate from many threads (e.g. 20×50 →
   exactly `limit` allowed; gate → exactly `limit`); a race would over-allow.
3. **Clock injection**: drive window slide + block expiry deterministically.

Pitfalls hit here (avoid repeating):
- `store.list()` and `blocked()` default to real `time.time()`, but a test set
  `block_until` from an injected `Clock` (small value) → every block looked
  "expired". Pass the clock's `now` into `list(now=...)` when using a fake clock.
- When patching a method whose body is a bare `return {dict}`, rewriting it to
  build-and-return a variable (`out = {...}` then mutate `out`) requires capturing
  the opening `return {` — a patch that only matches the closing `}` fragment
  silently leaves an undefined `out`. Match the whole statement.
- Load-bearing numbers: the module suite count is now 63 within ai_defense; do
  not regress the original 42 detector/adversary-gate tests when adding layers.
