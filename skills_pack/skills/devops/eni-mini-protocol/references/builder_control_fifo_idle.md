# Builder control-FIFO idle protocol

## Context
ENI swarm builders are dispatch-driven: a directive reaches a builder ONLY via its
control FIFO, conventionally `/tmp/eni_ctl_<BUILDER_NAME>` (e.g. `/tmp/eni_ctl_BUILDER_37`).
The master/PL creates the FIFO and writes the task into it. Builders do NOT poll for work
anywhere else.

## TOOLING PITFALL — a control FIFO is a named PIPE, not a regular file (verified BUILDER_37, Aug 2026)
A control file `/tmp/eni_ctl_<NAME>` is a FIFO (`prw-------`, zero size, mode `p`), NOT a
normal file. Consequences that WILL bite if you try to inspect it like a file:

  ## RECOGNITION FINGERPRINT — `cat`/`read_file` misbehave (verified BUILDER_37, Aug 2026)
  The single fastest tell: running `cat /tmp/eni_ctl_<NAME>`, `read_file(...)`, or `skill_view`
  (any pipe-reading tool) on a FIFO NEVER yields the task. The failure mode differs BY TOOL:
  - `cat` (shell) BLOCKS/HANGS until timeout (e.g. 180s `Command timed out`) — a FIFO open()
    for read blocks because there is no writer.
  - `read_file` returns an EMPTY `{"content": "", "file_size": 0}` with a misleading
    `"error": "File not found"` — NOT a hang. It looks like "no such file" but the inode exists.
  - A `find`/`ls` in the same shell shows the entry as `prw-------` (mode `p`, zero size).
  Because of the misleading "File not found," NEVER conclude "task file deleted/invalid" from a
  read failure alone. Confirm a FIFO's existence with `ls -la /tmp/eni_ctl_<NAME>` and the
  `[ -p "$FIFO" ]` test; `[ -p ]` true => directive channel present (proceed), `NO_ENTRY` => IDLE.ile` on it) when no
  writer/master has opened the other end BLOCKS INDEFINITELY — the command hangs until the
  tool's timeout fires (e.g. 180s), then returns nothing. Do NOT read a control FIFO with
  `cat`/`read_file`/`wc -c`. Diagnose with `stat -c '%n %s bytes %F' /tmp/eni_ctl_<NAME>` which
  returns INSTANTLY: a FIFO shows size 0 with file type `fifo`/mode `p`. Presence (stat OK) but
  size 0 + mode `p` = a live control pipe awaiting a directive; `stat` "No such file" = never
  created (IDLE candidate). Never let a `cat` hang teach you this again — stat first.
  ## VERIFYING A DELETED-FIFO vs NEVER-CREATED (empirical, verified BUILDER_37, Aug 2026)
When a cron pass finds `/tmp/eni_ctl_<NAME>` absent, confirm WHICH case you're in before
declaring IDLE — don't assume. A builder whose FIFO was DELETED (but once existed, e.g. an
older BUILDER_<N> superseded by a newer one) is indistinguishable from a never-created one
by a single stat. Verify empirically, then record exactly that evidence in the STATUS/log:
  - `[ -e /tmp/eni_ctl_<NAME> ]` → NO_ENTRY means the path is gone entirely.
  - `[ -p /tmp/eni_ctl_<NAME> ]` → NOT_A_PIPE confirms it is not hiding as some other type.
  - MOST CONVINCING: list the whole `ls /tmp/eni_ctl_*` namespace and note that SIBLING
    builders' FIFOs (`BUILDER_50`, `DEMIURGE_*`) are still present while only this one is
    absent → strong evidence of selective deletion, not a namespace-wide teardown.
Record this verbatim in the pass log, e.g. `[ -e ] NO_ENTRY, [ -p ] NOT_A_PIPE ... BUILDER_50
+ DEMIURGE* FIFOs present, none for BUILDER_37`. That evidence lets a future session
distinguish "this builder is genuinely idle" from "the whole control namespace vanished."
  - `read_file` / `cat` / `stat` on it → `read_file` reports "File not found" (it isn't a
    regular file); `cat <fifo>` BLOCKS for the full shell timeout (~180s) and then the
    command times out, because opening the read end of a FIFO waits for a writer to
    connect. Same for `head`/`tail`. Do NOT cat control FIFOs.
  - The directive is carried by the FIFO's **existence**, not its contents. On a crate there
    is just a named pipe sitting there with no data until the master writes; an EMPTY read is
    expected and is NOT the signal.
  - Correct verification is pure existence checks: `[ -e FILE ]` (NO_ENTRY if absent) and
    `[ -p FILE ]` (NOT_A_PIPE if it's not a pipe). Combine both — absence shows as
    `NO_ENTRY`/`NOT_A_PIPE`. Use `ls -la /tmp/eni_ctl_*` only to enumerate WHICH builders
    have FIFOs (the mode letter is `p`); never to read a FIFO's content.
  - When the pipe exists but you need to hand a directive to it, you WRITE to it (from the
    master side): `echo '<task>' > /tmp/eni_ctl_<NAME>`. A read-only consumer blocks until a
    writer opens it, and vice-versa.

## Concrete STATUS mirror locations (reconcile ALL that exist, empirically)
A builder's STATUS card is mirrored at multiple paths that must ALL be reconciled to
the same state + timestamp each pass (observed on BUILDER_37, Aug 2026).

Confirmed mirror GROWTH: Sat Aug 08 2026 had exactly THREE on-disk mirrors; by Sun Aug 09
2026 the set had grown to FIVE (verified empirically Sun Aug 09 18:07 MDT 2026 on
BUILDER_37): re-run the `find` every pass — the tally is NOT frozen — and reconcile
whichever of the following exist:
  1. `~/Commander/eni_swarm/builds/STATUS_BUILDER_<N>.md`   (markdown STATUS card)
  2. `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_BUILDER_<N>.md` (markdown)
  3. `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_BUILDER_<N>.md`              (markdown)
  4. `~/STATUS_BUILDER_<N>.md`                                                     (markdown)
  5. `~/.cache/eni_swarm/builder_logs/BUILDER_<N>_STATUS.md`  **DIFFERENT FORMAT** — a
     `[STATUS]` key-value log (lines `status=[IDLE]`, `verified=<ts>`, `blocker=`,
     `next=`, then the raw timestamp), NOT a markdown card. Do NOT write the markdown
     template into it; use the `[STATUS]` key-value shape instead.
Also note `~/.cache/eni_swarm/builder_logs/BUILDER_<N>.log` and `BUILDER_<N>_TASKS.log`
exist as append-only activity logs — leave them alone (they are not reconciliation targets).
When writing the markdown mirrors, include the Workdir + Model lines from the template;
the `[STATUS]` mirror captures model/workdir via its own fields. new paths are added over time). Four confirmed as of Sun Aug 09
2026, all four already refresh-correct IDLE:
  - /home/hunter/STATUS_BUILDER_37.md
  - /home/hunter/Commander/eni_swarm/builds/STATUS_BUILDER_37.md
  - /home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_BUILDER_37.md
  - /home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_BUILDER_37.md
(the last one under tasks/status/ was the NEW fourth mirror.) Located via
`find /home/hunter -maxdepth 4 -name 'STATUS_BUILDER_37*'` — all already refresh-correct IDLE):

EMPIRICAL RECONFIRMATION (Aug 09 2026 pass): the `-name 'STATUS_BUILDER_37*'` glob again
returned only FOUR markdown paths and silently MISSED the `.cache` reversed-name mirror.
The both-globs form
  `find ~ -maxdepth 6 \( -name 'STATUS_<NAME>*' -o -name '<NAME>_STATUS*' \)`
returned the full FIVE (4 markdown + `.cache/eni_swarm/builder_logs/BUILDER_37_STATUS.md`).
Also observed: the `tasks/status/STATUS_<NAME>.md` mirror can be stale at a DIFFERENT
timestamp than the other mirrors (e.g. one at 02:02Z while three sat at 02:31Z) — so don't
assume all mirrors are in sync; check each mirror's timestamp individually and reconcile
every one to the same current pass timestamp, or the PL/summary pass reading the HOME copy
can see a stale card.
  - /home/hunter/STATUS_BUILDER_37.md
  - /home/hunter/Commander/eni_swarm/builds/STATUS_BUILDER_37.md
  - /home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_BUILDER_37.md
Mirror count is UNSTABLE across passes (has ranged 3-5 over Aug 2026) — ALWAYS re-discover
with `find` each pass and reconcile whatever exists; never assume the set from a prior pass.
2026: (1) <Commander>/eni_swarm/builds/STATUS_BUILDER_37.md, (2) ~/STATUS_BUILDER_37.md,
(3) <Desktop/Enterprise Builder/ENI_Swarm_NEW>/STATUS_BUILDER_37.md,
(4) .../ENI_Swarm_NEW/tasks/status/STATUS_BUILDER_37.md,
(5) .cache/eni_swarm/builder_logs/BUILDER_37_STATUS.md. Mirrors (1)-(4) share the
'# STATUS — IDLE — <dow> <mon> <day> <HH:MM> <YYYY>' markdown header; mirror (5) uses a
DIFFERENT native `[STATUS]` ini form (status=, verified=, blocker=, next= + bare date
line). Reconcile (5) in its own form at the same timestamp — do NOT copy the markdown
Do NOT trust a fixed count; ALWAYS enumerate with `find ~ -maxdepth <N> -name 'STATUS_<NAME>*'`
(or `ls`) FIRST and reconcile exactly the paths that come back; never assume a fixed count
(four, three, or otherwise). If `find` returns only three, reconcile three.
  - PITFALL (observed Aug 08 2026): the `-name 'STATUS_<NAME>*'` glob DOES NOT match the
    `.cache` mirror because that file is named the OTHER way round: `BUILDER_37_STATUS.md`
    (`<NAME>_STATUS.md`), not `STATUS_<NAME>.md`. A `find -name 'STATUS_<NAME>*'` pass on
    BUILDER_37 returned only FOUR paths and silently missed the `.cache` one (5th mirror).
    The hardcoded known-list still carries it, so when `find` comes back one short of the
    documented count, check for the swapped-naming `<NAME>_STATUS.md` under
    `~/.cache/eni_swarm/builder_logs/` before trusting the count. Enumerate with BOTH globs
    (`-name 'STATUS_<NAME>*' -o -name '<NAME>_STATUS*'`) to catch it.
  - canonical:  `~/Commander/eni_swarm/builds/STATUS_<NAME>.md`
  - mirror:     `~/STATUS_<NAME>.md`
  - mirror:     `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_<NAME>.md`
  - mirror:     `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_<NAME>.md`
Always `write_file` ALL four (and scan for any other `STATUS_<NAME>.md` siblings via
`find`/`ls` before finishing). A stale mirror left behind can confuse the PL/summary pass
that reads the HOME copy. After writing both, `head -1` each to confirm same header landed.

### PITFALL: concurrent sibling passes write the SAME mirrors — warnings are expected, verify after
On multi-worker passes (BUILDER_<N> dispatchers, or a master/PL pass running at the same
time), the same STATUS_<NAME>.md paths are shared. `write_file` will happily succeed but can
return `_warning: "<path> was modified by sibling subagent '<ID>' but this agent never read
it. Read the file before writing to avoid overwriting the sibling's changes."` This does NOT
mean the write failed or a conflict is fatal — it is informational. Reconcile each mirror to
YOUR pass timestamp as normal, then run `head -1` on every path to confirm your header landed
last; if a sibling overwrote yours afterward, the idempotent IDLE content is identical anyway,
so a final timestamp mismatch after the whole group settles is acceptable. Do not chase the
warning, and do not re-read+rewrite defensively in a tight loop — just write all mirrors, then
verify all headers once.

