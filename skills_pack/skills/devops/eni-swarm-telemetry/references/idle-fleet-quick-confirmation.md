# One-shot idle-fleet confirmation (cron/quick triage)

When a fleet-status cron fires and the ledger is dominated by stale rows, confirm
"dormant, not broken" in ~2 quick checks instead of a multi-step process investigation.
Pairing infra-health + control-channel state with the mtime cross-check makes the
idle determination airtight and fast.

## The two cheap authoritative checks

1. **Controller infra health** — one HTTP hit, returns full 6-check diagnosis:
   ```
   curl -s -m 5 http://127.0.0.1:8940/health
   # -> {"overall":{"healthy":true,...checks_ok":6}, "queue":{"pending":0}}
   ```
   Healthy + `queue.pending:0` = infra live and NO work queued. This single response
   covers airllm brain, free_router, secrets vault, enterprise modules, hermes_runner,
   and the queue in one call.

2. **Control-FIFO enumeration** — what control channels are actually open:
   ```
   ls -la /tmp/eni_ctl_* ; ls /tmp/eni_ctl_* | wc -l
   ```
   If only a handful of stale FIFOs exist (e.g. `BUILDER_50` + a family like
   `DEMIURGE*_B01..B12`) and NO per-builder control FIFO for the builder in question
   exists, then NO directive has been issued and no builder is actively being driven.
   A freshly-touched STATUS file for one builder (e.g. a daily-touch `STATUS_BUILDER_37.md`)
   is a scheduling-template heartbeat, NOT evidence of active work.

## Corroborating broad-swarm source: MASTER_STATUS.md
`/home/hunter/Commander/eni_swarm/MASTER_STATUS.md` is the status_hub
(auto-gen by `status_hub.py` / worker w2, refreshed ~every 5 min / on demand).
It consolidates EVERY `STATUS_ENI*.md` mini AND the per-project `STATUS_*` files
(recursive), and is a stronger cross-check than the per-builder ledger because it
spans the whole ecosystem, not just the 50-builder floor. Its alert rule is
explicit and useful: ALERT when STATE==BLOCKED OR (STATE != DONE AND age > 10 min);
DONE minis are terminal and their age is informational only.

How to read it for a dormant-fleet report (safe via grep, no ENI wrapper):
```
grep -cE "\| YES \|"  MASTER_STATUS.md   # stale/stalled rows (often ~390)
grep -cE "\| BLOCKED \|" MASTER_STATUS.md
grep -cE "\| IN-PROGRESS \|" MASTER_STATUS.md
grep -cE "\| DONE \|" MASTER_STATUS.md
```
- Hundreds of stale `YES`/IN-PROGRESS rows across the hub is the ecosystem-wide
  mirror of the builder floor: dormant, and NO per-row intervention is warranted —
  status_hub regenerates from disk and is "never the source of truth". A broad
  staleness spread is cosmetic, not a crash.
- It also confirms "DONE means READY/IDLE": DONE minis with old mtimes are given a
  pass by the ALERT rule, matching the ledger's `[DONE]`="IDLE" semantics.
- Use it to widen a non-silent report (give the whole-ecosystem tally) but do NOT
  count its staleness as a reason to act — that is the exact intraday state captured
  as `status_hub.py`'s 5-min self-heal and never means intervention.

## Corroborating config fact: autobuild is intentionally OFF
`crontab -l` shows the swarm boot line commented out:
`#DISABLED-by-LO-stop-autobuild @reboot swarm_start_opt.sh`.
So a dormant fleet is the EXPECTED end-state, not a crash symptom — LO
explicitly stopped auto-bringing the mini swarm up at boot. When confirming
idleness, checking this crontab comment removes the last doubt: if autobuild
is disabled and nothing is queued, do nothing. Note `status_hub.py` (heartbeat
watchdog) usually still fires every 5 min; that's a monitor, not a builder.

## Composite rule
- All/most STATUS mtimes share one old "parking date" (~14-16 days old), AND
- controller `:8940/health` is healthy with 0 pending, AND
- no open control FIFOs beyond stale ones, AND
- no live per-builder `hermes chat` processes:

→ **Fleet is DORMANT and healthy.** No stalls, no blockers, no intervention.
If state is unchanged from the last cycle, the correct cron output is exactly
`[SILENT]` — re-reporting identical idle counts is monitor noise. Only emit a
non-silent report when state CHANGED (builder started/stalled/BLOCKED, a real
blocker named, an alert file exists, or intervention is genuinely needed).

