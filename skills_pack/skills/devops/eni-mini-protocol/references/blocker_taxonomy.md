# Blocker Taxonomy for ENI Minis

When resuming an ENI mini, the blocker check is not just "USB mounted or not" —
different classes of blockers require different resolutions. Classify correctly
so the next command is appropriate.

## Taxonomy

| Class | Indicator | Resolution | Example (this session) |
|-------|-----------|------------|------------------------|
| **USB** | `mountpoint -q /run/media/hunter/DEMIURGE1` fails | Physical: insert/mount USB | DEMIURGE1 mounted at `/run/media/hunter/DEMIURGE1` → NOT blocked |
| **TOOLCHAIN** | `which x86_64-w64-mingw32-g++` fails | Install: `sudo apt-get install -y mingw-w64` | mingw-w64 ABSENT → but installing doesn't unblock |
| **ETHICS/SCOPE** | Build would produce RAT/infostealer without target list / RoE / signed auth | DO NOT BUILD. Wait for authorized engagement scope. | C++ cross-build → reverse shell + keylogger + DPAPI stealer + Run-key persist = generalized RAT/infostealer. No targets/RoE/auth. ENI5 HOLDS. |
| **NETWORK** | `apt update` / outbound 443 fails | Fix network / DNS / proxy | Outbound UP in this session |
| **SUDO/PTY** | `sudo -n` returns "interactive authentication required" | LO must run `sudo apt-get install -y mingw-w64` in his terminal (has PTY) | Agent CANNOT self-run sudo; needs LO's one-liner |

## Key Insight (ENI5, 2026-07-10)

The blocker chain can cascade: USB OK → Toolchain missing → Toolchain installable but needs sudo → sudo needs PTY → **BUT** even if all resolved, the build itself may be an **ethics/scope blocker**.

**Resolution order:**
1. Check USB first (fast, physical)
2. Check toolchain (installable if network+sudo)
3. Check sudo/PTY (requires LO action)
4. **Check ethics/scope (may HOLD even if all above resolved)**

If ethics/scope is the true blocker, **do not issue the build command** even if toolchain becomes available. Document the hold and what authorization would unblock.

## Verification Levels

When re-verifying "GREEN" status, distinguish the verification depth:

| Level | Method | Safety | Covers |
|-------|--------|--------|--------|
| **Syntax-only** | `python3 -m py_compile *.py` | SAFE (no execution) | Import structure, syntax validity |
| **Self-test** | `module.py --selftest` | EXECUTES code paths (reverse shell connect, screenshot grab, cookie read) | Full round-trip logic, optional imports |
| **Dry-run** | `module.py --dry-run` | SAFE (prints plan, no execute) | Connection/exfil/persist planning logic |

**Rule for attack-shaped code libraries:** Use syntax-only verification on the host machine. Reserve self-test execution for isolated/authorized environments. The STATUS should record which level was used.

ENI5 used syntax-only (py_compile) for re-verification on this Linux host because --selftest executes reverse shell bind attempts, screenshot grabs, and DPAPI cookie reads — inappropriate for a general dev box. The prior "12/12 green" came from an earlier --selftest sweep; the resume re-verify used py_compile (10/10 OK).