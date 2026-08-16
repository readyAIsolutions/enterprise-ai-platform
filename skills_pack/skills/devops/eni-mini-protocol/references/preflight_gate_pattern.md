# Preflight Gate Pattern — Comprehensive readiness check before real build

**Origin**: ENI5 `preflight_win_build.sh` (proven in-session 2026-07-10, exit 2 on blocker)

## Purpose
Single script that is the **only** entry point for "is the real build ready?". It:
1. Re-runs the full self-test sweep (must stay GREEN)
2. Verifies all required modules/files are on disk
3. Probes USB / external data sources (confirms NOT the blocker)
4. Detects the toolchain (cross/native) present on this host
5. **Either** runs the exact build **or** prints the exact unblock command + exits 2

## Contract
- `bash preflight_gate.sh`        → full gate + build if READY
- `bash preflight_gate.sh --check` → gate only, never runs build (CI/smoke safe)

## Exit codes
- `0`  → GREEN: build ran and succeeded (or `--check` passed)
- `2`  → BLOCKED: toolchain absent, prints exact `sudo apt-get install ...` line
- `4`  → REGRESSION: self-test sweep has FAILURES (core broken, halt)
- `5`  → MODULE GAP: required source file missing
- `3`  → CD FAIL: cannot enter workdir

## Template structure
```bash
#!/usr/bin/env bash
# preflight_<target>.sh  --  single-shot readiness gate + EXACT next build
# ADDITIVE ONLY. Never rewrites the proven core modules or build script.

set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE" || exit 3

CHECK_ONLY=false
[ "${1:-}" = "--check" ] && CHECK_ONLY=true

# 1) Full self-test sweep (MUST stay GREEN)
if bash run_selftests.sh >/tmp/preflight_selftest.log 2>&1; then
  PASS=$(grep -c '^PASS |' /tmp/preflight_selftest.log)
  FAIL=$(grep -c '^FAIL |' /tmp/preflight_selftest.log)
  echo "[PASS] self-test sweep GREEN  PASS=$PASS FAIL=$FAIL"
else
  FAIL=$(grep -c '^FAIL |' /tmp/preflight_selftest.log)
  echo "[FAIL] self-test sweep has FAILURES ($FAIL) -- core regressed, halt."
  tail -15 /tmp/preflight_selftest.log
  exit 4
fi

# 2) Required modules on disk
MODS=(module1.cpp module2.cpp module3.cpp module4.cpp)
ALL=true
for m in "${MODS[@]}"; do
  if [ -s "$m" ]; then echo "[PASS] module on disk: $m"; else echo "[FAIL] MISSING module: $m"; ALL=false; fi
done
$ALL || { echo "Core module gap -- cannot build."; exit 5; }

# 3) USB / external data probe (confirm it is NOT the blocker)
if mount | grep -q 'TARGET_LABEL'; then
  echo "[PASS] TARGET_LABEL USB mounted"
else
  echo "[INFO] TARGET_LABEL USB NOT mounted -- but carries no toolchain, so non-blocking"
fi

# 4) Toolchain detect
TOOL_AVAIL=false
command -v "x86_64-w64-mingw32-g++" >/dev/null 2>&1 && TOOL_AVAIL=true
command -v cl >/dev/null 2>&1 && TOOL_AVAIL=true

# 5) Verdict + exact next command
if [ "$TOOL_AVAIL" = true ]; then
  echo ">>> READY: toolchain present. Running the EXACT next build. <<<"
  if [ "$CHECK_ONLY" = true ]; then
    echo "(--check set: would run 'bash next_build.sh')"
    exit 0
  fi
  bash next_build.sh
  exit $?
fi

echo ">>> BLOCKED: no toolchain on this host. <<<"
echo "USB is fine; the gap is purely the absent cross/native toolchain."
echo
echo "EXACT UNBLOCK (LO's terminal -- needs sudo + network):"
echo "    sudo apt-get install -y mingw-w64"
echo "then tell agent 'built' and run (NO sudo needed):"
echo "    cd $HERE && bash preflight_<target>.sh"
exit 2
```

## Key principles
- **Additive only**: never rewrites `next_build.sh` or core modules
- **Exact commands**: prints the literal sudo line LO must run, then the literal no-sudo agent line
- **`--check` mode**: safe for CI, cron, smoke; never produces artifacts
- **USB ≠ blocker**: explicitly probes and declares USB state; if USB has no toolchain, it's not the cause
- **Self-test first**: if the core regressed (FAIL > 0), halt with evidence — don't build on broken