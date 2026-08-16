# Master-class Member Heartbeat + Liveness Registry (programmatic layer)

Companion to the telemetry HEARTBEAT monitor. Where the telemetry skill reads
*external* truth (wmctrl windows, procs, STATUS mtimes), this is the *in-code*
liveness layer for an enterprise module — a self-contained, stdlib-only
registry/protocol/aggregator that tracks member liveness on an injectable clock.
Built for `modules/swarm_bridge/heartbeat.py` (91 tests green: 64 legacy + 27 new).

## Core design (all stdlib, no stubs — real clock-driven liveness)

- **`SwarmMember`** dataclass: `member_id, role, addr, capabilities[], status,
  last_heartbeat, registered_at`. `status` ∈ {alive, absent, lost}; `mark_alive()`,
  `is_alive()`, dict serialization round-trip (`to_dict`/`from_dict`).
- **`MemberRegistry`**: in-memory dict + RLock, OPTIONAL SQLite persistence
  (`db_path`). `register` = upsert + stamps initial heartbeat/registered_at so a new
  member starts alive; `unregister`, `get`, `contains`, `__len__`,
  `list(role=, status=)` with stable ordering, `load_persisted()`. Persistence is a
  clean no-op when no db_path (optional by design). Every mutation mirrored to SQLite
  via INSERT OR REPLACE / DELETE.
- **`HeartbeatProtocol`**: `send_heartbeat(member_id)` stamps last_heartbeat + marks
  alive (KeyError on unknown member — surface misconfig, don't swallow). `mark_alive()`.
  `check_liveness(now, timeout)` computes staleness age = now − last_heartbeat and
  escalates via a real per-member consecutive-miss counter: first miss → `absent`,
  then `lost` once misses ≥ floor_misses (default 2). Returns the *affected* set
  (members whose status changed this pass). A fresh heartbeat resets the miss streak
  (soft-recovery). t = `tick()` alias.
- **`HealthAggregator`** → `HealthReport`: flips stale members first (unless
  apply_liveness=False) then scores. Verdict via `health()`: `healthy` = alive_count ≥
  required AND no critical role lost; `down` if alive_count == 0; else `degraded`.
  Report carries alive/absent/lost counts, missing_required, critical_roles_lost.
- **Injectable clock**: `SwarmClock` (monotonic) / `FixedClock` (start/advance/set) so
  tests drive time deterministically. Inject into registry, protocol, aggregator.
- **`SwarmHealth`** facade bundles registry + protocol + aggregator.

## Pitfalls learned the hard way

1. **floor_misses semantics**: first miss must be `absent`, `lost` only once
   misses ≥ floor. Formula LOST if misses >= floor else ABSENT. With default floor=1 a
   single blip instantly marks a member `lost` — wrong. Default to 2.
2. **Empty swarm** should report `down`, not `degraded`: gate on `alive_count == 0`
   regardless of total.
3. **Check-liveness reports transitions**, not absolute state: a member that stays
   stale re-reports on escalation (absent→lost). Don't assert `== []` on a second
   pass — assert the escalation instead.
4. **Fixture name shadowing**: pyright/pytest resolved an undeclared `registry`
   variable to the module-level *fixture function* (AttributeError at runtime). Every
   fixture you reference in a test body MUST be a declared parameter. Keep fixture
   names distinct from tested-object names.
5. **Fake-clock timing after a revive**: advancing the clock past the timeout right
   after `send_heartbeat` stale-outs the freshly-revived member. Advance by a small
   epsilon (e.g. 1s) when the intent is "revived member stays alive".

## Workspace quirk

In this workspace, ENI-compression carriers intercept a lot of file reads — module
source AND even skill bodies (`skill_view` returns an ENI-COMPRESSED head/tail
instead of the full SKILL.md). When you need the full content of a compressed file,
pull it with a one-liner instead of the read tool, e.g.
`python3 -c "print(open('path').read())"` or grep for the object/class headers. Don't
treat a truncated read as the whole file, and don't patch a skill body based on a
compressed glimpse — recover the real text first.
