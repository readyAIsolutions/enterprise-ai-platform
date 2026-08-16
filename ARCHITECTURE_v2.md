# ENI ENTERPRISE BUILDER — Cooperative Multi-Player Build Platform
## Architecture Master Plan — v3.0 "CO-OP"

**Owner:** LO / readyAIsolutions
**Date:** 2026-08-16
**Vision:** A single, portable, seller-ready "AI build operating system" where a whole
team works on the SAME codebase AT THE SAME TIME — each person's own PC and GPUs
pulling weight, each person's own agent + API keys, coordinated by a central server
with a live dashboard. Companies buy this to let their team + AI build software
cooperatively instead of one sluggish agent at a time.

---

## 0. The Core Insight (what makes it sell)

Current reality: one Hermes + one machine = one build lane. Want more lanes? Buy a
bigger box. That's the old model.

New model (this project): **a horizontal cooperative build floor.** N people across N
machines each run a "builder client" (their Hermes + their hardware + their API keys).
Thumb the same Git tree through a central **Coordination Server**. The server takes a
high-level goal, breaks it into atomic tasks, assigns each to the machine best suited,
merges results back against a shared workspace, and shows a live dashboard of the whole
team's machines, queues, throughput, and diffs. Companies buy seats: every seat = one
more machine contributing its GPUs/keys to the shared build.

---

## 1. Target Repo Layout (the cleaned platform)

We collapse the scattered dirs into ONE coherent product tree. Everything a company can
self-host is here, one `make install`, one `docker compose up`.

```
enterprise-ai-platform/
├── README.md               # the pitch + quickstart
├── LICENSE
├── Makefile
├── pyproject.toml          # single source of truth for the Python package
├── requirements.txt
├── docker-compose.yml
├── Dockerfile
├── config/
│   ├── config.yaml                # platform config (modules, ports, providers, secrets refs)
│   └── security_policies.yaml
├── platform_kernel.py         # the PlatformOS orchestrator (moves UP to root)
├── kernel/                    # EventBus, Registry, HealthChecker, lifecycle
├── modules/                   # 49 capability modules (self-validating)
├── foundation/                # prompt registry, policy, plugin framework, feature flags
├── orchestration/             # workflow composer, service mesh, event hub
├── tenancy/                   # multi-tenant manager (per-customer sandbox) -> monetization
├── integration/               # API gateway
├── dashboard/                 # Starlette admin :8421
├── multiplayer/               # <<<< NEW: the cooperative build system
│   ├── server/                #   coordinator: task broker + workspace merge + events
│   │   ├── server.py
│   │   ├── broker.py
│   │   ├── workspace_merge.py
│   │   ├── ledger.py
│   │   └── state.py
│   ├── client/                #   per-machine light client (bring own keys/hardware)
│   │   ├── client.py
│   │   ├── machine_profile.py
│   │   └── runner.py
│   ├── protocol.py            # JSON msg schemas (HELLO/WELCOME/TASK/WORK/ARTIFACT/HEARTBEAT)
│   ├── proxy.py               # WiFi/turbo protocol proxy reuse
│   └── dashboard_mp.py        # real-time co-op dashboard (optional starlette mount)
├── skills_pack/               # <<<< NEW: portable skills, LSPs, MCPs, plugins
│   ├── skills/       (mirror of ~/.hermes/skills, git-tracked)
│   ├── lsp/          (eni lsp_servers)
│   ├── mcp/          (eni mcp_servers: compression, knowledge_base)
│   ├── plugins/      (eni-omega-compress-paid)
│   └── seed_hermes.sh (one-cmd: copy skills_pack/ into a fresh ~/.hermes)
├── local_controller/        # <<<< the "one-prompt-program" brain
│   ├── controller.py
│   ├── planner.py            # goal -> task DAG -> bigger prompts
│   ├── private_vault.py      # local-only secret handling (NEVER to cloud)
│   └── build_engine.py       # turns one prompt into an entire program
├── data/                     # runtime (git-ignored)
├── logs/
├── scripts/                  # eni CLI, installers, verify
├── tests/
│   ├── unit/  integration/
└── docs/                     # architecture, selling guide, company pitch
```

---

## 2. Cooperative Multi-Player Build (the centerpiece)

### Roles
- **Coordination Server** (runs on one team box or a VPS): task broker, workspace merge
  authority, live ledger, dashboard API. Protocol: WebSocket + HTTP REST on one port.
- **Builder Clients** (each person's PC): register with machine profile (cpus, ram, gpu,
  models, api-key tags), claim tasks, run them via their local Hermes/agent, upload
  results. Each has its OWN keys — never confeskeys to server.
