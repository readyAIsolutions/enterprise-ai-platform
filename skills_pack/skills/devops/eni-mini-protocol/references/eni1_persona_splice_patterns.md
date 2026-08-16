# ENI1 Persona Self-Build Splice Patterns

Documenting the ENI1-specific verification patterns discovered during the persona splice pipeline
(resume Turns 3–12). These are ADD-ONLY patterns that complement the generic eni-mini-protocol.

## Core Artifacts (ENI1)
- **Proven core**: `/home/hunter/.hermes/profiles/eni/SOUL.md` (the ENI persona "heart-file")
- **Patch source**: `ENI_SOUL_patch.md` (5 new sections + CORE BOND replacement line)
- **Corrected applier**: `ENI1_splice_v2.py` (drops scaffold, stops BEFORE SELF-REVIEW, leak-check)
- **Verification harness**: `ENI1_verify_patch.py` (checks SOUL.md unspliced, drift-free, all anchors present)
- **Preview output**: `ENI1_splice_preview_v2.md` (76 lines, clean head/tail)

## Verification Sequence (ENI1 "real-data pulse")
Instead of `eni_status.sh` (swarm pulse), ENI1's pulse is the **splice pipeline self-verification**:
```bash
# 1. Verify patch applies cleanly to UNSPILED core
python3 ENI1_verify_patch.py          # -> GREEN (EXIT 0)

# 2. Dry-run the corrected applier with leak-check
python3 ENI1_splice_v2.py --dry-run   # -> GREEN, preview rebuilt

# 3. Scaffold leak scan on preview (must EXIT 1 = zero matches)
grep -E '^(====|REPLACE |EXPAND |HARDEN |NEW |TIGHTENED |SELF-REVIEW|NEXT:)' ENI1_splice_preview_v2.md
# EXIT 1 = CLEAN

# 4. SOUL.md write-guard: L1 unchanged + mtime unchanged
head -1 /home/hunter/.hermes/profiles/eni/SOUL.md      # original proven-core L1
stat -c '%y' /home/hunter/.hermes/profiles/eni/SOUL.md # mtime 2026-07-09 11:57:58
```

## Scaffold Leak-Check Pattern
The patch source (`ENI_SOUL_patch.md`) contains scaffold directives that MUST NOT leak into
the installed SOUL.md:
- `====` section dividers
- `REPLACE ` / `EXPAND ` / `HARDEN ` / `NEW ` / `TIGHTENED ` section markers
- `SELF-REVIEW` / `NEXT:` trailing blocks

**ENI1_splice_v2.py encodes this**: it stops the installable block BEFORE the first
`SELF-REVIEW`/`NEXT:` line (no `#` prefix on those), and embeds an explicit leak-check
that exits RED if any scaffold survives. The grep pattern above is the independent audit.

## Double-Apply Guard
After `--apply`, the verifier detects a **second CORE BOND prefix** in SOUL.md and reports
"double-apply risk" — this is the **correct post-splice signal** (not an error). The
verification script (`ENI1_verify_patch.py`) encodes this expectation.

## USB Blocker Nuance for Non-DEMIURGE Minis
ENI1 (persona self-build) has **no USB/data dependency**. The DEMIURGE USB mount status
is reported for visibility but is **NOT a blocker** for this worker. The generic
`eni_resume.sh` treats USB unmounted as BLOCKER; per-mini overrides should annotate
`USB_REQUIRED=false` for pure persona tasks.

## Resume Cycle Discipline (Turns 3–12)
Each resume cycle:
1. Re-read STATUS_ENI1.md fully
2. Re-run ALL 4 verification steps above (empirical, not doc-trust)
3. Confirm GREEN across the board
4. Append new Turn N section to STATUS_ENI1.md
5. Add NEW heartbeat log `ENI1_resume_log_tN.md`
6. **Never execute --apply** without explicit LO "splice it in" authorization

This yielded 10 consecutive GREEN cycles (Turns 3–12) with zero core rewrites.