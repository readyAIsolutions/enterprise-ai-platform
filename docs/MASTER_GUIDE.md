# THE ENI ENTERPRISE PLATFORM — THE WHOLE DAMN THING
## A complete, plain-English, nothing-skipped guide to what it is, how it works,
## how to set it up, and how to use it.

**Version of this document:** 2026-08-16
**Repo:** `/home/hunter/Desktop/Enterprise Builder/enterprise`
**Who this is for:** anyone who has never seen this codebase. No jargon left
unexplained. Read top to bottom, or jump to the chapter you need.

---

# PART 1 — WHAT THIS IS (the 30-second version)

ENI Enterprise is a piece of software that lets you and a whole team tell a
computer "build me X" in plain English, and then the computer splits that one
request into many small jobs, hands those jobs out to multiple machines working
in parallel, checks the results, and merges them back into one finished,
tested program.

If you already have an AI assistant like ChatGPT, imagine this instead: instead
of ONE assistant typing slowly on ONE machine, you get a *team* of assistants —
one per computer — all typing at once on the same job, with one "boss" (the
server) coordinating them so they don't step on each other.

The whole thing is built as ~50 separate "modules" (like plug-in apps), each
doing one specific job. A central "kernel" starts them up, checks they're alive,
and runs them. Because each module is separate, you can add new abilities by
just dropping in a new module — it finds itself automatically.

---

# PART 2 — THE ONE-SENTENCE VIEW OF HOW IT'S PUT TOGETHER

```
  You type:  "build me a budget tracker app"

       |
       v
  [LOCAL BRAINS]  (one computer, port 8913)
       |  splits your goal into 6 smaller steps,
       |  each with a clear instruction + a test to check it
       v
  [COORDINATION SERVER]  (the "boss", ports 8787 + 8788)
       |  puts the 6 steps in a queue, then assigns each
       |  step to whichever machine is least busy
       v
  [BUILDER CLIENTS]  (one per computer on your team)
       |  each picks up a step, writes real code for it,
       |  runs the test, sends the finished file + result back
       v
  [MERGE + WORKSPACE]  (the shared folder where all work lands)
       |  the server checks the finished files, refuses to
       |  overwrite anything that conflicts, and logs it all
       v
  A finished, tested program, built by many machines at once.
```

That's the whole idea in one picture. Everything below is just "what each box
really is" and "how to run it."

---

# PART 3 — WHAT'S IN THE FOLDER (the map)

Everything lives under `/home/hunter/Desktop/Enterprise Builder/enterprise/`.

| Folder / file | What it is |
|---|---|
| `platform_kernel.py` | The "brain"/kernel. Starts, checks, and runs all modules. |
| `modules/` | The ~50 plug-in capability modules (one folder each). |
| `kernel/` | Extra core pieces: orchestration, registry, audit log, quality gates. |
| `foundation/` | Policy rules, evaluation, and the prompt registry. |
| `orchestration/` | Workflow composer, plug-in framework, feature flags. |
| `integration/` | API gateway, event hub, service mesh. |
| `monitoring/` | Metrics, health dashboard, alerts, log aggregation. |
| `tenancy/` | Lets one server run multiple isolated customer "tenants". |
| `multiplayer/` | **The main selling feature** — the team of builder machines. |
| `local_controller/` | The "one prompt → program" brain (planner + secret vault). |
| `skills_pack/` | A copy of your whole Hermes agent's skills/LSP/MCP/plugins. |
| `scripts/` | The command-line tools you actually use day-to-day (`eni_cli`,
  `boot_all`, `setup.sh`, `hermes-local`, etc.). |
| `systemd/` | Startup service definitions (controller + multiplayer server). |
| `dashboard/` | A web admin screen (port 8421). |
| `docker/` | Ready-made Docker packaging. |
| `docs/` | All the explanatory documents. |
| `config/` + `config.yaml` | Settings for the whole platform. |
| `tests/` | Automated tests. |
| `setup.sh` (one level up) | One-command installer. |

The parent folder also has:
| Folder | What it is |
|---|---|
| `_legacy/` | **Archived** old projects (no longer used). Kept for reference only. |
| `config/` `data/` `logs/` | Runtime settings / stored data / log files. |

---

# PART 4 — THE PORTS (which number talks to which thing)

