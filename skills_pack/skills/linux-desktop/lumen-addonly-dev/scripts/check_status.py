#!/usr/bin/env python3
"""Validate a LUMEN swarm STATUS_<NAME>.md against the required contract.

Required:
  * Line 1 (first non-empty line) is `[state: DONE|IN-PROGRESS|BLOCKED]`
  * Contains a PASS/FAIL board (both "PASS" and "FAIL" appear, case-insensitive)
  * Contains a "what adds R" section (case-insensitive)
  * Contains an "UNVALIDATED" section (case-insensitive)

Usage:
  python scripts/check_status.py STATUS_LM13.md
Exit 0 = contract met, 1 = missing a required element.
"""
import re
import sys
from pathlib import Path

STATE_RE = re.compile(r"^\[state:\s*(DONE|IN-PROGRESS|BLOCKED)\]$", re.IGNORECASE)


def check(path: str) -> bool:
    p = Path(path)
    if not p.exists():
        print(f"[FAIL] file not found: {path}")
        return False
    text = p.read_text(encoding="utf-8", errors="replace")
    ok = True

    # 1. first non-empty line is the state line
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not STATE_RE.match(first.strip()):
        print(f"[FAIL] line 1 must be '[state: DONE|IN-PROGRESS|BLOCKED]' "
              f"(got: {first!r})")
        ok = False
    else:
        print(f"[PASS] state line: {first.strip()}")

    # 2. PASS/FAIL board present
    low = text.lower()
    has_pass = "pass" in low
    has_fail = "fail" in low
    if has_pass and has_fail:
        print("[PASS] PASS/FAIL board markers present")
    else:
        print("[FAIL] PASS/FAIL board missing (need both 'PASS' and 'FAIL')")
        ok = False

    # 3. what adds R section
    if "what adds r" in low:
        print("[PASS] 'what adds R' section present")
    else:
        print("[FAIL] missing 'what adds R' section")
        ok = False

    # 4. UNVALIDATED section
    if "unvalidated" in low:
        print("[PASS] 'UNVALIDATED' section present")
    else:
        print("[FAIL] missing 'UNVALIDATED' section")
        ok = False

    print(f"result: {'PASS' if ok else 'FAIL'}")
    return ok


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/check_status.py STATUS_<NAME>.md")
        sys.exit(2)
    sys.exit(0 if check(sys.argv[1]) else 1)
