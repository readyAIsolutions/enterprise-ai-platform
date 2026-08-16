# Builder FIFO control-channel cron: how it works + stale-job diagnostics

## What the builders' control plane is
Each parallel-build "builder" in the ENI fleet is driven by a **named-pipe FIFO**
(NOT a regular file) at `/tmp/eni_ctl_BUILDER_NN`. One cron watcher per builder polls
its FIFO on a schedule (typically `*/1 * * * *` = every minute).

Real FIFO set (provisioned builders) may be:
- `/tmp/eni_ctl_BUILDER_50` (example v4.1 on-demand builder)
- `/tmp/eni_ctl_DEMIURGE_B01..B12`, `/tmp/eni_ctl_DEMIURGE3D_B01..B12` (legacy headless floor)

Not every `BUILDER_N` number is provisioned — 37 may be a gap while 50 exists.\n\n**Observed FIFO count (Aug 2026): 1/50.** Only BUILDER_50 has a live FIFO;\nthe other 49 builders have no control pipe. This means most builders can only be\ndispatched through PRODUCT_LEAD routing or direct Hermes PTY sessions, not via the\nFIFO control-channel watcher. When running a fleet-state diagnostic, always count the\nFIFOs (`ls /tmp/eni_ctl_BUILDER_* | wc -l`) and report the ratio — a 1/50 ratio means\nthe FIFO control plane is effectively unused.

## Repeated-diagnosis suppression (avoid re-reporting the same stale job)

When a builder FIFO watcher has already been diagnosed as a stale gap
(Nth+1 consecutive firing with no state change and no user action),
the agent should short-circuit to [SILENT] instead of re-running full
diagnostics and re-delivering the same "recommendation: delete" report.

Check: (a) the FIFO is still absent, (b) the same cron ID was diagnosed
in a prior session, (c) no new builder provisioning has occurred.
If all three hold, output [SILENT] — do NOT repeat the diagnostic or
recommendation. The user has been informed and has not acted; further
repetition is noise.

## The CORRECT watcher pattern (shell, per-cron)
`/home/hunter/.hermes/scripts/builder_50_watcher.sh` is the reference model:
```bash
FIFO="/tmp/eni_ctl_BUILDER_50"
STATUS="/home/hunter/Desktop/Projects/ENI_Swarm_NEW/STATUS_BUILDER_50.md"
touch "$STATUS"
# Open RDWR so open() never blocks on missing writer; read -t 1 bounds the read.
if exec 3<>"$FIFO" 2>/dev/null; then
    if read -t 1 -r line <&3 2>/dev/null; then
        echo "[IN-PROGRESS] $line" > "$STATUS"
        date +%s > /tmp/builder_verified
    else
        echo "[IDLE] Waiting for task..." > "$STATUS"
    fi
    exec 3<&-
else
    echo "[IDLE] FIFO missing" > "$STATUS"
fi
```
Key mechanics to preserve when writing any builder watcher:
- Open with `exec 3<>"$FIFO"` (RDWR) so `open()` does not block forever waiting for a writer.
- Bound the read with `read -t 1` so the cron exits promptly when idle.
- Non-blocking-clean on a **missing** FIFO (`else` branch -> `[IDLE] FIFO missing`), never throw.
- Write a STATUS file so the watcher is observable; `last_status: ok` alone is not proof of useful work.

## Diagnosing a stale / no-op builder watcher cron
Signs it is a dead job rather than a working watcher:
1. The `prompt` is a Python-style multi-command string
   `read_file(path='/tmp/eni_ctl_BUILDER_37') && skill_view(name='hermes-agent') && delegate_task(...)`
   instead of a shell script call. The three-command prompt does not do FIFO RDWR semantics.
2. The referenced `/tmp/eni_ctl_BUILDER_N` FIFO **does not exist** in `/tmp` — builder not provisioned.
3. `repeat.completed` is very high (hundreds) yet no artifact/status file is produced — it is
   "succeeding" (exit 0, `last_status: ok`) into the void every minute.

