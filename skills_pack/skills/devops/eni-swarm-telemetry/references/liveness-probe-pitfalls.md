# Fleet-monitor liveness-probe pitfalls (verified 2026-08-11 monitor cron run)

These bite when running `monitor_fleet.py` as a cron job and cross-checking the
ledger against disk state. All verified on an actual parked-fleet cron run.

## Pitfall 0 — the probe script's real disk path + correct invocation
`fleet_liveness_probe.sh` is described as "SKILL-BUNDLED", so don't guess its
path — it lives under the **category subdir** of the skills tree, not the bare
skill name:
```
~/.hermes/skills/devops/eni-swarm-telemetry/scripts/fleet_liveness_probe.sh
```
(A first guess at `~/.hermes/skills/eni-swarm-telemetry/scripts/...` fails with
"no such file". Locate it once with `find ~/.hermes/skills -name fleet_liveness_probe.sh`.)
When invoking from a cron/hermes shell, **either** `cd` into the swarm dir **or**
pass it as `$1` — the script has a guard that prints a loud WARNING when it sees
0 status files (a wrong-cwd false alarm, not a dead fleet). The guard only fires
on zero files; a wrong-enough-but-nonzero count won't wake you, so always pass
the explicit swarm dir: `bash <path>/fleet_liveness_probe.sh /home/hunter/Commander/eni_swarm`.

## Pitfall 1 — `pgrep -af` SELF-MATCHES the cron wrapper
```
pgrep -af 'STATUS_BUILDER' | wc -l   # → returned 2, but fleet was parked!
```
Inside a cron / hermes-shell wrapper, the *wrapper bash command line itself*
contains the pattern you're grepping for (`... eval 'pgrep -af STATUS_BUILDER' ...`),
so pgrep matches its own parent shell. A healthy-looking count (1–2) is NOT
liveness — **filter the wrapper out**:
```bash
ps -eo pid,args --no-headers | grep -iE 'STATUS_BUILDER|build_controller|eni_swarm' \
  | grep -vE 'grep|/bin/bash -c|_hermes_snap|status_hub'
```
Zero remaining rows (after the filter) = parked fleet even when the raw count said 1–2.
Corroborate with `find builds/ -name 'STATUS_BUILDER_*.md' -mmin -10080 | wc -l`.

## Pitfall 2 — builder filenames are ZERO-PADDED
Status files are `STATUS_BUILDER_01.md … STATUS_BUILDER_09.md` but
`STATUS_BUILDER_50.md` (unpadded above 9). A naive loop:
```bash
for i in $(seq 1 50); do [ -f "builds/STATUS_BUILDER_${i}.md" ] || echo "MISSING $i"; done
```
falsely reports BUILDERS 1–9 as missing. Pad the probe:
```bash
for i in $(seq 1 50); do
  n=$(printf '%02d' $i); [ -f "builds/STATUS_BUILDER_${n}.md" ] || echo "MISSING $i";
done
```

## Pitfall 3 — ledger lines < file count is EXPECTED, not an error
Every builder file is scanned; **empty files are skipped by the crash-guard**
(good — a blank/corrupt STATUS file must not be parsed as real state). So on a
50-file fleet the ledger can legitimately have 48–49 lines. Verify with:
```bash
ls builds/STATUS_BUILDER_*.md | wc -l        # 50 files
grep -c 'BUILDER_' HEARTBEAT_LEDGER.md        # 48-49 entries
for f in builds/STATUS_BUILDER_*.md; do [ -s "$f" ] || echo "EMPTY: $f"; done
```
"Missing" builders in the ledger are usually just empty files, not lost builders.

## Pitfall 4 — "controller down" needs the right port set
A controller that "looks healthy" may still be absent. Probe the full set, and
don't assume port 8080 belongs to the swarm:
```bash
for p in 8420 8421 8422 8080 8000; do \
  printf '%s -> %s\n' "$p" "$(curl -s -m2 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/health)"; done
```
On LO's box: 8420/8421/8422/8000 all `000` (down), but **8080 is signal-cli**, not
the swarm — a `200`/`404` there is a false signal. A separate long-running
`swarm_turbocharger.py --port 8922` is an aux process, not a controller; don't
count it as build-floor liveness. A live status_hub writing
`MASTER_STATUS.md` (regenerating it) coexists with a parked floor — workers can
publish stale-flavored aggregates without any builder running.

## Combined interpretation (parked-fleet signature)
Use ALL of: (a) files-in-24h/7d counts, (b) filtered ps liveness, (c) controller
port health. When only 1 file in 24h, 0 filtered builder procs, and all swarm
ports dead → the fleet is parked awaiting LO directive, regardless of how many
`[IN-PROGRESS]` markers the ledger carries. `[DONE]` in the ledger = idle/ready,
not task-complete. Report as parked, don't invoke a rebuild.