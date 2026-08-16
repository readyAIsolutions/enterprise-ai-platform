# Builder STATUS-mirror write method (PITFALL: sed mangling)

Applies to the mirror-reconcile steps in `builder_idle_pass_ops.md` (steps 5-6).
Observed live on BUILDER_37, Aug 08 2026.

## PITFALL — do NOT use `sed -i` to edit STATUS mirror headers
The mirror H1 and prose lines contain **multibyte em-dashes** (`—`, shown as
`M-bM-^@M-^T` in `cat -A`). A single-byte-matching `sed` pattern such as
`s/# STATUS_BUILDER_37 . IDLE . */replacement/` fails to consume the multibyte
bytes, so the replacement is appended *before* the untouched tail is written
back, producing a corrupted doubled header, e.g.:

```
# STATUS_BUILDER_37 — IDLE — Sat Aug 08 2026Sat Aug 08 23:31 2026
```

Case-sensitivity and `.`-matching across an M-bM-^@M-^T sequence is not reliable,
even when it looks correct in the shell. Do not spend turns debugging precision
regex against multibyte — switch method.

## RELIABLE METHOD — full-file rewrite via placeholder template
Write each mirror in full (not an in-place substitution). Refresh the timestamp
by string-substituting a single `__TS__` placeholder before writing:

```bash
TS=$(date '+%a %b %d %Y')
MD=$(cat <<'EOF'
# STATUS_BUILDER_37 — IDLE — __TS__
Control FIFO /tmp/eni_ctl_BUILDER_37 does not exist (re-verified empirically __TS__ via read_file File-not-found + [ -e ] NO_ENTRY + [ -p ] NOT_A_PIPE). Cron dispatch frame is a scheduling template, not a directive. No task assigned to BUILDER_37. IDLE — no directive, do not invent work.
blocker=none
next=await LO's directive via /tmp/eni_ctl_BUILDER_37 FIFO creation
Workdir: /home/hunter/Commander/eni_swarm/builds
EOF
)
for f in \
  "/home/hunter/Commander/eni_swarm/builds/STATUS_BUILDER_37.md" \
  "/home/hunter/STATUS_BUILDER_37.md" \
  "/home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/STATUS_BUILDER_37.md" \
  "/home/hunter/Desktop/Enterprise Builder/ENI_Swarm_NEW/tasks/status/STATUS_BUILDER_37.md"; do
  printf '%s\n' "${MD//__TS__/$TS}" > "$f"
done
```

Same pattern for the `.cache` INI mirror, but keep its INI `[STATUS]` block format
verbatim (do NOT write markdown into it).

## Verify after writing
One loop `head -3 <each mirror>` — all must show the SAME `[IDLE]` state AND the
SAME timestamp, byte-identical. A corrupted header (doubled ts / stray bytes) is
your signal that you slipped back into sed-on-multibyte; rewrite the full file.

## Placeholder-substitution note
`${VAR//__TS__/$TS}` (bash) replaces ALL `__TS__` occurrences in the template at
once, keeping every line's timestamp in sync with zero risk of partial matching.