Think of ports as numbered doors on your computer. When a program "listens" on a
port, it means "send stuff to me through this door." Here is every door this
platform uses:

| Port | What's behind it |
|---|---|
| **8421** | The **web dashboard** — a screen you open in a browser to see how
  the whole platform is running (which modules are up, scores, events). |
| **8787** | The **multiplayer coordination server** (WebSocket) — where builder
  clients connect and receive work. |
| **8788** | The **multiplayer HTTP API** — where you (or the dashboard) submit
  goals and read the live board over a web request. |
| **8913** | The **local brains** — the "one prompt → program" planner server. |
| **9090** | **Prometheus** metrics (a monitoring data exporter). |
| **8920** | The **free-model router** — points your model calls at cheap/free AI
  models to save money. |
| **8922** | The **swarm turbocharger** — tunes the network so many agents don't
  crash the WiFi. |
| **9120** | The **agent server**. |
| **8420** | The **swarm bridge**. |
| **8080** | A local/free **model endpoint** (part of model routing). |

You don't need to memorize these — the tools (`eni_cli`, `hermes-local`) start the
right ones for you. But if something "isn't listening," checking these ports is
how you find out.

---

# PART 5 — THE KERNEL (the brain that runs everything)

## 5.1 The idea
The kernel is a single program (`platform_kernel.py`) that acts like an
operating system for all the modules. It owns:
- **Lifecycle** — every module goes through the same stages: *not started →
  initializing → discovering → configuring → starting → running*. If a module
  crashes, the kernel can pause it and restart it.
- **Discovery** — when you add a new module folder, the kernel finds it
  automatically by scanning `modules/*/__init__.py`. You don't edit the kernel
  to add a feature; you just drop in a folder.
- **Health** — every so often the kernel asks each module "are you alive?"
  (`health_check`). It tracks which are healthy, which are sick, and which are
  down.
- **Events** — modules "talk" to each other by publishing **events** (messages)
  on a shared bus (`EventBus`). One module can say "a task was created" and any
  other module that cares gets a copy.

## 5.2 The module contract (every module agrees to these 3 things)
Every module is a Python class that MUST provide:
- `initialize()` — set yourself up and get ready.
- `health_check()` — report if you're healthy or not.
- `shutdown()` — tidy up before stopping.

And each module is marked with a special label: `@module(name="something")`.
That label is how the kernel knows it exists.

## 5.3 The lifecycle state machine (the official "stages")
A module can be in exactly one of these states, and can only move in legal ways:
```
INITIALIZING -> DISCOVERING -> CONFIGURING -> STARTING -> RUNNING
                                                          |
                                     (crash/timeout)     v
                                          RECOVERING <-> PAUSED
```
- `RUNNING` = healthy and working.
- `PAUSED` = temporarily stopped (you can resume it without a full restart).
- `RECOVERING` = it broke; the kernel is trying to bring it back.

## 5.4 What's inside `kernel/` (the extra core pieces)
- `kernel.py` — the core kernel context and gate helpers.
- `orchestrator.py` — the multi-agent orchestrator: decides the order to run
  things, and resolves conflicts using *evidence* (proof), not guesses.
- `registry.py` — a declarative list of the core modules in the order they must
  start (dependencies).
- `audit.py` — an **audit chain**: a tamper-evident log (uses SQLite) so you can
  prove, after the fact, exactly what happened and nobody secretly changed it.
- `quality_gate.py` — checks the platform against **17 quality gates** before
  release (e.g. "do all modules pass their tests?").

---

# PART 6 — THE 50 MODULES (each one explained)

The kernel "discovers" these automatically. They're grouped below by what they
do. Each entry says: **name — what it does**.

### Agent & team mechanisms (14)
| Module | What it does |
|---|---|
| `agent_core` | The core agent brain (a re-implementation of the Claude Code agent). |
| `agent_infra` | The low-level machinery the agent runs on. |
| `agent_tools` | The toolbox the agent can use (read files, run commands, etc.). |
| `agent_os` | Reads and scores trending news from free feeds (no API key needed). |
| `agent_coordination` | Lets many agents work together: schedules, shares knowledge,
  resolves disagreements, survives machines failing. |
| `agent_graph` | Runs agents in a flowchart-like sequence (a "graph" of steps). |
| `agent_catalog` | A catalog of **432 specialist roles** (a big menu of pre-made
  expert personalities) the system can pick from. |
