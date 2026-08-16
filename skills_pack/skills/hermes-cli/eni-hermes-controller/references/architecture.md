# ENI Hermes Controller — architecture detail & build backlog

## Module layout (/home/hunter/.hermes/controller/eni_controller/)
- `config.py`       — paths (controller/enterprise/KB dirs), free-router/security URLs,
                      retry + auto-continue defaults, free-model list. Env-overridable.
- `enterprise.py`   — `EnterpriseCatalog` (auto-discover modules), `ModuleInfo`,
                      `recommend()`, `to_prompt_block()`. Ever-expanding by design.
- `secrets.py`      — `SecretsBoundary` wrapping SecretBroker; `sanitize_for_cloud()`,
                      `assert_cloud_safe()` (fail-closed), `restore_for_lo()`. `use_broker`
                      flag for deterministic tests (fallback vault when broker absent).
- `expander.py`     — `PromptExpander.expand()` → massive structured prompt. Build modes:
                      full power / demiurge / normal. Injecte catalogs + standing rules +
                      REINFORCEMENT block. `_detect_build_mode()` recognizes swarm/build/fix.
- `router.py`       — `ModelRouter.chat()`: free-router first, then OpenRouter free-model
                      rotation. Auto-continue on `finish_reason=length`. RateLimitExhaustedError.
                      Records every success/failure/429 + latency into observability.
- `observability.py`— NEW 2026-08-07. Thread-safe `Metrics`: per-provider ok/fail/
                      rate-limit windows, latency p50/p95/avg, event ring buffer, counters.
                      `get_metrics().snapshot()` feeds `/status` + `/metrics`.
- `health.py`       — NEW 2026-08-07. `check(cfg)` probes airllm, free-router, secrets
                      broker + audit integrity, enterprise catalog, hermes runner, queue;
                      returns overall healthy. Backs `/health` + CLI `health`.
- `hermes_runner.py`— `HermesRunner.run()` (subprocess `hermes -z`), `JobQueue` (persistent json).
- `scheduler.py`    — `DeferredScheduler.tick()`, `next_run_at('18:00')`, `enqueue_for_6pm()`.
- `reinforce.py`    — `RetentionStore` (KB dedupe), `reinforce_success()`, skill instructions.
- `model_miner.py`  — `LocalModelScanner`, `KnowledgeRipper`, `ModelMiner.mine()`.
- `controller.py`   — `Controller.process()`, CLI, HTTP `make_handler`/`serve`.

## Service file (~/.config/systemd/user/eni-controller.service) — as wired 2026-08-05
```
[Service]
Type=simple
WorkingDirectory=/home/hunter/.hermes/controller
ExecStart=/usr/bin/env python3 -m eni_controller.controller serve --port 8940
Restart=on-failure
RestartSec=3
Environment=ENI_FREE_ROUTER_URL=http://127.0.0.1:8920
Environment=ENI_SECURITY_SERVER_URL=http://127.0.0.1:8940   # security folded INTO controller
Environment=ENI_AIRLLM_URL=http://127.0.0.1:8913/v1
Environment=ENI_AIRLLM_MODEL=mistralai/Mistral-7B-Instruct-v0.2
```
`serve` accepts `--host`/`--port`. Scheduler thread runs in `serve()`.

## Local chat backend (added this session)
- `eni_controller/airllm.py` — `AirLLMBackend`, PRIMARY local chat backend.
  `Controller.process()` direct-chat path routes through it first (`backend: airllm`),
  falling back to `ModelRouter` (free-router cloud) only when airllm is down.
  `ENI_AIRLLM_URL` / `ENI_AIRLLM_MODEL` in config.py (env-overridable).
- The standalone `eni-security.service` sidecar (:8931) was RETIRED. Security is
  now served by the controller's own HTTP handler under `/security/*`
  (`/security`, `/security/env/{set,get,list,remove}`, `/security/sanitize`,
  `/security/audit`) reusing `controller.boundary` (SecretsBoundary). airllm's
  `secret_get/secret_set` tools now POST to `:8940/security/env/*`, not :8931.
