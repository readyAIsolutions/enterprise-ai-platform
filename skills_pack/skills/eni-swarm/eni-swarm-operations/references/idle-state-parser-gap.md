# IDLE state mapped as DONE — monitor_fleet.py parser gap

**Scenario:** A builder writes `[IDLE]` or `# STATUS_BUILDER_N — IDLE` in its
STATUS file (meaning it checked in, found no work to do, and is waiting). The
monitor script maps this to `[DONE]`, not `[IDLE]`.

**Why it happens:** The fallback state-parsing path (lines ~47-57) has this
order:

1. Check for `BLOCKED` in the first non-empty line → `BLOCKED`
2. Check for `IN` + `PROGRESS` in the first non-empty line → `IN-PROGRESS`
3. Check for `[DONE]` bracket token → `DONE`
4. **Else → `DONE`**

IDLE hits step 4 and is silently classified as DONE.

**Impact:** A live IDLE builder is invisible in the ledger — it looks no
different from a builder that completed its work and shut down. You cannot tell
whether the fleet has ready-and-waiting capacity or is truly idle.

**Fix options:**

- **Quick fix (minimal):** Add `[IDLE]` tag to the STATUS file so the bracket
  token check catches it before the else-clause:
  ```python
  elif m2 and m2.group(1).upper() in ("DONE", "IDLE"):
  ```
- **Clean fix:** Add IDLE as a separate detected keyword in the two-pass
  pipeline (alongside IN-PROGRESS and BLOCKED), and emit `[IDLE]` in the
  ledger so the state is distinguishable from DONE.

**How to detect the gap after the fact:**

```bash
# Find STATUS files that say IDLE but the ledger says DONE
grep -rli 'IDLE' builds/STATUS_BUILDER_*.md 2>/dev/null | \
  while read f; do
    num=$(echo "$f" | grep -oP '\d+')
    grep "BUILDER_$num" HEARTBEAT_LEDGER.md
  done
```