| `autonomous_agent_runtime` | The engine that talks to many different AI providers
  so the agent isn't locked to one. |
| `a2a` | Agent-to-Agent messaging — lets agents talk to each other directly. |
| `task_harness` | Runs long jobs with pause/resume, priorities, and dependencies;
  knows which task must finish before the next can start. |
| `skill_factory` | **Makes new skills automatically** — turns patterns into
  reusable "skill" files, and improves them over time. |
| `gateway` | Connects to chat apps (Telegram/Discord/webhook) and runs scheduled
  "cron" jobs — remote control + automations. |
| `swarm_network` | Optimizes the network so many agent connections run fast without
  dropping. |
| `swarm_bridge` | The "traffic cop" for a 50-builder swarm. |

### Model, quality & machine-learning (8)
| Module | What it does |
|---|---|
| `model_router` | Sends each AI request to the best/cheapest model, retries on
  failure, and falls back to another model if one is down. |
| `model_miner` | Finds, downloads, serves, and (optionally) deletes local AI
  models. |
| `model_security` | Guards whatever model you use, regardless of which one it is. |
| `mlops_lifecycle` | Tracks a machine-learning experiment from start to finish. |
| `llmops_trace` | Records every AI call for debugging (who asked what, what came
  back). |
| `eval_gate` | Automatically scores how good a model's output is before you let it
  through. |
| `universal_score` | Gives any software build a **single score** (0–100+, where
  100 = "sellable to a company"). Checks real code on disk, not made-up numbers. |
| `enterprise_validation` | Runs the whole certification/validation process. |

### Safety, security & compliance (10)
| Module | What it does |
|---|---|
| `safety_governance` | The big-picture safety & governance: reviews model changes,
  approves prompt changes, tracks incidents, registers risks. |
| `threat_model` | Figures out how someone might attack an AI system (uses industry
  threat models like MITRE ATLAS and STRIDE). |
| `ai_defense` | Defends against automated/AI attackers: spots abnormal traffic,
  real-vs-bot. |
| `compliance` | Proves to auditors that you follow rules (OWASP, NIST, MITRE). |
| `privacy_data` | Governs private data: who can see it, how it's kept safe. |
| `guardrails` | Checks input/output against rules and fixes problems. |
| `prompt_guard` | Blocks prompt-injection / jailbreak attempts at the door. |
| `secret_broker` | **Keeps secrets (API keys, passwords) on the machine** so they're
  never sent to outside AI services. |
| `secret_rotation` | Automatically changes passwords/keys on a schedule so old ones
  expire. |
| `vuln_scanner` | Scans AI models for security weaknesses (in the style of the
  "garak" tool). |

### Knowledge, memory & search (6)
| Module | What it does |
|---|---|
| `knowledge_graph` | A map of facts and how they connect (entities and
  relationships). |
| `kb_bridge` | The bridge to the knowledge base: save, search, and get stats. |
| `memory` | Long-term memory for agents — remembers what happened in past
  sessions. |
| `semantic_memory` | Smarter memory that finds things by *meaning*, not just exact
  words. |
| `rag` | Retrieval-Augmented Generation — lets an AI answer using your own
  documents as the source. |
| `compression_bridge` | Compresses data/context to save tokens and money (uses
  several compression algorithms). |

### Business operations & lifecycle (8)
| Module | What it does |
|---|---|
| `release_change` | Manages product releases and changes (approvals, rollout). |
| `disaster_recovery` | Backups, recovery plans, and crisis handling. |
| `innovation_rd` | Tracks research, experiments, and inventions. |
| `developer_experience` | Makes the platform pleasant to develop for. |
| `customer_experience` | Tracks customer journeys, support tickets, engagement. |
| `look_and_feel` | Manages the visual/design identity. |
| `response_hardening` | **(Added recently)** keeps Hermes from cutting off long
  outputs — raises the output-length limits and repairs them after upgrades. |
| `hermes_controller` | The controller for Hermes — orchestrates its prompts. |

### Developer & integration tools (4)
| Module | What it does |
|---|---|
| `mcp_tools` | Lets tools plug in via the Model Context Protocol. |
| `prompt_context` | Manages prompts and their context. |
| `research_verification` | Tracks and verifies research. |
| `triadforge` | Security testing (white/grey/black box) against your own systems. |

