# ENI ENTERPRISE — HEAVY UPGRADE ROADMAP
## The next tier of upgrades to make this a real, sellable, self-improving platform

Draft v1 — targeted at real, verified gaps in the code (not hypotheticals).
Priorities follow: (A) make it *actually* work great → (B) make it *sell* → (C) make
it *learn*. Each is concrete and grounded in current weaknesses.

---

## A. MAKE IT ACTUALLY WORK GREAT (engineering truth first)

### A1. Make observability real (biggest true gap right now)
Status: The validation digests show only ~3 of 20+ modules report live health; most
`/health` endpoints are "not deployed"; the dashboard still leans on old scored
numbers. This is the weakest part of the system on paper.

Upgrade:
- Every module gets a real `health_check()` that hits its own `/health` or a uniform
  probe, wired through the kernel.
- One Prometheus/alerts config that covers ALL modules + the multiplayer floor +
  the local brains, not a few.
- Dashboard shows the LIVE verified state (real test count, per-module health,
  active builders, cost) — kill the stale "177" stickers.

### A2. Real-time board (fix the "cosmetic console" complaint for good)
Status: the side-by-side hub polls `/api/board` every 3s and the mp tab renders raw
JSON; no live streaming.

Upgrade:
- Push-model WebSocket/SSe from the coordination server → every dashboard/tab updates
  live (task added / running / merged, worker CPU/GPU, streamed logs per task).
- A proper rendered board: worker heatmap, per-task progress bars, merge conflict
  badges — not JSON dumped in an iframe.

### A3. One-prompt → REAL program (the demo must produce real code, not stubs)
Status: `/program` today writes deterministic scaffold files that satisfy test hints
but aren't real working programs. Great for tests, useless as a selling demo.

Upgrade:
- Wire the `llm` worker (MP_LLM_URL/KEY_ENV/MODEL) as the real generator inside
  `submit_plan`: planner → N steps → real model writes real code across the fleet →
  real tests compile → merged.
- Add a "generate → compile → test → iterate" loop (bounded retries) so the demo
  ends with a program that actually runs.

### A4. ICM becomes the routing brain, end to end
Status: ICM now scaffolds + routes + compresses context, but the *broker* doesn't
consult it. Every task enters the floor unstructured.

Upgrade:
- Router order: task → ICM `classify()` (sequential vs swarm) → sequential tasks get
  auto-scaffolded + routed to a stage + progressive-disclosure context; swarm tasks
  stay in the multi-agent layer.
- Close the loop: the multiplayer broker reads `00_master.md` and feeds each worker
  only the stage it needs.

### A5. Self-healing fleet
Status: worker timeout re-queues exist, but there's no supervisor.

Upgrade:
- systemd-watchable supervisor for every role (multiplayer server, controller, free
  router, dashboard, builders) with health-based auto-restart.
- Dead-worker → auto-replace + task re-dispatch so the floor never silently stalls
  (the classic "looks dead, is retrying on a dead key" failure we've hit).
- A fleet-health monitor endpoint consolidating it all.

---

## B. MAKE IT SELL (product, security, monetization)

### B1. Product-grade authentication (the security gap)
Status: auth is a single shared `MP_AUTH_TOKEN`, and TLS only protects the WS side,
not the HTTP API. For customers this is a blocker.

Upgrade:
- OIDC / API keys with **per-tenant scopes**, with every request audited to the
  tamper-evident audit chain.
- TLS on both the WS and HTTP surfaces by default; mTLS or key-hashed workers.
- Optional SSO (the plan's customers are companies — they'll ask).

### B2. Real licensing & tier enforcement (monetization; `licensing/` is empty)
Status: pricing tiers exist in docs but nothing enforces them.

Upgrade:
- `licensing/` module: signed license keys, seat counting per tier
  (Free ≤10 builders / Team unlimited / Pro per-seat / Hosted), expiry, feature
  gating.
- Enforcement hooks in the broker (cap builders per license) + dashboard shows
  license status + renewal.

### B3. Per-tenant cost metering + budget guards
Status: tenancy isolates filespaces but not cost.

Upgrade:
- Meter tokens/cost per task per tenant from the router ladder; enforce per-tenant
  monthly budgets with automatic model downgrade when a tenant approaches quota.
- This IS the "cheaper, better automated building" selling point, made measurable.

### B4. "Bring-your-own-machine" onboarder
Status: a client is launched by hand with env vars.

Upgrade:
- One command: `curl -sSL eni.io/fleet | sh` detects hardware + GPU, installs deps,
  generates a capability profile, and connects to a named server with a one-time
  invite token. A fresh machine becomes a builder in ~90 seconds.

### B5. CI/CD drop-in (GitHub/GitLab app)
Status: the floor builds from a `/api/submit_plan` call; no repo hook.

Upgrade:
- A thin app that watches a repo: any issue/PR → auto-decompose into ICM stages →
  build on the fleet → open a PR with merge-safe artifacts + test results.
- This is the "bring your backlog" story that opens enterprise doors.

### B6. The capability marketplace
Status: `agent_catalog` (432 specialists) + `skills_pack` exist but are folders, not
browsable/purchasable.

Upgrade:
- A marketplace inside the dashboard: browse/search the 432 specialists + every ICM
  skill; one-click install to a tenant; per-skill licenses. Monetizes the catalog
  we already have.

---

## C. MAKE IT LEARN (compounding advantage)

### C1. Live benchmarks as sales proof
Upgrade: a benchmark harness proving N machines build the same task N× faster than
1 machine (one machine vs 2 vs 4 on the same `submit_plan` goal, real times). This is
the single most persuasive artifact — a speed curve from the actual floor.

### C2. Live business intelligence
Upgrade: the proforma (`ENI_PROFORMA_2YR.xlsx`) stops being a manual model — the
controller feeds real build counts / token cost / billable builders into it so
revenue forecasts update with real usage. Turns the loan plan into a living model.

### C3. Outcome-based evolution (the self-improving flywheel)
Status: `skill_factory` self-evolves skills; `universal_score` scores builds.

Upgrade:
- Tie them: every completed build gets scored; losing skills auto-regress, winning
  patterns get promoted into the default scaffold. The platform literally gets better
  at building the more it builds — a defensible moat.
- Use `outcome-based-evolution-scoring` (existing skill) to drive it.

### C4. Fractional reasoning (the escalation ladder as a feature)
Upgrade: make the OpenRouter escalation ladder *observable and configurable per
task-type*: deterministic ICM stages always use the cheapest model; judgment stages
escalate to frontier only when needed. Customers see cost exactly where it's spent.
This is a real differentiator vs flat-price AI tools.

---

## Suggested order of execution (highest leverage → high effort)
1. **A3 (real code) + B1 (auth) + A2 (live board)** — the demo must work and look real
   before selling; security before customers. These close the "broken/useless" and
   "not sellable" gaps.
2. **B2 (licensing) + B3 (cost metering)** — make it actually make money.
3. **C1 (benchmarks) + B4 (onboarder) + B5 (CI/CD)** — the sales + onboarding wedge.
4. **A1 (observability) + A5 (self-healing) + ICM-end-to-end** — enterprise trust.
5. **C2/C3/C4 (live BI, evolution, fractional cost)** — the compounding moat.

## Cross-cutting principle
Every upgrade must be **verified truth, not claims**: real tests, real live numbers,
real benchmark times. The platform's reputation hinges on the honesty rule — no
"177 magic numbers"; only what actually runs.