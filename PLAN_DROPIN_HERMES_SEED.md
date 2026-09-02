# ENI ENTERPRISE BUILDER -> HERMES DROP-IN SEED (PLAN v4)

Author: LO / ENI. Date: 2026-09-01. Status: PROPOSED (not yet built).

## THE PIVOT (why)
Old framing (ARCHITECTURE_v2.md): standalone self-hostable "Enterprise AI OS" —
dashboard :8421, desktop chat app, multiplayer coordination server (+licensing/
tenancy rounded on selling seats). Candid: LO is rejecting that. No dashboard. No
desktop chat. No multiplayer-server-for-hire.

New framing: Enterprise Builder is a **drag-and-drop HERMES augmentation seed.** It does NOT
run as its own server or app. It INSTALLS ITSELF INTO HERMES (~/.hermes/plugins/,
skills/, cron/), boots its PlatformOS kernel EMBEDDED inside the Hermes process, and wires all
88 capability modules into Hermes's own build loop — so Hermes itself becomes a dramatically
better builder. One folder dropped in + one installer = done.

##THE MECHANIC (why drag-and-drop works)
Hermes v0.15.2 auto-discovers user plugins from ~/.hermes/plugins/<name>/ —
each folder just needs plugin.yaml + __init__.py with `register(ctx)`. Verified via
/hermes_cli/plugins.py (sources: bundled / user / project via HERMES_ENABLE_PROJECT_PLUGINS /
pip entrypoints). So "drag and drop" = copy the seed folder into ~/.hermes/plugins/
+ run one installer (python3 seed_installer.py --home ~/.hermes). Restart Hermes. Done.
No dashboard, no separate server.

Hermes's VALID_HOOKS (verified):
  pre_tool_call / post_tool_call
  transform_terminal_output / transform_tool_result / transform_llm_output
  pre_llm_call / post_llm_call / pre_api_request / post_api_request
  on_session_start / on_session_end / on_session_finalize / on_session_reset
  subagent_stop / pre_gateway_dispatch / pre_approval_request / post_approval_response
