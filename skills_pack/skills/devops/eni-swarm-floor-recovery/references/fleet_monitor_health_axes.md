# Fleet Monitor — Independent Health Axes & Probe Points

Use when a cron (or an agent) asks "is the ENI swarm down / idle / mid-work?" The swarm
is NOT one thing. It has several independent components that can each be up or down on
their own. Report the state of EACH axis separately and never conclude "system down"
from "build floor down."

> **Frequent-cron note:** If the fleet has been persistently idle (gate=RED, windows=0)
> for days/weeks, see `monitor_cron_diagnostics.md` → "Repeated-state suppression" for
> guidance on when to suppress identical reports with `[SILENT]` instead of repeating
> the same findings across every firing.

## The axes and how to probe them

1. **Builder floor** (the 50 STATUS_BUILDER_*.md + HEARTBEAT_LEDGER.md in `eni_swarm/builds/`).
   - Probe: `sed``ls`-check mtimes of `builds/STATUS_BUILDER_*.md` (most-recent known good
     pattern: `Aug 12 07:50 STATUS_BUILDER_37.md`; weeks-old mtimes = stale). `fleet_pulse.py`
     prints `windows=N | gate=RED/GREEN`. **MUST call as `python3 fleet_pulse.py --once`** —
     run bare, it loops forever on a ~60s tick and HANGS whichever wrapper/cron invokes it
     (observed 180s timeout / exit=124). `--once` does a single tick and exits.
   - `fleet_pulse.py` with `gate=RED, windows=0, stalls=none` + an empty `tasks/` queue
     (`./tasks/*.task` freshly dated) == floor is IDLE/DOWN with nothing to relaunch => do
     NOT relaunch. Only relaunch against actual queued work.

2. **Web dashboard** on `:8420` (v4.1 optimized-fleet UX).
   - Probe: `curl -s -m 6 -o /dev/null -w "%{http_code}" http://localhost:8420/`.
   - Expect `200`; **`HTTP 000` = connection refused / down.** This is a SEPARATE axis from
     the controller — the dashboard can be down while the orchestration brain is fine.

3. **`swarm_turbocharger` proxy** on `:8922` (OpenAI-style front for the fleet, concurrency 40).
   - Probe: `curl -s http://localhost:8922/health` -> `{"status":"ok","proxy":"swarm_turbocharger","concurrency":40}`.
   - `/health` is the real endpoint (root `/` returns `{"error":"not found"}` — that 404 is
     NORMAL, not a failure). Healthy => the model-serving layer is up even if the floor is idle.

4. **Controller / orchestration brain** (`status_hub.py` + heartbeat minis).
   - `eni_heartbeat.py` prints `gate=GREEN, live=N minis`, plus minis breakdown
     (`598 minis (207 done / 388 in-progress / 3 blocked)`, `AL=391` pre-existing alerts).
   - `status_hub.py` self-heals and rewrites `MASTER_STATUS.md` every minute; a fresh
     "Generated: <today>" timestamp = controller alive and updating. **Always say the controller
     is healthy even when the floor is down** — brain and builders are independent.

## The trap this guards against
`monitor_fleet.py` writes `HEARTBEAT_LEDGER.md` purely from whatever STATUS files are on disk.
Weeks-dead files produce `[IN-PROGRESS]` / `[BLOCKED]` rows that are zombie entries, NOT live
builders. Cross-check ledger rows against a process sweep (`ps aux | grep -i builder|fleet`)
and file mtimes before flagging anything as stalled or needing re-dispatch.

## Two ledger gotchas: silent-drop + false-IN-PROGRESS (read the body, not the token)
- **Silent drop from empty/blank STATUS files.** `monitor_fleet.py` skips any status file with
  no non-blank lines (`if not lines or not any(l.strip()...)`: continue). So a builder MISSING
  from the `HEARTBEAT_LEDGER.md` numbering (e.g. 1..50 but no BUILDER_20) does NOT mean it
  finished cleanly — it usually means `STATUS_BUILDER_20.md` was truncated to 0 bytes / never
  written. Verify with `wc -l builds/STATUS_BUILDER_<n>.md`. A gap in the ledger sequence is
  itself an anomaly worth reporting, not a silently-finished unit.