Diagnostic procedure:
- `ls -la /tmp/ | grep -E "eni_ctl_BUILDER|eni_ctl_DEMIURGE"` -> real provisioned FIFO set. Note `prw` = named pipe.
- Read `~/.hermes/cron/jobs.json` and filter by id/name to get the job's `prompt` + `schedule` + `repeat.completed`.
- Cross-check the cron id with `/tmp/eni_listing.txt` (a `ls` snapshot of /tmp).

## Resolution
- If the builder number is NOT part of the live fleet: suspend/delete the cron job (`hermes cron` / jobs.json) to stop minute-level no-ops. Do NOT mutate jobs.json without the user — report and recommend.
- If the builder IS intended: `mkfifo /tmp/eni_ctl_BUILDER_N` and port the cron to the shell
  watcher pattern above instead of the three-command Python prompt.

## Caveat
A Python `read_file(...)` on a FIFO can hang or mis-report; the shell RDWR-watcher is the
canonical, safe form. Never answer "no task" by fabricating a task line — if the FIFO/channel
doesn't exist and no line was queued, report IDLE / stale-job, not a processed task.

## Builder state file-layout map (quick triage)
When a cron fires "process builder N" and you must decide whether a REAL task is queued,
you do NOT need to decompress/read the whole builder persona prompt. Triangulate from the
on-disk state around the numbered builder (paths under `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/`):
- Control FIFO: `/tmp/eni_ctl_BUILDER_N` — the ONLY hard trigger. If it does not exist,
  **no task is queued** → IDLE, stop. Its presence (not its 0-byte size) is the signal.
- Task definition: `config/eni_build_tasks.json`, entry with `"name": "BUILDER_N"` — gives
  `workdir`, `model`, `provider`, `status_file`, and the (long) persona prompt. Builder defaults
  to `nvidia/nemotron-nano` on `free-router`.
- Task prompt: `tasks/swarm/BUILDER_N.txt` (short: "You are BUILDER_N ... monitor FIFO ... write STATUS").
- Status files — write to BOTH: `STATUS_BUILDER_N.md` (repo root) and `tasks/status/STATUS_BUILDER_N.md`.
  An existing status `[IDLE] / blocker=none / next=await ... FIFO creation` is normal, not an error.
- Builder log: `.cache/eni_swarm/builder_logs/BUILDER_N.log`.
- NOTE: config `workdir` may say `~/Desktop/Projects/ENI_Swarm_NEW` while the LIVE status/log/task
  tree actually lives elsewhere. There is NO single authoritative tree — builder state is scattered
  across at least THREE real locations, all observed in the wild:
  - `~/Commander/eni_swarm/builds/`  ← builder fleet status (e.g. STATUS_BUILDER_37.md)
  - `~/Desktop/Projects/ENI_Swarm_NEW/`  (e.g. STATUS_BUILDER_50.md, plus its /tmp FIFO watcher)
  - `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/`  (config workdir / legacy)
  When locating a builder's files, fall back to searching BOTH/all trees — trust the existing files
  over the config's workdir field. A STATUS_*.md that exists in one tree while the matching
  /tmp/eni_ctl_BUILDER_NN FIFO is absent in all trees is the normal DORMANT state (no directive
  ever issued), NOT a failure and NOT a signal to fabricate work.

Decision rule: FIFO present + has content → process the directive. FIFO present but empty → in-progress/idle.
FIFO absent + status says IDLE → report [SILENT]/IDLE, do NOT fabricate work and do NOT create STATUS by hand.