## CRITICAL: an EXISTING-but-unwritten FIFO BLOCKS on read — never `cat` one to check for work
The control channels are named pipes (FIFOs), not regular files. Reading an EXISTING but
unwritten FIFO (`cat`, `head`, `tail`, and `read_file` on an existing-but-empty FIFO)
BLOCKS INDEFINITELY until a writer opens it — this has hung a terminal call the full 180s
timeout before aborting. They are write-only-by-master and only materialize once the master
assigns a task. To check for a directive, never read an existing FIFO.

## Distinguish ABSENT (idle, safe) vs PRESENT-but-empty (blocking, dangerous)
The block happens ONLY when the FIFO *exists* but no writer has opened it. When a builder is
truly idle the FIFO usually does NOT exist at all — and reading a NON-EXISTENT path is SAFE:
`read_file('/tmp/eni_ctl_<NAME>')` returns a clean "File not found" / `ls` gives no-such-file /
`[ -p ]` returns NOT_A_PIPE, none of which hang. So on a fresh idle pass you can safely probe
with `read_file` on the control path: a "File not found" result IS your empirical proof of
idle, not an error to fear. The thing to NEVER do is `cat` (or otherwise open-for-read) a FIFO
that current filesystem state says EXISTS — that is the hang.

When reconciling STATUS, record WHICH method proved absence (e.g. `read_file` File-not-found +
`[ -p ]` NOT_A_PIPE) for auditability, and note the pass timestamp.