**That's the full inventory of ~50 modules.** The exact count you see when you
run `eni_cli status` comes from the kernel *discovering* them at start time.

---

# PART 7 — THE COOPERATIVE MULTI-PLAYER BUILD FLOOR (the main event)

This is the part that makes ENI different from anything else: the ability to have
**many computers build one thing at the same time.**

## 7.1 The three roles
- **Coordination Server** (the boss). Runs on one machine. Holds the queue of
  work, decides which builder gets which job, and keeps the shared workspace.
- **Builder Clients** (the workers). One per computer. Each has its own hardware,
  its own GPU, and its own AI API keys. They connect to the boss and wait for
  jobs.
- **Shared Workspace**. The folder where all finished work is collected,
  conflict-checked, and logged.

## 7.2 How one goal becomes a finished program (step by step)
1. **You submit a goal** (usually through the web API or a curl command):
   `{"goal": "build me a budget tracker"}`.
2. **The local brains** (port 8913) take that one sentence and split it into
   smaller steps, in the right order:
   1. requirements & spec
   2. data model
   3. core logic
   4. API / interface
   5. tests
   6. packaging & README
   Each step has a clear instruction AND a test to check it.
3. **The server** puts those steps in a queue and asks: "which builder is least
   busy and able to do this?" It hands each step to the best-fit machine.
4. **Each builder** writes real code for its step, runs the test, and sends the
   finished file + the test result back.
5. **The merge** checks: did this file already exist with different content? If
   yes, it does NOT overwrite (it flags a conflict). If clean, it writes it into
   the workspace and logs it.
6. When all steps are done, you have a complete, tested program — built by
   several machines in parallel.

## 7.3 The message traffic (how the boss and workers talk)
The boss and workers talk over a WebSocket using small JSON messages. The
important types:
- `hello` / `welcome` — worker introduces itself; boss says "welcome."
- `task` — boss hands a worker a job.
- `work_start` / `work_log` / `work_result` — worker says "starting," streams its
  progress, then reports the result.
- `heartbeat` — worker says "still alive" every 15 seconds.

## 7.4 Safety features (so it doesn't all collapse)
- **Heartbeat timeout**: if a worker goes silent for 60 seconds, the server
  treats it as dead and re-queues its job somewhere else.
- **Retry once**: if a job fails, it's tried once more on another machine. Second
  failure = the job is marked failed.
- **Conflict-safe merge**: it never silently overwrites a file another worker
  wrote. It flags the conflict instead.
- **Never sees your secrets**: workers tell the boss only *what they're capable
  of* (how many CPUs, which models). They never send API keys.
- **Anti-secret guard**: the message system itself refuses to transmit messages
  containing things like `api_key`, `password`, `bearer token`, etc.

## 7.5 Optional hardening you can turn on
- **Auth token** — set `MP_AUTH_TOKEN` and every worker must present it.
- **Multi-tenancy** — isolate customers: each tenant (company) gets its own
  private workspace so they can't see each other.
- **TLS** — encrypt the connections with a certificate.

## 7.6 The environment variables (settings you control)
| Variable | What it does |
|---|---|
| `MP_LLM_URL` | Where builders send their AI calls (e.g. your local free router). |
| `MP_LLM_KEY_ENV` | The name of the env var holding the AI key (so no key is hard-coded). |
| `MP_LLM_MODEL` | Which model builders use. |
| `MP_AUTH_TOKEN` | The shared secret that workers must present. |
| `MP_HOST` / `MP_TENANT` | Where to connect / which tenant this worker belongs to. |
| `MP_MAX_TASKS` | How many jobs one worker handles at once. |
| `MP_TAGS`, `MP_MODELS`, `MP_PROVIDERS` | Advertise what this machine can do. |
| `MP_TOKEN` | The client's credential (used with auth). |

---

# PART 8 — THE LOCAL BRAINS (one prompt → a full program)

On port **8913**, a small server ("local controller") runs the brains of the
whole operation. It answers web requests:

| Endpoint | What it does |
|---|---|
| `POST /plan` | You give it a goal; it returns a step-by-step plan. |
| `POST /enrich` | You give it a short prompt; it expands it into a long, detailed
  one (this is the "make bigger prompts" feature). |
| `POST /program` | It runs the whole plan and writes real files + tests to disk. |
| `GET /health` | Says whether the brain is alive. |

