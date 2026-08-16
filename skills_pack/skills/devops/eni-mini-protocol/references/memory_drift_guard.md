# Memory-write drift guard (issue #26045)

## Symptom
A `memory(action=add, target=memory, content=...)` (or `replace`) call returns:

    Refusing to write MEMORY.md: file on disk has content that wouldn't round-trip
    through the memory tool (likely added by the patch tool, a shell append, a manual
    edit, or a concurrent session). A snapshot was saved to
    /home/hunter/.hermes/memories/MEMORY.md.bak.<ts>. Resolve the drift first — either
    rewrite the file as a clean §-delimited list of entries, or move the extra content
    out — then retry. This guard exists to prevent silent data loss (issue #26045).

## Root cause
The memory tool maintains an internal model of each MEMORY.md. If the file was written
by anything other than the memory tool itself (patch / write_file / external editor / a
prior cycle's apply pass), the on-disk bytes no longer match the tool's model, so the
tool refuses to write — to avoid overwriting external edits (silent data loss).

## DO NOT
- Do NOT force a `patch` / `write_file` rewrite of MEMORY.md to "fix the round-trip".
  That (a) violates the ENI standing rule "never rewrite the proven core", and (b) the
  tool's internal model stays stale, so it will keep refusing future writes.
- Do NOT delete the `.bak` snapshots — they are the tool's safety net, not clutter.

## DO (correct handling)
1. Preserve the intended change in a NEW file (a proposal / `*_VERIFY.md` / candidate-add
   note). The knowledge is not lost and the proven core is untouched.
2. Re-sync the store to a round-trippable state. The sanctioned owner is the
   `hermes-memory-consolidation` skill — its recurring READ-ONLY re-consolidation cron
   (every 6h) re-strips volatile blocks and re-syncs the file. Run that skill now, or let
   the cron fire, THEN re-issue `memory(action=add)`.
3. Report the step as BLOCKED (never RED, never a failure): the hardware/USB is fine; the
   blocker is the tool guard protecting the proven core. State the exact next command.

## Worked example (ENI2, cycle 16)
- Resume re-verify GREEN; USB DEMIURGE1 mounted.
- Real-data cross-check vs live USB `gate_verdict.json` surfaced a NEW durable fact: a
  deploy-gate VETO layer (HIGH severity) sitting on top of the 4 scalar gates.
- Tried `memory(action=add, target=memory, cross_profile=true, content="...veto layer...")`.
- Tool REFUSED with issue #26045 — MEMORY.md had last been written by a cycle-14 patch
  apply, so the tool's model was stale vs disk.
- Handled correctly: wrote the veto fact to NEW file `ENI2_C16_REALDATA_VERIFY.md` (a
  candidate add), left MEMORY.md untouched, gated the add on the 6h consolidation cron
  re-sync, and reported the step BLOCKED. No proven core rewritten; knowledge preserved.