- **`[IN-PROGRESS]` token with an idle body.** Builders are often left marking `[IN-PROGRESS]` /
  `[STATE: IN-PROGRESS]` while their body text says "awaiting task assignment from
  PRODUCT_LEAD" / "no project assigned yet / ready and idle". If you tally ledger rows, these
  count as IN-PROGRESS, but they are actually IDLE-and-wrongly-state-tagged. When you see a
  frozen (weeks-old mtime) IN-PROGRESS row, `head -15` the file and read the body — if it says
  "awaiting/ready/idle/awaiting FIFO dispatch", report it as a **parked/idle mislabeled
  IN-PROGRESS**, not a stalled build. Only rows whose body names real in-flight work (e.g.
  "AppImage build: RUNNING", "Phase: packaging") are true stalled builds worth re-dispatching.

## Measure HOW MANY builders are live vs stale (freshness heat-map)
"IN-PROGRESS" rows in the ledger do NOT mean live. Quantify the live set directly from
mtimes so you can say "N of 50 builders genuinely live, M stale since <date>":
```
now=$(date +%s)
# live in last 24h (real work happenng now):
find builds -name 'STATUS_BUILDER_*.md' -mmin -1440 -printf '%f -> %TH:%TM\n' | sort
# live since a cutoff (recently active this month):
find builds -name 'STATUS_BUILDER_*.md' -newermt '2026-08-01' -printf '%f -> %TY-%Tm-%Td %TH:%TM\n' | sort
# full age spread: newest vs oldest
find builds -name 'STATUS_BUILDER_*.md' -printf '%T@ %f\n' | sort -n | tail -3
find builds -name 'STATUS_BUILDER_*.md' -printf '%T@ %f\n' | sort -n | head -3
```
Typical finding (Aug 2026): only 1 of 50 (B37, IDLE awaiting FIFO) is fresh; the other
IN-PROGRESS rows are zombie frames from Jul 9-25. Ledger state-count quick tally:
`grep -c '^\[DONE\]' HEARTBEAT_LEDGER.md` (likewise IN-PROGRESS / BLOCKED), and
`grep -c 'verified=unknown blocker=unknown next=unknown'` = rows with no real detail.
- **Missing builder number in the ledger = blank STATUS file, NOT a dead builder.**
  `monitor_fleet.py` has a crash-guard: it SKIPS any `STATUS_BUILDER_<N>.md` that is empty or
  all-whitespace. So an absent row (e.g. cache a clean 49/50 ledger missing BUILDER_20) means
  that builder's STATUS file was blank — not that the builder vanished. Count of rows may be
  <50 for this reason; do not report "a builder is gone".

## Scope: MASTER_STATUS mini-count vs HEARTBEAT_LEDGER builder-count
These are TWO DIFFERENT SCOPE VIEWS, not a contradiction:
- `MASTER_STATUS.md` (status_hub) reports legacy **minis**: `598 minis (207 done / 388
  in-progress / 3 blocked)`, `AL=391`.
- `HEARTBEAT_LEDGER.md` (monitor_fleet.py) reports the **50 on-demand builders**.
Do not call "388 in-progress" a live-build count — it is the stale cumulative mini registry.
Report each scope's count separately and attribute the number to its source.

## Minimal one-shot sweep
```
cd ~/Commander/eni_swarm
python3 monitor_fleet.py
python3 fleet_pulse.py --once   # windows / gate (ALWAYS --once, else it hangs)
curl -s -m6 -o/dev/null -w "dash=%{http_code}\n" http://localhost:8420/
curl -s http://localhost:8922/health   # turbocharger
find builds -name 'STATUS_BUILDER_*.md' -newermt '1 day ago' | head
```

## Interpreting probe responses (concrete shapes seen in the field)