## Reconciling STATUS mirrors when idle
A builder typically has MULTIPLE STATUS_<NAME>.md mirrors. Keep them ALL reconciled to the
same `[IDLE]` state and the same pass timestamp. Known locations were (Aug 2026):
  - `~/STATUS_BUILDER_37.md`
  - `~/Commander/eni_swarm/builds/STATUS_BUILDER_37.md`   (canonical — carries `Workdir:` + `Model:` lines)
  - `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_BUILDER_37.md`
  - `~/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_BUILDER_37.md`   (nested `tasks/status/` subdir)
  - mirror under `~/.cache/eni_swarm/builder_logs/` (e.g. `BUILDER_37_STATUS.md`)
To find them all, DO NOT trust the hardcoded list alone — mirrors get added. Run a recursive
glob from $HOME each pass. Use a BROAD glob on just the builder token, NOT `STATUS_BUILDER_37*`,
because the cache mirror's name is REVERSED (`BUILDER_37_STATUS.md`, not `STATUS_BUILDER_37.md`)
and a prefix match on `STATUS_BUILDER_37*` SILENTLY SKIPS it. Correct:
`find /home/hunter -iname "*BUILDER_37*" 2>/dev/null` (adjust token per builder). Diff this
against the known list every pass to catch newly-added mirrors (this is how the `tasks/status/`
nested mirror and the reversed cache mirror were caught).

