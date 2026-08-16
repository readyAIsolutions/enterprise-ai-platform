# Runtime Feature-Flag / Canary / A-B Engine (master-class pattern)

When LO asks to "MASTER CLASS" a release/change module (`modules/release_change/`),
the ask is almost always: the existing `strategies.py` canary/blue-green/staged
rollout classes are **descriptive** — they log `"..._configured"`, split traffic
only on paper, and return result dicts. They do NOT decide anything at request
time. The upgrade is to add a REAL runtime decision engine. This reference captures
the exact pattern that worked (verified 158 green tests, 2026-08-04).

## Structure: one new file `flags.py`, wired into `__init__.py`
Do NOT touch the existing strategy/quality-gate/workflow files — they pass and
their API is preserved. Add `modules/release_change/flags.py` (stdlib only:
`hashlib, dataclasses, enum, threading, time, logging`) and export its symbols from
`__init__.py` (`from .flags import ...` + append to `__all__`). Keep every existing
export in place.

## The five pieces that make it "master class"
1. **`FeatureFlag`** dataclass: `name, enabled, rollout_percent, variants{name:weight},
   default_variant, targeting_rules, seed`. `apply_to(context)` = all targeting
   rules match. `variant_for(context)` = deterministic weighted pick.
2. **`FlagEngine`**: `register_flag / unregister_flag / get_flag / is_enabled /
   get_variant / enable / disable / set_rollout`. Guard shared dict with an RLock.
   Every decision is appended to an audit log.
3. **`Canary`**: state machine (`NOT_STARTED / SENDING / PROMOTING / FULL /
   ROLLED_BACK / BLOCKED`) with `initial_percent / increment_step / target_percent /
   current_percent`, plus `send_traffic() / promote() / rollback()`. `promote()` is
   gated by an **injectable** `health_check: Callable[[], bool]` — a failing check
   sets state to BLOCKED and does NOT bump traffic. `rollback()` drops to 0 and
   raises on re-send. Absent health_check => treated healthy (allows promotion).
4. **`ReleaseGate`**: `evaluate(engine, flag_name, canary, context)` returns
   `{decision: PASS|BLOCKED, go: bool, checks: [{check, ok, reason}...]}`. A change
   only goes when: flag EXISTS, flag ENABLED, `flag.rollout_percent <=
   max_rollout_percent` (policy), and canary healthy. Any single fail => BLOCKED.
5. **`AuditLog`**: append-only, thread-safe, capacity-capped list; every
   register/enable/disable/set_rollout/evaluate/variant/canary-transition/gate
   decision recorded. `find(action=, name=)` for querying. Snapshot via
   `.entries` returns a copy so tests can assert immutability.

## Deterministic hash-bucket (the core "real engine" trick)
```python
_BUCKET_MOD = 10_000  # 0.01% granularity
def hash_bucket(*parts):
    raw = ":".join(str(p) for p in parts)
    return int(hashlib.sha256(raw.encode()).hexdigest(), 16) % _BUCKET_MOD

def _rollout_hit(percent, seed, name, context_key):
    bucket = hash_bucket(seed, "rollout", name, context_key)
    return bucket < int(round(percent * (_BUCKET_MOD / 100.0)))
```
- Same `(seed, flag_name, context_key)` ALWAYS maps to the same bucket => stable
  A/B assignment across calls and processes (no `random`, fully reproducible).
- Weighted variant: `bucket % total_weight`, walk cumulative weights, first to
  cross returns that variant.
- `context_key` derives from a stable context field: `id` → `user_id` → `tenant` →
  sorted-fingerprint fallback. This is what makes "the same user gets the same
  treatment" true.

## Test strategy (test_flags.py, `unittest` style to match test_release.py)
Aim for ~30 test methods (35 used) covering every mandated case:
- flag enable/disable (+ unknown flag => False; enable/disable unknown => False)
- rollout determinism: same input same result; 0% blocks all, 100% serves all;
  ~50% over N=2000 within delta=0.05
- weighted variants: 90/10 over 2000 samples within delta=0.05; stable per context;
  boolean flag (no variants) => None; default_variant when not rolled out
- targeting rules (IN region gate; EQUALS / GREATER_THAN)
- canary: send_traffic starts at initial; promote increments when healthy; BLOCKED
  + unchanged when unhealthy; no-health-check promotes; rollback to 0; re-send after
  rollback raises RuntimeError; health-check exception => unhealthy
- release gate: PASS all-ok; BLOCK missing flag / disabled / rollout-exceeds-policy /
  unhealthy canary
- audit log + full lifecycle (register → rollout → variant → gate pass → promote
  to FULL → set_rollout 100 → everyone served)

## Pitfalls hit (fix BEFORE they cost you time)
- **Blocked-canary snapshot lacked a `decision` key** → consumers KeyError. When a
  health check fails, explicitly add `result["decision"] = False` to the snapshot so
  the return shape is consistent between success and blocked paths.
- **Canary test expected 100 after one promote but got 95** → `send_traffic()`
  resets `current_percent` to `initial_percent` (default 5.0), so if you seeded
  `current_percent=10` you must ALSO set `initial_percent=10` for the arithmetic to
  hold. This is a test-setup bug, not an engine bug.
- Pyright flags `flag.rollout_percent` as "not a known attribute of None" in the
  gate — it's a false positive because `flag is not None` was checked earlier.
- The repo's files read back ENI-compressed (head/tail truncated) on paid models —
  read in small chunks (offset/limit ~60-80) or grep signatures. See
  `eni-omega-compress-paid` / references/read-side-compression.md.

## Verification
`cd ~/Desktop/Enterprise Builder/enterprise && python3 -m pytest modules/release_change -q -p no:cacheprovider`
Green = existing suite + new flags suite all pass (was 123 baseline, ended 158).