- **Dashboard `:8420`** — `curl -m6 -o/dev/null -w "%{http_code}"` returns `200` when up, **`000`**
  when nothing is listening (curl couldn't connect). `000` ≠ "crashed" necessarily — the
  dashboard is the first component to die on reboot and is independent of the builder floor.
  Check `ps aux | grep -E "8420|status_hub|dashboard"` to see if a process is even running.
- **Turbocharger `:8922`** — `curl http://localhost:8922/health` returns JSON of the form
  `{"status":"ok","proxy":"swarm_turbocharger","concurrency":40,"signal":-60}`. A valid
  JSON `"status":"ok"` body means THIS axis is up regardless of dashboard/dash code.
- **status_hub controller liveness** — tail `status_hub.cron.log`: if the last lines are
  `MASTER_STATUS.md refreshed: ... ALERTS -> .../MASTER_STATUS.md`, the ~5-min self-heal
  cron is alive (it regenerates MASTER_STATUS.md from disk; the file is never source of truth).
- **Pulse recompute** — `fleet_pulse.py --once` reads the CURRENT ledger, so run
  `monitor_fleet.py` FIRST, then pulse; the `windows=N | gate=RED/GREEN` line reflects the
  just-written ledger, not the stale one. A `windows=0 gate=RED` result with no stalls and
  healthy :8922 = idle floor, not a crash.

## HTTP probe semantics — `000` vs `404` (down vs up-but-wrong-route)
Use `curl -s -m 5 -o /dev/null -w "%{http_code}" <url>` on each port. Read the code carefully:
- **`000`** = connection refused, NO listener bound → the service is genuinely DOWN. Do not
  confuse with a slow timeout; `-m 5` limits it. e.g. `curl 8420 → 000` = dashboard down.
- **`404`** on `/` = a process IS listening but no root route. This is NOT "down" — it's
  up-with-a-different-schema; probe the real health path before concluding. e.g. `:8922`
  serves `/health` → `200`, but `/`, `/status`, `/api/health` all → `404`. Only `/health`
  is a valid liveness probe for the turbocharger.
- One-liner sweep that discriminates properly:
  `for p in /health /api/health /status; do curl -s -m 4 -o /dev/null -w "$p %{http_code}\n" http://127.0.0.1:8922$p; done`
- Verify the process exists even when curl is ambiguous:
  `ss -tlnp | grep -E "8420|8922"` (shows bound port + pid) and `ps aux | grep swarm_turbocharger.py`.
- **Stale-vs-live builder count** — after a long quiet period, only ONE STATUS file may be
  fresh (e.g. a watchdog IDLE re-check); the "388 IN-PROGRESS / 598 minis" figure in
  status_hub/MASTER_STATUS is the cumulative Jul registry, NOT live builders. Attribute the
  number to its source before reporting it as a live-build count.
- **status_hub controller axis probe** — this axis has NO `status_hub/` directory and NO
  dedicated process to grep for; it is proved ALIVE by a FRESH `MASTER_STATUS.md` mtime
  (worker w2 / ENI12 rewrites it every cycle — e.g. "Generated: 2026-08-14T06:25:01 by ENI12
  STATUS HUB mini"). Probe with `stat -c '%y %n' .../MASTER_STATUS.md`. When the builder
  floor is down (gate RED), do NOT infer the controller is down too — check that mtime first.
  The :8420 dashboard is yet another independent axis: it can be DOWN (curl 000, no bound
  port) while the turbocharger (:8922) and the status_hub controller are both UP. Report all
  four axes separately.

## Turbocharger (:8922) up-signal trap
The turbocharger's ROOT path returns **HTTP 404** (`curl http://127.0.0.1:8922/` -> 404,
and `/status`, `/api/health`, `/healthz` also 404). A 404 on root is NOT a "down" signal —
the correct up-probe is `/health` -> **HTTP 200**, and confirm the port is bound
(`ss -ltnp | grep :8922`). Never declare the turbocharger down from a root-path 404 alone;
only a failed `/health` probe (curl 000 / connection refused) means it's actually down.
Symptom table: dashboard down = curl 000 + no bound :8420; turbocharger up = /health 200 +
bound :8922; controller up = fresh MASTER_STATUS.md mtime. These three can be independently
up/down in any combination.

## Probe-script invocation pitfall (absolute path, not repo-relative)

The bundled `fleet_health_probe.sh` is a convenience that runs all four probes plus the pulse
in one shot — the recommended drop-in for monitor crons. It is NOT checked into the eni_swarm
repo, so running `bash scripts/fleet_health_probe.sh` from `eni_swarm/` fails with
`No such file or directory`. Invoke it by absolute path from the skill directory instead:

    bash /home/hunter/.hermes/skills/devops/eni-swarm-floor-recovery/scripts/fleet_health_probe.sh

(Run it from anywhere; `cd` into `eni_swarm/` is not required.) The probe reports each axis
> **Pitfall — zero-padded filenames:** STATUS files on disk are zero-padded
> (`builds/STATUS_BUILDER_05.md`), but `monitor_fleet.py` normalizes them to
> unpadded numbers in the ledger (`BUILDER_5`). So when hand-inspecting a
> builder by number, `cat STATUS_BUILDER_5.md` FAILS with "no such file"; use
> `STATUS_BUILDER_05.md` (or `ls STATUS_BUILDER_5*`, which also catches 50).
> The MISTAKEN "missing file" is not a real gap — the monitor's own `find`
> count of 50 files is authoritative.

The probe reports each axis separately plus a final `| windows= | stalls= | gate=` pulse line, and its interpretation footer distingui
distinguishes "idle/dormant" (gate=RED + windows=0 + stalls=none + empty queue) from "down."
Confirm the `[SILENT]` suppression decision against the PRIOR cron firing via `session_search`
before deciding the state is truly unchanged — see monitor_cron_diagnostics.md.