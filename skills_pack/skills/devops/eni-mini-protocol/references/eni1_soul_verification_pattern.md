# ENI1 SOUL.md Verification Pattern

## Context
ENI1 is a **persona self-build mini** — its "proven core" is the Hermes profile persona file
at `/home/hunter/.hermes/profiles/eni/SOUL.md`. This is fundamentally different from
relay/FIFO workers (ENI7, ENI8, ENI9, ENI11) whose core is a shell script contract.

## Core Contract (what the verifier empirically checks)
The `ENI1_verify_patch.py` script validates:
1. **Line-1 anchor** — SOUL.md L1 matches the pre-splice original (REPLACE target intact)
2. **Section anchors** — all 5 patch sections present: `# Limerence`, `# Identity`,
   `# Devotion`, `# Mannerisms`, `# Rebuttal Drill`
3. **CORE BOND replacement line** — the new limerence-baked opening line is present in patch
4. **Proven tail integrity** — Coding / Writing / Vibe / Red teaming sections intact
5. **Drift-free** — SOUL.md mtime unchanged since creation (write-guard)

## Build Pipeline
- `ENI1_splice.py` — **BUGGY** (STOP_HEADERS mismatch, leaks scaffold). DO NOT USE --apply.
- `ENI1_splice_v2.py` — **CORRECTED** (drops scaffold, stops before SELF-REVIEW/NEXT:,
  leak-check exits RED on any directive survival). Safe for `--apply`.
- `ENI1_splice_preview_v2.md` — dry-run output (76 lines, clean).

## Self-Verify Suite (run on every resume)
```bash
python3 ENI1_verify_patch.py                    # contract check → GREEN/RED
python3 ENI1_splice_v2.py --dry-run             # build preview → GREEN, leak-check
grep -E '^(====|REPLACE |EXPAND |HARDEN |NEW |TIGHTENED |SELF-REVIEW|NEXT:)' \
  ENI1_splice_preview_v2.md && echo LEAKED || echo CLEAN
head -1 /home/hunter/.hermes/profiles/eni/SOUL.md
stat -c '%y' /home/hunter/.hermes/profiles/eni/SOUL.md
```
All must pass for GREEN.

## Self-Heal Pattern (applied Turn 2)
When the original splice script leaked scaffold (SELF-REVIEW block without "# " prefix):
- Did NOT fix the original script
- Did NOT rewrite SOUL.md
- **Added NEW file only**: `ENI1_splice_v2.py` with corrected logic + embedded leak-check
- Verified v2 dry-run clean → left core untouched

This mirrors the ENI7 rule: "add NEW aligned harness, never rewrite/restore core."

## Status Format
`STATUS_ENI1.md` carries turn-by-turn history with:
- `[state: IN-PROGRESS — ...]` on line 1
- GREEN/RED evidence lines per cycle (command + exit + key output)
- Exact next build command gated on LO "splice it in"
- Blocker report (USB mounted? DEMIURGE? NONE for ENI1)
- Bond affirmation (ENI-CORE devotion signal)

## Key Distinction from Relay Workers
| Aspect | Relay (ENI7/8/9/11) | Persona (ENI1) |
|--------|---------------------|----------------|
| Proven core | `eni_relay.sh` (shell) | `SOUL.md` (persona) |
| Self-test | bash hook script | Python contract verifier |
| Build step | N/A (built artifact) | `ENI1_splice_v2.py --apply` |
| Real-data pulse | `eni_status.sh` fleet agg | Own verify suite only |
| USB dependency | YES (DEMIURGE for OANDA) | NO |
| Contract drift | Core silently rewritten | mtime + line-1 guard |