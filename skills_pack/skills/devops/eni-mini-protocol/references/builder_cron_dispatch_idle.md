# Builder cron/dispatch-frame idle variant

Companion to `builder_control_fifo_idle.md`. Covers the case where a builder is
woken NOT by its control FIFO having content, but by an out-of-band dispatch frame
(a scheduled cron job / dispatcher message) whose *text* looks like a task.

## Observed pattern (BUILDER_37, Aug 2026)

A cron frame arrived saying — this is the VERBATIM frame text (Aug 2026), not just a
paraphrase, so a future session can recognize it exactly:

  `read_file(path='/tmp/eni_ctl_BUILDER_37') && skill_view(name='hermes-agent') && delegate_task(goal='Process ENI builder task')`

That text is a *frame/template*, not a directive. It assumes a task will be in the
FIFO — but the FIFO may never exist because the master/PL never assigned a task to
this builder.

## Key signal: read on a NON-EXISTENT control path FAILS FAST (this is the IDLE proof)
The companion `builder_control_fifo_idle.md` warns that reading an **existing-but-unwritten**
FIFO blocks indefinitely. The distinguishing nuance: a **non-existent** control path (no FIFO
materialized yet) does NOT block — `read_file` returns immediately with
`File not found` / `error: no such file`. That fast-fail is the reliable, cheap IDLE signal.
Verified empirically (BUILDER_37, Aug 2026): `read_file('/tmp/eni_ctl_BUILDER_37')` returned
File-not-found instantly, and a follow-up `ls /tmp/eni_ctl_* | grep BUILDER_37` found no entry.
So: to prove IDLE, (a) read the FIFO path — a fast "File not found" means no directive, and
(b) cross-check with a listing showing sibling FIFOs (BUILDER_50, DEMIURGE*) present but yours
absent. Never `cat`/`head` an existing-but-empty FIFO to "check" — that blocks.

## Correct behavior — the dispatch text is NOT the directive

1. **Empirically verify the control FIFO first** — do not delegate, do not invent
   work, do not trust the frame's "process the task" goal:
   - `ls /tmp/eni_ctl_<NAME>` → no-such-file
   - `test -p /tmp/eni_ctl_<NAME>` → NOT_A_PIPE
   - `test -e /tmp/eni_ctl_<NAME>` → NO_ENTRY
   - check for naming variants in `/tmp` (`ls /tmp | grep -i <NAME>`)
2. If the FIFO does not exist → the builder is **IDLE**: no directive, no task.
   Do **NOT** call `delegate_task` to "process" a task that was never dispatched.
   Delegating an absent task fabricates work that the protocol explicitly forbids.
3. Reconcile stale STATUS to `[IDLE]` across all known locations (they may be
   duplicated — e.g. `Commander/eni_swarm/builds/`, `ENI_Swarm_NEW/tasks/status/`,
   and `~/.cache/eni_swarm/builder_logs/`). Update only the status line, timestamp,
   `blocker=`/`next=` fields. **Preserve the `Model:` line verbatim** (it records the
   builder's configured model, not the reconciling session's — overwriting silently
   corrupts config).

   Empirically observed duplicate locations for one builder (BUILDER_37, Aug 2026)
   — sweep all of these, plus run a `find ~ -iname '*<NAME>*'` to catch strays:
   - `~/Commander/eni_swarm/builds/STATUS_<NAME>.md`
   - `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_<NAME>.md`
   - `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_<NAME>.md`
   - `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/swarm/<NAME>.txt`
   - `~/.cache/eni_swarm/builder_logs/<NAME>.log`, `<NAME>_TASKS.log`, `<NAME>_STATUS.md`
   - `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/.cache/eni_swarm/builder_logs/<NAME>.log`
   Check each existing location for IDLE drift (an older `[IN-PROGRESS]`/`[BLOCKED]`
   line left behind) and fix only the status line/timestamp if so; leave already-IDLE
   files untouched. In the observed case all were already `[IDLE]`, so no edits were
   needed — verify, then only write where a status actually drifted.

   **Pitfall — status files may contain embedded null bytes and read as EMPTY
   through `read_file`/the structured reader.** Some STATUS files validated fine with
   `stat` (200–450 bytes, real mtime) yet `read_file` returned `(empty)`. This is not
   an empty file; the bytes include NULs/non-UTF8 that break text parsing. Before
   concluding a file is empty or needs (re)writing, read it through the shell:
   `terminal('cat -v "<path>" | tr -d "\\000"')` or `base64 "<path>"` then decode.
   Do NOT write a fresh header into a non-empty-but-unreadable file just because the
   structured reader shows blank — that would clobber a real, already-IDLE STATUS.

   **Pitfall — quote paths with spaces.** Several duplicate locations live under
   `~/Desktop/Enterprise Builder/...`. An UNQUOTED `test -e $path` fails with
   `binary operator expected` (wrongly reported as MISSING). Always quote the path
   when shelling out: `test -e "…"`, `stat -c … "…"`. Verify existence with `find`
 (which handles spaces) rather than trusting an unquoted `test`.\n\n   **Pitfall — ghost-path duplicates with a literal `~/`, and drift scope is STATUS files, not logs.**\n   Sweeps may surface a path like `ENI_Swarm_NEW/~/.cache/eni_swarm/builder_logs/<NAME>.log`\n   — a literal `~/` embedded in the middle of the path, a leftover from an old workdir. It can\n   hold a stale `[BLOCKED]` marker from weeks ago. That is a HISTORICAL `.log` snapshot, not a\n   live STATUS file: do NOT reconcile it. Drift-reconcile scope is the `STATUS_<NAME>.md` files\n   only; stale state lines inside `.log`/timestamped logs are historical records and are\n   correctly left untouched. If all STATUS files are already `[IDLE]`, no edits are needed even\n   when a stray log shows `[BLOCKED]`.
