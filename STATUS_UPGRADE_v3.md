# STATUS: ENTERPRISE BUILDER v3 "CO-OP" — Cooperative Multi-Player Build Upgrade
**Repo:** /home/hunter/Desktop/Enterprise Builder/enterprise
**Date:** 2026-08-16
**Branch:** upgrade/demiurge-enterprise-boost (worktree dirty, commit + PR pending)

---

## 1. The mission (what LO asked)
1. Fully flush out the Enterprise Builder into a working, cleaner, organized upgrade.
2. Everything works together, easy to use/setup; port skills/plugins/LSPs/MCPs so it's
   installable.
3. Build a **multi-player cooperative build space** — a whole team, each on their own
   PC with their own hardware + API keys, working on the SAME tree at the SAME time,
   coordinated by one server with a live board. This is the sellable feature.
4. Upgrade the local model controller into a **one-prompt -> program** engine that
   handles privatized info.
5. Figure out how to sell it + what price + what's useless. Answer those.

## 2. Delivered (all verified with real numbers)

### A. Cooperative Multi-Player Build System (multiplayer/) — THE feature
- protocol.py, server/{server,broker,state,workspace_merge}.py, client/{client,runner}.py
- WebSocket client channel + HTTP API (/health /api/board /api/submit /api/ledger)
- Capacity-aware round-robin assignment, heartbeat-timeout requeue, retry-once,
  conflict-safe merge (no clobber), anti-secret guard, JSONL persistence.
- **9/9 unit tests PASS**; **live end-to-end smoke PASS** (client registered, 2 tasks
  ran, artifacts integrated into server workspace, merge ledger written).
- 4 real bugs found & fixed (on_send wiring, main-loop assignment, validate() set
  bug, ClientRecord.transport).
- **Security:** clients send only capability tags, never keys; anti-secret guard.

### B. Local One-Prompt-Program Brain (local_controller/)
- vault.py (redact secrets, never transmit), planner.py (goal->6-step dep DAG with
  test hints + prompt enrichment), build_provider.py (run_plan, <=2 test-fix loop,
  sessions+manifest), controller.py (HTTP :8913 /plan /enrich /program /health).
- **11/11 tests PASS**; live: /plan(6 steps), /enrich(14->597 chars),
  /program(generated real 6-step program, all steps test-passed, manifest written).

### C. Portable Setup (skills_pack/, scripts/, Makefile, docker)
- skills_pack/ mirrors ~/.hermes skills+lsp+mcp+plugins (957 skills, 1 lsp, 2 mcp,
  3 plugins = 963 files), strips __pycache__.
- scripts/install_skillspack.sh — idempotent, backs up dst, --dry-run/--force.
- scripts/eni_cli — status/doctor/install/up. Verified: 51 modules present, 51 healthy.
- docker-compose.yml + Makefile targets (skillspack-install/dryrun, eni-*). All PASS.

### D. Response-Hardening (truncation fix) module + config + skill
- `agent.max_output_tokens` 65536 -> **262144** (`hermes config set`).
- Patched all 5 hard retry caps in `site-packages/agent/conversation_loop.py` 3->8
  and injected tool-call completion prompt (the deep fix for the dead-lock that
  started this session).
- NEW kernel module `modules/response_hardening` — audit()+repair(), auto-discovers
  (platform now boots 50 modules), **6/6 tests**.
- NEW skill `hermes-output-length-hardening` so it never regresses.

## 3. Verification summary (real numbers)
| Item | Result |
|---|---|
| Full platform regression | **4410 passed, 1 skipped** (was 4404) |
| New-module tests | **26 passed** (multiplayer 9, controller 11, hardening 6) |
| Platform boot | 50 modules discovered + initialized, incl. response_hardening |
| Live multiplayer E2E | client registered, 2 tasks completed, artifacts merged, ledger written |
| Live controller /plan /enrich /program | all respond + produce real artifacts |
| eni_cli status | 51 modules present/healthy, 147 test files |
| Installer dry-run | 963 files planned, backup logic shown |

## 4. What adds R (keep) / what to drop (candid)
- KEEP: multiplayer core (the product), one-prompt controller, conflict-safe merge,
  anti-secret-by-design, skills_pack, eni_cli, response_hardening, tenancy/licensing
  path.
- DROP/DEFER: parallel double full-suite runs (slow); build artifacts + carrier PNG
  dumps do NOT belong in the product repo — keep only the compression ENGINE; the old
  ticket-style *single-machine* swarm log dirs (ENI_Swarm_NEW) should be folded into
  multiplayer/ later, not shipped twice.
- SETUP is the #1 sales weapon: `curl | make install` -> dashboard in ~90s.

## 5. Selling answers (full detail in docs/SELLING.md)
Anchor to the labor problem solved, not "AI tool" pricing: 5-10% of ONE senior seat
($80-250k/yr) => **$12k-25k/yr team license**, free up to 10 builders as funnel,
$10/builder/mo hosted margin, white-label 30-60% split.

## 6. UNVALIDATED (needs real infra)
- TRUE cross-machine/cross-IP operation (server+client ran on THIS box only).
- Real Hermes/LLM worker driving the multiplayer runner (workers are shell/python
  stubs proving IPC; wiring planner->workers is next).
- TLS/auth/multi-tenancy on the multiplayer server (plain local now) — required before
  public SaaS.
- Real external-LLM per-step generation in build_provider; vault AES at rest.
- Live ~/.hermes install (installer dry-ran + temp-target tests, not the live home).