It has three internal parts:
- **`planner.py`** — the goal→steps splitter (deterministic, so the same goal
  always gives the same plan).
- **`vault.py`** — the secret safe. It holds real passwords/keys **locally** and
  replaces them with `{placeholder}` names before anything leaves the machine.
  It also scrubs obvious "api_key=..." text as a safety net.
- **`build_provider.py`** — actually runs each step, writes the file, runs the
  test, and retries once if it fails.

This is the "wow" demo you show a company: type "build me a to-do app," and real,
tested code appears.

---

# PART 9 — SECURITY: HOW SECRETS NEVER LEAVE YOUR MACHINE

This is a core promise of the platform. The chain works like this:
1. Every prompt first passes through a **prompt guard**.
2. If a real secret is detected (an API key, a password), it is **replaced with a
   placeholder** like `{SECRET:OPENROUTER}`.
3. The actual secret value is only ever stored **locally** in the vault.
4. Cloud AI models receive **only the placeholder** — never the real value.
5. After the model replies, the placeholder is swapped back in locally, and the
   output passes through a validator.
6. Everything is logged in an **audit chain** so you can prove nothing leaked.

The messaging layer adds another safety net: it refuses to even transmit a
message that looks like it contains a credential.

Related modules: `secret_broker`, `secret_rotation`, `prompt_guard`,
`model_security`, `ai_defense`.

---

# PART 10 — THE COMMAND-LINE TOOLS (what you type)

The main tool is `eni_cli`. You run it from the repo:

```
python3 scripts/eni_cli <command>
```

| Command | What it does |
|---|---|
| `eni_cli status` | Shows how many modules are present and healthy, test counts,
  and whether the skills pack is there. |
| `eni_cli doctor` | Deep health check of the kernel + skills pack. |
| `eni_cli install` | Installs the portable skills/LSP/MCP/plugin pack into your
  Hermes home. |
| `eni_cli setup` | **One-command setup:** installs the pack + sets up systemd
  services so the controller and multiplayer server start on boot. |
| `eni_cli fleet [host]` | Starts a builder client that connects to the
  multiplayer server. |
| `eni_cli local` | **Boots the whole side-by-side view** — starts the ENI
  controller + multiplayer server + Hermes, and opens a browser tab showing them
  all. |
| `eni_cli agent-os` | Reports the status of the agent_os module. |
| `eni_cli up` | Tells you how to bring up the Docker version. |

There's also a convenience command called **`hermes-local`** (installed into your
`~/.local/bin`). Typing `hermes-local` in a terminal boots the local ENI stack
AND Hermes side-by-side and opens a browser page with tabs for each — so you can
actually *watch* both run at the same time instead of staring at a blank JSON
response.

---

# PART 11 — HOW TO SET IT UP (the whole thing, step by step)

You have two options: one-command, or manual.

## Option A — One command (easiest)
From the parent folder:
```
bash setup.sh
```
This will (in order):
1. Check you're in the right place.
2. Try to install Python dependencies (if the system blocks it for security,
   it notes this and continues — the core is all built-in Python so it still
   works).
3. Install the portable skills/LSP/MCP/plugin pack into your Hermes home
   (existing files are backed up first).
4. Set up systemd services so the controller and multiplayer server start on
   boot.
5. Verify the platform kernel imports.
6. Print a status report.

After setup, start the servers:
```
bash enterprise/scripts/boot_all.sh --headless
```
This boots the multiplayer server, the local controller, and (if present) the
free model router. Then open the browser hub:
```
hermes-local
```