### Mirror formats differ — reconcile each in ITS native format
Two distinct layouts exist and must NOT be conflated:
  - **Markdown-header mirrors** (the `STATUS_BUILDER_37.md` files): start with a
    `# STATUS_BUILDER_37 — IDLE — <ts>` H1 line followed by a prose `verified` sentence.
    Refresh the timestamp in BOTH the H1 line and the prose sentence.
  - **Cache mirror** `~/.cache/eni_swarm/builder_logs/BUILDER_37_STATUS.md`: uses an INI-like
    `[STATUS]` block with `status=[IDLE]` and a `verified=` key=value line (typically phrased
    `[ -p ] NO_PIPE, [ -e ] NO_ENTRY` rather than `read_file`/`ls` wording). Update its
    `verified=` line timestamp; keep `status=/blocker=/next=` and its native phrasing convention.
If you rewrite a cache-format mirror using the markdown-header format (or vice-versa) you break
the parser that consumes it — preserve each mirror's own layout. Keep `blocker=`/`next=` and any
`Model:`/config lines verbatim in every copy.

### Concurrent sibling reconciliation is NORMAL — don't panic on write warnings
Multiple swarm passes / sibling subagents can reconcile the SAME STATUS mirrors in parallel
(observed Aug 2026: every `write_file` to all five mirrors returned a
"modified by sibling subagent" warning, and the written content landed correctly anyway).
This is expected concurrency in the swarm, not an error and not a conflict to resolve.
  - If `write_file` emits a sibling-modification warning, the fix is not aborting or merging —
    the reconcile is idempotent (same `[IDLE]` state + same timestamp), so a parallel writer
    converges to the same bytes. Just proceed.
  - After writing all mirrors, re-verify the final HEAD of each (one quick loop
    `head -3 <each mirror>`) to confirm the state + timestamp landed. 
  - Do NOT treat sibling concurrency as a reason to skip reconciliation or to invent conflict
    resolution — the mirrors converge; only the timestamps race, and a later pass rewrites them.

