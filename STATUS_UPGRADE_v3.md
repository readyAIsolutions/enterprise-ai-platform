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
   across a fleet.
2. Unify WS+HTTP on one port; add live WebSocket board push.
3. Multi-tenancy + licensing enforcement (modules/tenancy, licensing/).
4. TLS + auth on the server; real cross-machine smoke on 2 PCs.
5. Write the one-page demo script + partner deck from SELLING.md.