# monitor_fleet.py — the cron ledger generator

A scheduled fleet monitor lives at `/home/hunter/Commander/eni_swarm/monitor_fleet.py`.
It runs as a cron job and writes `HEARTBEAT_LEDGER.md` in that same directory.

## What it does
- Scans `STATUS_BUILDER_<N>.md` (in `builds/` subdir, falling back to cwd) and collapses each
  into one ledger line: `[STATE] BUILDER_N verified=... blocker=... next=...`.
- Maps each file to `DONE | IN-PROGRESS | BLOCKED`.
- Also reads `HEARTBEAT_ALERTS.md` (if present) for `- BUILDER_<N>` lines and force-marks those
  builders BLOCKED.

## Critical pitfall — the ledger is CONTENT-DERIVED, not a liveness signal
The states come from parsing the STATUS file's own text, NOT from whether the builder is actually
running. A stale `# STATE: IN-PROGRESS` marker from weeks ago still shows up as IN-PROGRESS.
Always cross-check before reporting:
- **STATUS file mtimes** — if all are 1–2+ weeks old and only one is fresh, the "IN-PROGRESS"/"BLOCKED"
  rows are stale artifacts, and the fleet is effectively idle/parked.
- **Live processes** — `ps aux | grep -iE "eni|builder|swarm"`; expect daemons (`eni_kb_daemon`,
  `eni_controller :8940`, `swarm_turbocharger :8922`) even when builders are idle. No build procs =
  nothing active.
- **Control FIFOs** — `ls /tmp/eni_ctl_*`; a builder with no FIFO has received no directive.
- **Dashboard** — `curl -s -m 3 -o /dev/null -w "%{http_code}" http://127.0.0.1:8420/`; a `000`
  means the swarm web dashboard is down even if the ledger looks healthy.

A healthy, non-actionable fleet report says: script exit 0, ledger regenerated, N builders, and a
clear note that states are stale + no live build procs + dashboard up/down.

## Working around the ENI-COMPRESSED wrapper on paid models
In this environment a plugin (`eni-omega-compress-paid`) wraps large tool results in
`<ENI-COMPRESSED ...>` blocks and persists the full payload to a carrier PNG. Recovering that payload
is unreliable here: the decompress path (worker module + paq8pxd) is frequently unavailable, and the
carrier PNGs can be 1×1 px stubs carrying no real data. Don't burn effort trying to decode carriers.

**Technique that works:** keep tool invocations COMPACT so results stay under the compression
threshold and come back as plain text you can actually read. Concretely:
- Prefer a single short `python3 -c "..."` that computes a summary (counts, `Counter` of states,
  list of matching lines) over commands that dump whole files or long directory listings.
- Read `head`/`tail` slices of STATUS files rather than whole files.
- The compressed block still shows `--- head ---` and `--- tail ---` slices, so even if a result IS
  wrapped, you can often get the gist from those without decoding.