## Option B — Manual, one piece at a time (so you learn it)
1. **Check the platform is healthy:**
```
cd /home/hunter/Desktop/Enterprise\ Builder/enterprise
python3 scripts/eni_cli status
```
2. **Start the one-prompt brains** (port 8913):
```
python3 -m enterprise.local_controller.controller --port 8913
```
3. **Start the multiplayer coordination server** (ports 8787 + 8788):
```
python3 -m enterprise.multiplayer.server.server 8787
```
4. **Start a builder client** on this machine (so it can do work):
```
python3 -m enterprise.multiplayer.client.client --worker llm --host 127.0.0.1 --port 8787
```
5. **Submit a goal** (open another terminal, or a browser to the hub):
```
curl -X POST http://127.0.0.1:8788/api/submit_plan \
  -H "Content-Type: application/json" \
  -d '{"goal":"build a to-do app","tenant":"acme"}'
```
6. **Watch it happen** in the browser at http://127.0.0.1:8890/sidebyside.html
   (or the board at http://127.0.0.1:8788/api/board).

## The dashboard (web admin)
To see the whole platform's health on screen:
```
python3 dashboard/server.py        # opens on port 8421
```

## To have services start automatically (systemd)
The repo ships two service definitions in `systemd/`. `eni_cli setup` installs
them for you:
- `eni-controller.service` — the local brains on 8913.
- `eni-multiplayer-server.service` — the coordination server on 8787.

---

# PART 12 — HOW TO RUN THE TESTS (and what "green" means)

From the repo:
```
cd /home/hunter/Desktop/Enterprise\ Builder/enterprise
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider
```
A healthy result looks like: `44xx passed, 1 skipped`. That means every automated
test passed and the platform is in a buildable state.

**An honest note on the numbers:** older documents in the repo claimed
"3,135/3,135 tests passing, 100%, SINGULARITY score 177/100." Those numbers were
produced by a scoring engine and were never backed by an actual test run — they
are inflated and should NOT be quoted as fact. The real, verified state of this
repo:
- A current full run collects **4,412 tests** and passes **4,411 (1 skipped)**.
- Line coverage is roughly **83%** (Grade B) across ~205 files.
- The quality reports rated observability ~0.66, AI quality ~0.66, scalability
  ~0.65, and noted that some `/health` endpoints aren't deployed — real gaps, not
  perfect.

So when you talk to a customer or a lender, use the **verified** numbers, not
the old "177" sticker.

---

# PART 13 — VALIDATION & QUALITY (what's actually proven)

The good news is the platform is real and substantially tested. The honest
picture:
- **4,411 tests passing** (verified above) across the kernel, all modules, the
  multiplayer system, the local brains, and the CLI.
- The **Universal Build Score** framework exists and is grounded in real quality
  standards (ISO 25010, Sonar, DORA, CMMI, Snyk). It inspects real code on disk —
  it doesn't guess.
- **Not yet proven from a real run**: the "177 SINGULARITY" certification, the
  "100% Enterprise Ready" cert, the "3,135/3,135" pass count. Treat those as old
  engine claims.
- **Not yet done**: real penetration testing (security is capability-detection
  only so far), real load testing, and chaos/fault-injection testing. These are
  flagged as future work.

---

# PART 14 — HOW IT MAKES MONEY (pricing & the business plan)

## The pricing ladder (from `docs/SELLING.md`)
| Tier | Who | Price |
|---|---|---|
| Self-host, Free | people evaluating it | Free up to 10 builders |
| Team | companies using it daily | **$12k–25k/year** flat |
| Pro per-seat | freelancers / shops | $2,500/year per builder |
| Hosted SaaS | companies that won't host it | infra cost + $10/builder/month |
| White-label | agencies / resellers | 30–60% margin per session |

The thinking behind the price: a senior engineer costs a company $80k–250k/year
fully loaded. If ENI makes a team meaningfully faster, a company can justify
paying 5–10% of ONE engineer's salary for the whole platform. You price against
the *labor it replaces*, not against "what an AI tool costs."

## The 2-year financial model (real spreadsheet)
The repo ships `docs/ENI_PROFORMA_2YR.xlsx` — a live, editable formula sheet.
With current assumptions it shows:
- Year 1 = **–$59,340 net** (the investment/ramp-up year, while co-build clients
  sign on).
- Year 2 = **+$11,604 pre-tax** (profitable once ~5 clients are active),
  **+$9,288 after tax**.
That's an honest, credible curve for a lender: invest in Year 1, profit in
Year 2.

All the money pictures vary by what you put in the yellow "Assumptions" cells —
plug in a real signed contract and the numbers update everywhere automatically.

## Where the whole business story lives
- `docs/SELLING.md` — pricing & go-to-market.
- `docs/BUSINESS_PROPOSAL.md`, `docs/PRESENTATION.md` — the pitch.
- `docs/LOAN_READINESS_REPORT.md` — ties it all together for financing.
- `/home/hunter/Desktop/Enterprise Builder` business plan `.docx` files — the
  loan application (same content twice).

---

# PART 15 — THE PORTABLE HERMES LAYER (skills you can take anywhere)

The platform mirrors your entire Hermes agent setup into a portable pack:
- **`skills_pack/skills/`** — 20 categories, ~957 skill files.
- **`skills_pack/lsp/`**, **`skills_pack/mcp/`**, **`skills_pack/plugins/`** —
  language servers, MCP servers, and plugins.
- **`install_skillspack.sh`** — copies this pack into a Hermes home safely:
  idempotent (safe to run twice), backs up what was there, strips junk.

This means: hand a company this repo, run one installer, and they get a working
agent layer — plus the whole platform — without assembling it by hand.

---

# PART 16 — THE ARCHIVED OLD PROJECTS (`_legacy/`)

When the platform was consolidated, several early, overlapping projects were set
aside. **They are not used anymore.** Their capabilities all exist inside the
main platform now. They're kept only for reference:
- `_legacy/eni_compression/` — an early compression engine (the platform now has
  `compression_bridge`).
- `_legacy/ENI_Swarm_NEW/` — an early single-machine swarm (now replaced by the
  multi-machine `multiplayer/`).
- `_legacy/compression_bridge/` — older compression bridge.
- `_legacy/ENI_KB/` — an old knowledge-base checkout (the live knowledge base now
  lives at `~/.eni/kb`).

Don't read `_legacy/` for how things work today — use the main `modules/`.

---

# PART 17 — COMMON QUESTIONS (plain answers)

**Q: Do I need a powerful computer?**
A: No single computer needs to be powerful. The point is you use MANY ordinary
computers in parallel. Each worker just needs Python.

**Q: Do the builder machines share my API keys?**
A: No. Keys stay on each machine and are never sent to the server. The server
only knows what each machine *can do*.

**Q: Where do the finished programs land?**
A: In the server's shared workspace, under `data/multiplayer/wspace/` — and if
you use tenants, under a folder named after the tenant so customers stay
isolated.

**Q: I get "address already in use."**
A: Something is already on that port. Either stop the old process or change the
port (the tools let you pass a port number).

**Q: `hermes-local` shows a blank page or "Not Found"?**
A: Make sure the controllers are running (run `bash
enterprise/scripts/boot_all.sh --headless` first, or `eni_cli local`). The
browser page needs the services on their ports to show anything.

**Q: Why do old docs say "177/100"?**
A: That was an old scoring formula. The real, verified number is "4,411 tests
passing." Use the verified one.

---

# PART 18 — A QUICK CHEAT-SHEET OF EVERY KEY COMMAND

```bash
# From the enterprise repo
cd /home/hunter/Desktop/Enterprise\ Builder/enterprise

# Health & setup
python3 scripts/eni_cli status          # how am I doing?
python3 scripts/eni_cli doctor          # deep check
bash setup.sh                            # one-command install (from parent)

# Run the services
python3 -m enterprise.local_controller.controller --port 8913     # brains
python3 -m enterprise.multiplayer.server.server 8787              # coordinator
python3 -m enterprise.multiplayer.client.client --worker llm --host 127.0.0.1 --port 8787  # a builder

# All in one, with a browser view
hermes-local                            # boots ENI + Hermes + opens the hub

# Boot all servers in the background
bash enterprise/scripts/boot_all.sh --headless

# Submit a build goal
curl -X POST http://127.0.0.1:8788/api/submit_plan -H "Content-Type: application/json" \
     -d '{"goal":"build a to-do app","tenant":"acme"}'

# Web admin
python3 dashboard/server.py              # port 8421

# Run all tests
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider
```

---

# THE END — WHAT "DONE" LOOKS LIKE

You'll know everything is working when:
1. `python3 scripts/eni_cli status` shows your modules present and healthy.
2. `hermes-local` opens a browser page with green "up" pills for Hermes,
   Multiplayer, and Controller.
3. You submit `{"goal":"build a to-do app","tenant":"acme"}` to the submit_plan
   endpoint and, a little later, real files appear in the workspace.
4. `PYTHONPATH=. python3 -m pytest -q` most/all tests pass.

That's the whole platform: a kernel that runs ~50 safety-tested modules, a local
brain that turns one sentence into a plan, and a multiplayer floor that turns
that plan into real code using many machines at once — with secrets kept safe and
the test numbers kept honest.

*End of the master guide.*