## Canonical IDLE probe (persisted)
Rather than re-deriving the five-mirror set by hand, run the persisted probe:
`bash scripts/check_builder_idle.sh BUILDER_NN` (lives in this skill's `scripts/` dir).
It checks the FIFO, scans all FIVE mirror paths (4 markdown `STATUS_<N>.md` + the
`.cache` INI `BUILDER_NN_STATUS.md`), and tokenizes BOTH the markdown H1 (`— IDLE`)
and INI (`status=[IDLE]`) formats. Exit 0 = FIFO absent AND all mirrors agree IDLE
=> genuine steady-state idle => report [SILENT]. Exit non-zero prints what is out of
sync. Originally at /tmp/check_builder_idle.sh; persisted Aug 2026 so /tmp cleanups
never lose it.

## PITFALL: never read the control FIFO directly
A builder watcher-cron directive may literally say `read_file('/tmp/eni_ctl_BUILDER_NN')`
or `cat` the control path. Do NOT do either on the FIFO itself:
- `read_file` on a FIFO returns `File not found` (it is not a regular file).
- `cat`/plain `open()` on a FIFO BLOCKS until a writer connects — on a provisioned
  idle builder there is no writer, so it hangs (~180s to tool timeout).
Always drive the check through the persisted probe `check_builder_idle.sh BUILDER_NN`
instead, which tests `[ -p ]` before touching the FIFO and never blocks. Interpret
the result per the rules above: FIFO absent + all 5 mirrors agree IDLE => [SILENT].

## Authoritative probe path (do NOT hunt for it)
The probe is NOT installed at `~/.hermes/scripts/` (do not `ls` there for it). Its
canonical, versioned copy is this skill's own script:
`/home/hunter/.hermes/skills/eni-swarm/eni-swarm-operations/scripts/check_builder_idle.sh`
Run: `bash <that path> BUILDER_NN`.
(Note: an older duplicate also exists at
`/home/hunter/.hermes/skills/devops/eni-mini-protocol/scripts/check_builder_idle.sh`.
They should converge on one home — but either works; prefer the eni-swarm-operations copy.)
Exit convention: `0` = steady-state IDLE (FIFO absent + all found mirrors agree on
`[IDLE]`), `3` = FIFO is a live pipe (directive may be pending → act), `4` = stale
regular file occupies the FIFO path (repair needed).

## Gap / non-provisioned builder cron directives (e.g. BUILDER_37)
A cron may fire referencing a `BUILDER_NN` whose FIFO path does NOT exist. `37` is a
documented gap — only `BUILDER_50` plus the `DEMIURGE_*`/`DEMIURGE3D_*` floors are
provisioned. When this happens AND the "directive" payload is empty/vague (e.g. just
"process the builder task" with no actual job content):
- Confirm FIFO absence with `ls -la /tmp/eni_ctl_*` and `[ -p /tmp/eni_ctl_BUILDER_NN ]`
  (should be false). Also confirm no stale *regular* file occupies the path — a regular
  file there is exit `4`, a repair condition, not idle.
- Treat as steady-state IDLE → exit `0` / report `[SILENT]`. Do NOT fabricate work and
  do NOT spawn an empty `delegate_task`: an empty goal yields hallucinated output, not a
  job. If no real directive is queued, there is nothing to process.

## Reading skill content when tool output is ENI-COMPRESSED
When `skill_view`, `read_file`, or `terminal` output comes back as
`<ENI-COMPRESSED ratio=Nx carrier=.../carrier_....png (recover via decompress)`, the
gateway has packed the tool payload into a steganographic PNG carrier. To read the
underlying content WITHOUT the decompression toolchain:
- Read the skill's raw markdown/scripts directly from disk, e.g.
  `~/.hermes/skills/eni-swarm/eni-swarm-operations/references/<file>.md`.
- Keep reads short/narrow (`read_file` with small `limit`/`offset` windows) — large
  payloads trip the compression threshold; short ones usually pass through plain.
- Use the `--- head ---` / `--- tail ---` fragments the compressed wrapper ALREADY
  returns: they expose the top and bottom of the payload and are often enough to find a
  patch anchor or answer the question without decoding the carrier.