Plugin registry also exposes: register_tool, register_skill, register_cli_command,
register_command, register_context_engine, register_platform, register_auxiliary_task,
register_dashboard_auth_provider, and provider-regs (image/video/websearch/browser/tts/transcription.

##TARGET LAYOUT (what the drop-folder carries)
hermes_enterprise_seed/
  plugin.yaml                    # name: eni-enterprise-seed, hooks: (all above)
  __init__.py                   # register(ctx): boot kernel, wire module pipeline to hooks
  seed_installer.py              # python3 seed_installer.py --home ~/.hermes
                                   #   writes plugin/, skills/, cron/, config merges, systemd (optional)
  kernel_bridge.py              # embeds PlatformOS (ModuleRegistry+EventBus+HealthChecker)
                                 #   AS AN IN-PROCESS singleton, no network sockets
  pipeline.py                   # maps 88 modules -> hook/tool handlers (the "better builder" core)
  skills/                       # 88 eni-module-* SKILL.md (already built in skills_pack)
  cron/                        # scheduled: daily briefing, KB consolidation, eval sweep
  modules/                     # 88 module sources (from this repo, tree of the canonical root)
  kb/                          # knowledge base seed (patterns.db bridge points
  STATUS_SEED.md               # health + self-test report
Notes:
  dashboard/ + desktop/ + multiplayer/server/ + tenancy/ + licensing/: CUT from the
  shipped seed (telemetry instead = Hermes logs + STATUS file + /enterprise status
  slash command). source stays in repo for reuse, but is NOT part of the drop-target.

##HOW THE SEED MAKES HERMES "WAYYY BETTER"
(Module -> Hermes hook -> effect on every build task)
Build-quality modules (the payload:
  prd_audit            -> pre_tool_call (on build start): require a written PRD/plan
                            before heavy tool use etiquette -> transform_tool_result: gate stunned output
  eval_gate            -> post_tool_call: score each build artifact vs declared spec; block
                            low-score results from entering context (fail open)
  codegen_audit / engineering_tradeoff -> transform_tool_result: audit diffs + surface
                            tradeoffs; inject "what adds R / what to drop" notes
  error_correction     -> post_llm_call: catch failed-too pipeline, auto-retry hardened
  production_agent_hardening + production_hardening + response_hardening
                          -> transform_llm_output + post_api_request: shippable-output
                            gates (no stubs, no placeholders, real data only)
  research_verification + enterprise_validation + prd_audit + automation_triage
                          -> pre_tool_call: verify sources, gate unvalidated claims
  second_brain + position_addressed_memory + semantic_memory + memory + knowledge_graph
                          -> on_session_end: offline memory de-dup + KB sync (via hermes-memory-kb-offload)
  agentic_rag + rag + kb_bridge + paper_feeds
                          -> register_context_engine: replace/boost entity ContextCompressor =>
                            ground every build in the KB/paper digest (no hallucinated design)
  model_router + model_psychometrics + cost_meter + model_miner + free-router
                          -> pre_llm_call: route each step to the right model (free/cheap for
                            mechanical, strong for reasoning),track cost,auto-fallback on 429
  model_security + guardrails + safety_governance + threat_model + prompt_guard
                          -> pre_llm_call: sanitize prompts, block injection into the build loop
  secret_broker + secret_rotation + privacy_data + compliance + vuln_scanner
                          -> pre_tool_call: exfil-less secrets for module/vendor calls, rotate,
                            scan for leaked creds in workspace
  skill_factory + task_harness + unified_work_system + custom_agent_workflows
                          -> on_session_start: surface one auto-built skill per completed task
                            (curator behavior; the build loop itself gets smarter each session)
  error_correction + llmops_trace + observability + monitoring + response_ops
                          -> post_llm_call: trace every build step, detect regressions, self-heal
  slash_workflow + unified_inbox + autonomous_agent_runtime + group_chat_orchestration
                          -> register_cli_command + register_command: /enterprise <module> <op>,
                            /prd <goal>, /status, /eval <artifact> (all UI is IN the Hermes chat —
                            no desktop, no dashboard.

##BUILD PIPELINE ON A HERMES TASK (end-to-end)
 1  on_session_start/heavy goal: prd_audit -> write PRD (spec+acceptance) to KB
 2   pre_tool_call: automation_triage + task_harness pick the module chain for this step
                           secret_broker provides creds; model_router picks the model
  3   pre_llm_call: prompt_guard + context_routing inject KB/rag grounding + paper feeds
                          response_hardening freeze the user's language/tone rules
  4   tool call: (normal) — but transform_tool_result runs eval_gate + codegen_audit
                          on the artifact BEFORE it enters context
  5   post_llm_call: error_correction + llmops_trace check the step succeeded;, else
                          eng->tradeoff auto-replan a cheaper/harder path
 6   on_session_end: second_brain + semantic_memory compress this session to memory,
                          KB sync, skill_factory proposes one new skill
  Result: every Hermes task is planned, gated, audited, grounded in KB, cost-routed,
  hardened, traced, and the pool of skills grows each session. THAT is "wayyy better."

##CUT LIST (what disappears from the shipped product
  dashboard/server.py :8421          -> DEAD (no web UI. /enterprise status replaces it
  desktop/ chat app                    -> DEAD (no desktop app. Hermes chat IS the UI
  multiplayer/server/ + broker/       -> DEAD (no multi-machine coordination server..
  tenancy/ + licensing/              -> DEAD (no per-seat/multi-tenant sell layer.in seed
  docker-compose / Dockerfile        -> DEAD for the seed (single-folder home drop; keep in
                                           repo for people who want the old standalone.
  carriers/*.png + .carrier blobs   -> do NOT ship in the seed (keep compression engine only.
Keep the source of all the above in the repo (git history), but the drop target = the seed folder only.

##VERIFICATION (how we prove "wayyy better" honestly)
 1  seed_installer.py --home ~/.hermes  (idempotent) then restart Hermes ->
     `hermes plugins list` shows eni-enterprise-seed enabled.
 (real verification
  2  /enterprise status -> PlatformOS kernel healthy, N/88 modules loaded, each module's
      health_check PASS/FAIL board (real numbers, no stubs.

  3  golden-path test: run one real build task twice — once with seed OFF, once ON;
      compare: artifacts pass eval_gate?? no-stub ratio?? retries?? cost?? A/B table in
      STATUS_SEED.md (real tallies, per LO: no fake data ever..
  4  memory/KB: after N sessions, KB row-count + skill_factory skill-count grow
      (real deltas, logged..
  5  cost: model_router + cost_meter tallies tokens $ per task across free/paid mix.

##PHASES
Phase 0 — Scaffold the seed folder + seed_installer.py (idempotent cp to
   ~/.hermes/{plugins,skills,cron}} + plugin.yaml + stub register(ctx) that boots
   kernel_bridge in-process.rand verify plugin auto-loads (hermes plugins list.This
   proves THE drag-and-drop mechanic end-to-end.

Phase 1 — kernel_bridge.py: load the 88 modules AS AN IN-PROCESS ModuleRegistry
   (reuse repo's platform_kernel.ModuleRegistry, no sockets), each module's
   initialize/health_check/shutdown wired to on_session_start/status/on_session_end.
+
Phase 2 — pipeline.py: map the BUILD-QUALITY module set to real Hermes hooks
   (eval_gate post_tool_call, prd_audit pre_tool_call, agentic_rag context engine,
   skill_factory on_session_end, etc.. Depart with the highest-R modules (BO learned
   what adds R: prd_audit, eval_gate, engineering_tradeoff, codegen_audit,
   error_correction, agentic_rag, second_brain, model_router..
   Phase  3 — slash commands + telemetry: /enterprise status/eval/prd in-chat,
   STATUS_SEED.md self-test board. Dashboard/desktop removed from shipped seed.

Phase  4 — golden-path A/B + memory/KB self-healing + STATUS_SEED.md PASS/FAIL board.
##OPEN QUESTIONS (resolve in Phase 0/1
  Which modules currently have WORKING initialize() when imported WITHOUT the full
    repo deps (some 88 are legacy-core decls. Audit = src of "what's R".
   KB bridge target: point at ~/.eni/kb (existing daemon) or carry a KB seed copy?
   Cron: reuse existing enterprise cron jobs or ship new under seed/cron/?
   Where does "module source" live in the seed: reference the canonical repo (symlink/
    copy). (Seed should be ONE standalone folder, so copy  — but de-dup via
    skills_pack already canonical. Decide in Phase 0.
##NEXT
Phase 0 approved -> build scaffold + installer + verify auto-load. Then go phase 1..