- airllm itself runs as systemd `airllm.service` (:8913, Mistral-7B 4-bit,
  auto-boot). See `references/local-ai-chat-backend.md` (stale-GPU-process fix)
  and `references/qlora-finetune-8gb.md` (train the controller's own model).

## New endpoints / CLI (added 2026-08-07 hardening pass)
- **`GET /health`** — real component probe via `health.check()`: airllm, free-router,
  secrets broker + audit-chain integrity, enterprise catalog (module count), hermes
  runner, queue. Returns `{checks:{...}, overall:{healthy, critical_ok, checks_ok}}`.
- **`GET /metrics`** — `observability.Metrics.snapshot()`: per-provider ok/fail/429
  windows, latency p50/p95/avg, counters, recent event ring. Also embedded in `/status`.
- **CLI subcommands:** `health`, `metrics`, `catalog` (dumps all modules + tests flag).
- **Free-model pool expanded 4 → 12+** in `config.DEFAULT_FREE_MODELS` AND
  `free_router.OPENROUTER_FREE_MODELS`: DeepSeek V3.1, SambaNova DS-V3.1, Upstage
  Solar Pro, Zhipu GLM-5.2, Nemotron family, Llama 3.1 405B, Qwen 2.5 72B, Mistral
  Large 2. Keep both lists in sync when adding/removing rollover targets.

## PITFALLS
- **AirLLM `/health` lives at the server ROOT, not under `/v1`.** The controller's
  old `healthy()` probed `base_url + "/../health"` = `/v1/../health` — but
  `urllib.request` does NOT normalize `..` path segments (curl does, which is why it
  "worked" in a terminal). Result: persistent false `unreachable`. Fix: derive root
  by stripping a trailing `/v1` from base_url, then hit `root + "/health"`. General
  rule: NEVER rely on `..` in URLs built for urllib.
- Keep `api_max_retries` low (3-6) so the expanded free pool rotates fast on 429
  instead of silently deadlocking (see memory).

## Tests
- `/home/hunter/.hermes/controller/tests/test_controller.py` — 17 tests, offline
  (no cloud). Expander, catalog, secrets (fallback mode via `use_broker=False`),
  scheduler, queue, reinforcement store, router (stubbed HTTP to avoid live calls).
- `/home/hunter/.hermes/controller/tests/test_eni_controller.py` — 13 tests (added
  2026-08-07): observability (snapshot/p95/fail/429/reset/thread-safety), config
  free-model list, enterprise catalog (all modules have capability hints,
  recommend returns security baseline), health report structure, airllm root-health
  regression, expander. Suite total now **45 passed in 0.33s**.
- Enterprise module: `modules/hermes_controller/tests/test_hermes_controller.py` — 5 tests.

## Verified outcomes (2026-08-07 hardening pass)
- Controller suite: 45 passed. Enterprise platform suite: 205 passed (untouched, still green).
- Live `health` probe: overall healthy, 6/6 checks ok (airllm, free-router, secrets,
  enterprise 47 modules / 44 with tests, hermes runner, queue).
- Fixed AirLLM health-path bug (root `/health` now detected healthy).
- All 47 enterprise modules now have static capability hints (added 6: model_miner,
  hermes_controller, rag, look_and_feel, mlops_lifecycle, autonomous_agent_runtime)
  → expander recommends the right module instead of weak introspection fallback.
- Note: the RUNNING `eni-controller.service` daemon needs a `systemctl --user restart
  eni-controller` to pick up new endpoints after code changes; fresh CLI processes
  (`python3 -m eni_controller.controller ...`) always run the new code immediately.

## Verified outcomes (2026-08-05)
- `status`: router healthy, 42 enterprise modules (incl. hermes_controller), broker
  attached, 0 pending.
- expander: "use swarm to build the full enterprise platform" → 5326-char demiurge
  prompt, 12 modules.
- model miner: mined `controller-free-router` → 8 KB entries
  (`~/.eni/kb/controller_model_rip_*.md`) + MCP tool descriptor + LSP note.
- chat: `hermes -z` path returns through the privacy gate.

## LO queued-build backlog (in flight / ideas to implement)
1. ✅ Cloud models must never touch private info across ALL builds → SecretsBoundary
   gate applied at `process()` level (both egress paths).
2. ✅ When free models run out, continue at 6pm local → scheduler + JobQueue.
3. ✅ Put the controller into the enterprise platform → `modules/hermes_controller/`.
4. ✅ Local-model trainer scanner → `model_miner.py` (scan/rip/MCP/LSP).
5. ✅ Make the model catalog ever-expanding → auto-discovery in `enterprise.py`.
6. Suggested next: add controller service + CLI to a skill (done here); add a daily
   "site check" cron that pings controller :8940 + acpeso tunnel + free-router.