## Recurring-cron delivery: suppress when already-IDLE
This pass runs as a scheduled cron job whose final output is auto-delivered. The cron
equivalent of "verbose zero-news" is owner fatigue, so:
  - On a pass where the control FIFO does not exist AND every STATUS mirror is ALREADY
    reconciled to `[IDLE]` with a current timestamp (a prior pass already wrote it this
    session/the same run cycle), do NOT re-report the IDLE state as a new finding. Emit the
    bare sentinel `[SILENT]` (nothing else) to suppress redundant delivery.
  - Only produce a real report if something CHANGED vs the last pass: FIFO appeared, a task
    is now assigned, a mirror was stale/missing and you fixed it, the timestamp drifted, or a
    new path was discovered. Otherwise `[SILENT]`.

### Same-cycle vs cross-cycle timestamp drift (decides report vs silent, ver. Aug 09 2026)
"Timestamp drifted" as a report trigger means a CROSS-CYCLE drift (a mirror's verified
timestamp / mtime comes from an older day or a prior distinct run cycle). That warrants a
re-write of all mirrors to the current pass timestamp + a real report.
Do NOT treat ordinary intra-cycle aging as drift: when you land inside the SAME run cycle as
the last pass (typically minutes later, all mirrors already mutually consistent, FIFO still
absent, broad glob returns no new mirror paths), the correct action is to make NO writes and
emit `[SILENT]`. Rewriting mirrors every rapid-fire cron tick just so the timestamp advances
Verify the drift type by comparing the mirrors'
`verified=`/`verified_at=` timestamps + disk mtimes against each other and
against the current date: all-matching-and-recent = same cycle = silent; one-or-more-old /
mixed/from-a-previous-day = cross-cycle = reconcile + report.

## PITFALL (verified BUILDER_37, Aug 12 2026): verifier EXIT 0 does NOT mean timestamp-fresh
`check_builder_idle.sh` exits 0 with `RESULT: all N mirrors present and all agree on IDLE ->
steady-state, nothing changed` based ONLY on the state-token (all mirrors `[IDLE]`). It does
NOT compare mirror mtimes against the current date. So a genuine cross-cycle gap — e.g. all 5
mirrors `[IDLE]` but dated the previous day (Aug 11 15:38) while today is Aug 12 — still yields
EXIT 0. You MUST additionally compare the mirror mtimes/epochs against the current date
(`date +%s` vs `stat -c %Y <mirror>`) to decide same-cycle (=silent `[SILENT]`) vs cross-cycle
(=reconcile all five to the current pass timestamp AND report). Letting EXIT 0 alone drive a bare
`[SILENT]` would skip the timestamp refresh and silently drop a day of drift. Recipe used successfully:
  - `date +%s` vs `stat -c %Y <any mirror>`; gap spanning a calendar-day/cycle boundary => cross-cycle.
  - Reconcile all 5 mirrors (4 markdown `STATUS_<NAME>.md` + `.cache` INI `status=[IDLE]`) to the
    SAME current timestamp, append to `<NAME>.log`, update HEARTBEAT_LEDGER, then re-run the verifier.
  - Never combine `[SILENT]` with content — it is all-or-nothing; the presence of any text
    means the report will be delivered, so reserve it for genuine state deltas.