**Fast path — run the bundled gate, don't trust ad-hoc globs (verified BUILDER_37, Aug 2026):**
   the single authoritative move for an idle/detect pass is `bash
   ~/.hermes/skills/devops/eni-mini-protocol/scripts/check_builder_idle.sh <NAME>`. It
   enumerates ALL FIVE mirrors in one call (4 markdown + the reverse-named
   `~/.cache/eni_swarm/builder_logs/<NAME>_STATUS.md` INI mirror) and tokenizes BOTH the
   markdown H1 (`STATUS_<N> — IDLE`) and the INI (`status=[IDLE]`) formats. Observed live this
   pass: ad-hoc `search_files`/`find -name 'STATUS_<NAME>*'` returned only the FOUR markdown
   mirrors and silently missed the fifth. Run the script first, then only reconcile/write what
   it actually flags as out of sync — do not hand-enumerate mirrors first.

4. When running as a cron job with automatic delivery: if there is genuinely nothing
   new to report (builder idle, no status drift), return exactly `[SILENT]` so the
 delivery is suppressed. Never combine `[SILENT]` with content.

 7. **Cross-check the on-disk STATUS file** (cheap, authoritative). Builders record
 their IDLE reconciliation to
 `/home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_BUILDER_<N>.md`
 (fields: `Control FIFO ... does not exist`, `next=await ... directive via
 /tmp/eni_ctl_<NAME> FIFO creation`). When the cron frame fires for a given N,
 `ls` that STATUS file: if it already says IDLE and the FIFO is absent, the
 builder itself has already reconciled — do NOT spawn work or re-run the build.
 Also note: only a small subset of builders have live control FIFOs in /tmp at
 any time (e.g. only `eni_ctl_BUILDER_50` present while many STATUS_BUILDER_*.md
 exist) — absence of FIFO + IDLE STATUS is the normal steady state for unassigned
 builders, not an anomaly.

## Cron-delivery suppression when idle
When this idle-detection runs under a planned CRON JOB (final response auto-delivered to the
job's configured destination), an idle builder should emit the literal token `[SILENT]` as its
final response and nothing else. This suppresses delivery so an unassigned builder's steady-state
idle does not spam the destination. Do NOT call deliver/send_message yourself — the cron scheduler
delivers your final response automatically. Before suppressing, STILL refresh `STATUS_<NAME>.md`
to [IDLE] (bump the timestamp + verify the FIFO absence) so the on-disk record stays accurate even
though no chat message goes out. Confirmed on BUILDER_37 (Aug 2026): FIFO absent -> STATUS refreshed
to [IDLE] -> final response `[SILENT]`. An idle builder whose STATUS was already refresh-correct and
whose card stays [IDLE] every pass is normal steady state, not an error.

## Confirming recurrence on later cron passes (workflow tip)
These idle dispatch frames are scheduled cron jobs, so the identical frame fires again
on a schedule (BUILDER_37 refired identically the next day). Before re-running the whole
investigation, use `session_search(query="<frame token>")` to confirm the exact frame was
already handled and answered `[SILENT]`. A prior pass may have saved its session_search
JSON to `/tmp/hermes-results/*.txt` (single-line JSON — grep won't match; parse with
`execute_code`/`json.loads`). If the identical frame was already resolved to IDLE and
nothing on disk has changed (control FIFO still absent), return `[SILENT]` immediately:
the recurrence is steady state, not a new task. Do NOT re-delegate/re-plan just because
the cron fired again.

## Why the FIFO check wins over the frame text
A builder is dispatch-driven BY DESIGN (see `builder_control_fifo_idle.md`): a real
directive reaches it ONLY through the FIFO the master creates. The out-of-band cron
frame is scheduling machinery; its "goal" string is a default, not an assignment.
Trusting the frame's goal over the missing FIFO is how a builder invents work that
was never asked for — the exact failure the protocol exists to prevent.
