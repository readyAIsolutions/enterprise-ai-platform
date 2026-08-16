# Respawn / self-heal on a shared artifact (verify-don't-rebuild)

Use when a deliverable file (corpus, STATUS, generated doc, manifest) is claimed to
already exist and be COMPLETE — e.g. a respawned ENI, a fleet ping, or a "continue"
task. The discipline: VERIFY ON DISK, then APPEND a re-verify block to STATUS.
NEVER regenerate proven prose (churn + risks overwriting parallel/sequential sibling
work). This is the narrative/corpus counterpart to the program-build self-healing loop.

## The verification recipe (re-grep ground truth; never trust a STATUS block's count)

```
FILE=/home/hunter/Commander/eni_swarm/ENI_WRITING_corpus.md
STATUS=/home/hunter/Commander/eni_swarm/STATUS_ENI6.md

# 1. annotation blocks must match scene headers 1:1 (no orphan blocks)
grep -c 'TIPS DEMONSTRATED' "$FILE"      # annotation blocks
grep -c '^EXCERPT ' "$FILE"              # scene headers (caret-anchored)
grep -c 'ALL FIVE' "$FILE"               # ALL-FIVE single-scene anchors

# 2. structural integrity
grep -c 'TIP INDEX' "$FILE"               # index present
grep -c 'HOW TO USE THIS CORPUS' "$FILE"  # MUST be exactly 1 (no dup-header bug)
grep -c 'FORBIDDEN WORDS' "$FILE"         # pinned no-slop block present

# 3. forbidden-word honesty — the banned word must appear ONLY inside the banned
#    list, never in any prose body
grep -n 'devastating' "$FILE"             # expect hits only on banned-list lines

# 4. confirm a "missing" excerpt by its EXACT header string — DO NOT abbreviate
grep -n 'The Eighteen-Degree Vault' "$FILE"   # NOT 'Eighteen-Deg'

# 5. ALWAYS read the TAIL too. Parallel workers append a "PARALLEL WORKER
#    ADDITIONS" section AFTER the main body; a head-only read (e.g. lines 1-500 of
#    a 586-line file) misses appended excerpts living at the end.
tail -n 90 "$FILE"
```

## Decision rule
- annotation blocks >= 5  AND  every required tip/section covered  => COMPLETE.
  Write NO new prose. Freshen STATUS only (below).
- Below threshold or a required section missing => THEN build (ADD-only, never rewrite
  the existing correct parts).

## Freshening STATUS (append-only, preserve sibling work)
Append a new block (do NOT overwrite the file or prior blocks):
```
=====================================================================
>>> AUTHORITATIVE GROUND-TRUTH RE-VERIFY — ENI self-heal (<context>, <date>, <model>)
=====================================================================
[state: DONE]
file: <path>
excerpt_count: <N> annotated blocks  (re-grep, NOT a remembered count)
  grep '^EXCERPT ' = N   grep 'TIPS DEMONSTRATED' = N   grep 'ALL FIVE' = <A>
--- PASS/FAIL BOARD (real evidence) ---
  <each requirement> .... PASS/FAIL  (<grep evidence>)
WHAT ADDS R: <why this artifact earns its keep>
WHAT TO DROP / NEXT: <drop nothing if coherent; only-if-LO-asks extensions>
UNVALIDATED: <anything needing LO's eye, not concluded without him>
LAST ACTION: <verified on disk with live grep ... wrote NO new prose>
=====================================================================
```
Fleet ping == same verification + append, no prose.

## Pitfalls (the ones that actually bit)
- MIS-GREP ABBREVIATED HEADING: grepping "Eighteen-Deg Vault" returned 0 because the
  real header is "The Eighteen-Degree Vault". Always grep the EXACT token copied from
  the file, not an abbreviated recollection.
- PARTIAL READ MISSES TAIL: read_file paginates and truncates (e.g. 1-500 of 586). A
  head-only read does not show the worker-appended tail section. Read the tail / full
  structure before concluding a section is missing.
- STALE STATUS COUNTS: prior STATUS blocks may cite an OLD excerpt_count because
  parallel/sequential workers appended AFTER that block was written (count crept
  11 -> 16 -> 19 across blocks). Re-grep ground truth every respawn; never trust a
  block's self-declared count.
- DO NOT CHURN PROVEN PROSE: regenerating an already-complete artifact wastes tokens
  and risks overwriting sibling/parallel-worker output. Verify, then append-only.
- DUPLICATE HOW-TO-USE HEADER BUG: when appending, insert BETWEEN the last excerpt's
  annotation and the single existing footer divider — never add a second HOW TO USE
  header. Grep 'HOW TO USE THIS CORPUS' MUST stay = 1.