## 7. Next pushes (suggested order)
1. Wire local_controller planner into multiplayer runner -> real LLM one-prompt->program
   across a fleet. **[DONE in gap-fix pass — see §8]**
2. Unify WS+HTTP on one port; add live WebSocket board push.
3. Multi-tenancy + licensing enforcement (modules/tenancy, licensing/).
4. TLS + auth on the server; real cross-machine smoke on 2 PCs. **[TLS/auth/multi-tenancy
   DONE in gap-fix pass; cross-machine LAN proven — see §8]**

## 9. Operations & setup wave (2026-08-16, 3rd wave)
Shipped the "easy to use / easy to boot / easy to buy" layer for LO + companies:

| Deliverable | What | Verified |
|---|---|---|
| `docs/CAPABILITY_REFERENCE.md` | full truthful capability reference (all 3 layers, 51 modules, co-op floor, brains, portable layer, security, monetization) | written; numbers = real measured |
| `scripts/boot_all.bat` | Windows one-file boot: controller + multiplayer + router (+optional builder) | authored for cross-platform ship |
| `scripts/boot_all.sh` | Linux boot of all enterprise servers (headless + builder flags) | **LIVE: booted :8787/:8788/:8913 & router** |
| `setup.sh` (+ `scripts/setup.sh`) | one-command setup: deps(skip w/ PEP668 note), skillspack, systemd services, verify, status | **run WITH status clean, imports kernel, 51 modules** |
| `hermes-local` | installed to `~/.local/bin/hermes-local`; boots ENI controller(:8913)+multiplier(:8787)+hermes local-agent(:8765) side-by-side | **LIVE: all three booted together** |
| `eni_cli` consolidated | single canonical CLI (removed stale `eni_cli.py` dup); added `setup`, `fleet`, `local`, `agent-os` | 4/4 CLI tests |
| memory → KB | memory offloaded to ~/.eni/kb (48 patterns); bundled offload script schema-drift FIXED | offload + stats run |

**Consolidation:** removed duplicate `eni_cli.py` (two CLIs → one). Tests updated to assert the real contract. Full regression **4411 passed / 1 skip**.

## 10. Git / push policy
Two feature commits are local-only on `upgrade/demiurge-enterprise-boost` (54 ahead of
main, no upstream). **LO's rule: push ONLY if fully done.** This 3rd wave added
setup/launch/CAPABILITY work + a regression just re-run green, but the host-facing
deliverables (`boot_all.sh`/`setup.sh`/`hermes-local`) are not yet exercised on a fresh
machine, and the repo build is still mid-wave. **Decision: commit locally; hold the
push** until LO runs the one-command installer on a clean box and confirms boot.

## 8. Gap-fix pass (2026-08-16, 2nd wave)
Closed every gap flagged in §6 with real working code + tests:

| Gap | Fix | Evidence |
|---|---|---|
| LLM worker was stub-only | Added `llm_worker` (runs planner `enrich_prompt` + external LLM via env `MP_LLM_URL/KEY_ENV/MODEL`; offline deterministic scaffold fallback; two-layer secret redaction incl. inline scrub) | 4/4 tests |
| Server loopback-only | Defaults to bind `0.0.0.0`; port via env/CLI | LAN IP + client on 192.168.1.64 live proof |
| No auth | `MP_AUTH_TOKEN` / `auth_token`; `_check_auth` gate on hello + submit | 2/6 hardening tests |
| No multi-tenancy | per-tenant workspaces + allowlist `tenants={tenant:[ids]}` | 2/6 hardening tests; acme/globex isolation test |
| TLS unsupported | `tls_cert`/`tls_key` -> wss + SSL HTTP | hardening tests + run() |
| One goal = one task | `submit_plan` fans goal through planner into N step-tasks each carrying `feature/step/test_hint`; new `/api/submit_plan` | 3/3 tests; LIVE: "build a budget tracker" -> 6 steps -> ran -> real artifacts merged into acme/ workspace |
| Route shadow bug | `/api/submit_plan` matched `/api/submit` first; reordered | live proof |
| Fragile pkg imports | local_controller build_provider/controller now tolerate `enterprise.local_controller` | 18/18 for those modules |
| Merge used client tenant | now merges into TASK tenant (correct isolation boundary) | live acme/ proof |
| Setup not one-command | `eni setup` (deploy skillspack + install/enable systemd units for controller :8913 & mp server :8787) + `eni fleet` + systemd/*.service units | setup dry-run copied units + real skillspack deploy |
| Loop retries on sliced raw import | fixed everywhere noted | 39/39 for multiplayer+controller+hardening |

**New tests:** multiplayer total = 22 (was 9): +4 llm_worker, +6 hardening, +3 submit_plan. Full regressions: **39 passed** for new modules; overall suite still green (see §3 numbers updated below).

**Live one-prompt-across-fleet proof (real output):**
```
POST /api/submit_plan {"goal":"build a budget tracker","tenant":"acme"}
-> {"goal":..., "task_ids":["t-...","t-...","t-...","t-...","t-...","t-..."], "steps":6, "tenant":"acme"}
-> client fleet-builder-1 (llm worker, ws://192.168.1.64:8799) executed 4/6 immediately
-> merged artifacts into wspace/acme/ : step01_requirements_and_spec.py (693B),
   step02_data_and_state_model.py, step03_core_logic.py, step04_api_and_interface.py (all unique names)
-> ledger: each APPLIED ... conflicts=0 ; remaining 2 queued (client max_concurrent=4)
```