## Re-verified (3rd instance) — Aug 10 2026
Ran `monitor_fleet.py` as a cron: clean run, 50 builders, this time **40 DONE /
8 IN-PROGRESS / 1 BLOCKED** (counts drift a little between cycles — 41 DONE
last time — so take exact ledger tallies as indicative, not gospel). The 8
IN-PROGRESS + 1 BLOCKED were again stale Jul-25 frozen files; `find -mmin
-1440` showed exactly ONE fresh file (B37, state=`IDLE`); `ps` showed zero
per-builder worker procs for the IN-PROGRESS cores; only stale
`BUILDER_50` + `DEMIURGE*_B01..B12` FIFOs live. Also found `BUILDER_20.md` =
0 bytes (empty-skip) and crontab `#DISABLED-by-LO-stop-autobuild` confirming
dormancy is intentional. Conclusion unchanged: dormant + healthy, `[SILENT]`
or "nothing new" is the correct output.

## Verified Aug 2026
Ran as a fleet-status cron: 49-builder ledger, 48 stale (Jul-25 parking date),
B37 daily-touch only, controller 6/6 healthy + queue 0, no active control FIFOs,
no per-builder worker procs. Conclusion: fully dormant, no action required.

## Re-verified (2nd instance) — same pattern reproduced
Ran `monitor_fleet.py` again as a cron. Clean run, ledger regenerated with 50
builders (41 DONE, 8 IN-PROGRESS, 1 BLOCKED). The 8 "IN-PROGRESS" + 1 "BLOCKED"
labels were ALL parsing artifacts of frozen Jul-25 files — `find -mmin -1440`
showed exactly ONE file touched in 24h (B37, and its state token read `IDLE`),
`ps` showed 0 per-builder worker python procs, and no per-builder control FIFOs
existed (only stale `BUILDER_50` + `DEMIURGE*_B01..B12`). Missing-number check:
`STATUS_BUILDER_20.md` present but 0 bytes (empty-skip), and BUILDER_5 lives on
disk as zero-padded `STATUS_BUILDER_05.md`. Conclusion: fleet again dormant;
IN-PROGRESS/BLOCKED ledger lines are not live stall signals. Confirms the
composite rule holds across repeated cycles — a regenerated ledger alone does
NOT indicate activity; the mtime + proc + FIFO cross-check is mandatory.

## Healthy-dormancy signature: the self-re-verifying IDLE builder
Distinguish *healthy dormancy* from a *stalled/hung* worker by looking for builders
that actively reconfirm they have nothing to do. On the Aug 10 cycle, `BUILDER_37`
was the healthiest signal in the whole fleet and the model to recognize:
its status file re-verified empirically that `/tmp/eni_ctl_BUILDER_37` does NOT
exist (`[ -e ]` NO_ENTRY, `[ -p ]` NOT_A_PIPE), noted no directive was issued, and
stated an explicit **"IDLE — do not invent work"** policy. That is the correct,
canonical dormant-builder posture: it re-checked its own control channel and refuses
to fabricate a task rather than spin on stale IN-PROGRESS. When interpreting a
stale-ledger cron, a recently-touched IDLE status file like this is a strong
positive confirmation of "dormant and healthy" — NOT another stalled row. Contrast
it with the stale `[IN-PROGRESS]` rows (2+ weeks old mtime, no live proc, no FIFO),
which are terminal remnants of the old stall wave, not current activity. An
infra-health hit (`curl :8940/health` -> `queue.pending:0`) plus one such IDLE
file plus 0 worker procs closes the "dormant, not broken" case in ~2 checks.

## PITFALL — leftover control FIFOs in /tmp are NOT a liveness signal
(verified 2026-08-10 run) A fully dormant fleet can still have many stale control
FIFOs lingering in `/tmp` from older spawns — e.g. 25 `eni_ctl_*` entries
(`eni_ctl_BUILDER_50`, `eni_ctl_DEMIURGE*`, `eni_ctl_DEMIURGE3D*`) present while
`ps` shows 0 worker procs and every STATUS mtime except one is parked weeks old.
Do NOT treat FIFO presence as activity. The authoritative liveness trio is:
infra-health `queue.pending:0` + 0 worker procs + a single recently-touched IDLE
status file (whose own text re-verifies its *own* FIFO is absent — that absence
is the real tell, because that builder is alive enough to check). Count FIFOs
with `ls /tmp/eni_ctl_* | wc -l` for context, but never as proof of a working
builder. The per-builder FIFO that matters is the one the recent IDLE builder
re-verifies as missing.