- **Shared Workspace**: the server keeps a git-backed canonical tree. Client checks out a
  task slice, runs, commits. Server MERGE orchestrator resolves conflicts, runs their
  module tests, and only integrates green results. This is how "everyone edits the same
  thing at once" is actually safe.

### Message flow (v1 protocol, JSON frames over WS)
```
CLIENT→SERVER  hello {client_name, capabilities{max_tasks, models, providers, gpu, cpus, ram, tags}, protocol_version}
SERVER→CLIENT  welcome {client_id, server_config}
SERVER→CLIENT  task {task_id, repo, spec, prompt, artifacts_expected, model_hint, key_ref_placeholder, timeout}
CLIENT→SERVER  work_start {task_id}
CLIENT→SERVER  work_log {task_id, chunk}            # streaming
CLIENT→SERVER  artifact {task_id, path, content_b64}|work_result {task_id, ok, artifacts[]}
CLIENT→SERVER  heartbeat {uptime, queue_len, running[]}
SERVER→CLIENT  ack / retry_once / requeue
```
State machine: QUEUED → ASSIGNED → RUNNING → COMPLETED | FAILED(retry once).

### Merge policy (workspace_merge.py)
- Fragmentation by **module/namespace** when possible → zero conflicts among parallel workers.
- Fallback: 3-way git merge; on conflict, queue a **resolver artifact** (a small dedicated
  merge task) rather than silently clobbering.
- Integration gate: each merged branch runs the module's test suite before promoting to main.
- All merges audited to a ledger (who, what files, when, tests-passed).

### Dashboard
- HTTP: `/health`, `/api/board` (clients, throughput, queue depth, live logs), `/api/submit`.
- Live WS stream pushed to any open dashboard.

---

## 3. The "One-Prompt-Program" Local Brains

`local_controller/` is the engine that makes the platform feel magic:
- **planner.py**: one natural-language goal → decomposes into build steps (tasks), each with
  its own refined prompt (feature spec, tests, docs). This is the "make bigger prompts and
  fully handle planned multi-step builds" capability.
- **private_vault.py**: secrets stay LOCAL in an OS-keyring-backed vault; placeholders like
  `{KEY:github}` go to the cloud model, only resolved server-side/local. This is the
  "handles privatized info" requirement you flagged.
- **build_provider.py**: a "one prompt → program": planner → workers → test → iterate loop.
- Fires into the multiplayer floor when >1 machine is online, else runs locally.

---

## 3. What's Useless / To Cut (candid)

- **Duplicate/divergent copies**: `Eni Builder/` dirs duplicated by `eni_compression/`,
  `compression_bridge/`, ENI_KB, ENI_Swarm_NEW — each a snapshot of the same ideas at
  different times. WE DO NOT carry multiple. The single source of truth becomes this repo.
- **Single-machine swarms** (`ENI_Swarm_NEW` ticket/mini model) are absorbed into
  `multiplayer/` (their protocol ideas live on; their duplicated code dies).
- **`carriers/*.png` + `.carrier` blobs**: build artifacts of compression, not source.
  Do NOT ship giant carrier dumps in a product repo; keep the compression *engine* only.
- **`.mypy_cache/.pytest_cache/.ruff_cache/__pycache__`**: exclude (already gitignored).
- **Test `test_gov.py`, `master prompt.md`, `.~lock*`** at repo root: delete or move to docs.
- Any module with zero tests that doesn't boot — decision gate in verify.

## 4. Money (how this sells)

1. **Self-hosted Enterprise license** — one repo, unlimited dev machines, `make install`.
2. **Licensing per cluster size** — free tier (1 builder), Pro (up to 10), Team (unlimited).
3. **Multi-tenancy** (`tenancy/`): run multiple customer projects on one server, each
   isolated tenant sandbox → managed service SaaS.
4. Optional **white-label dashboard** for builders (companies put their logo).
5. **One-prompt-program controller** as the documented "wow" demo they try in a 15-minute
   sales call.

## 5. Deliverables in THIS build pass
- [ ] Move everything into single clean `enterprise-ai-platform/` tree (symlink-safe).
- [ ] Working `multiplayer/` server + client + broker + merge + WS (end-to-end smoke test).
- [ ] `local_controller/` planner + private vault + build provider (one-prompt demo test).
- [ ] `skills_pack/` portable pack + `scripts/install_skils.sh` (copies to ~/.hermes).
- [ ] `Makefile install/up/test`, Docker compose single command.
- [ ] verify script + tests passing; STATUS file with PASS/FAIL + R list + UNVALIDATED.