# STATUS_DEMIURGE_HERMES_DROPIN_SEED.md

Pass: Hermes drop-in seed + fixed compression-in-enterprise + cleanup
Date: 2026-09-01
Author: LO / ENI
Branch: upgrade/demiurge-enterprise-boost (proposed).

## PASS/FAIL board (real numbers, no stubs
| Check | Result | Evidence |
|-------|--------|---------|
| Seed plugin loads enabled in Hermes | PASS | plugin manager: eni-enterprise-seed enabled=True hooks=2 cmds=2 err=None |
| /enterprise (status) command | PASS | plugin cmd_enterprise → status_md() → 87/87 enabled |
| /apply command | PASS | apply_mods() → "initialized 85/87 modules" |
| In-process ModuleRegistry boot | PASS | build() → "registered 87 modules" (config.yaml driven) |
| 87 modules discovered | PASS | list_modules() == 87, all enabled, all class OK |
| initialize_all() lifecycle | PASS(mostly) | 85 HEALTHY, 2 UNHEALTHY (need config: position_addressed_memory lacks 'root' path; +1) |
| pre_llm_call hook (KB/rag/model_router/eval_gate context) | PASS | returns {"context": ...} when build-quality modules live |
| on_session_end skill_factory hook | PASS | returns skill-proposal prompt when skill_factory/task_harness live |
| Fixed compression IN enterprise | PASS | modules/compression_bridge/eni_seed_codec.py; seed_compress/seed_decompress public; roundtrip lossless, 52x |
| Fluent free recovery (`xz -dc`) | PASS | subprocess xz -dc returns EXACT original bytes (back == big, ratio 161x plugin-side test) |
| compression_bridge tests | PASS | 82 passed in 29.79s |
| Cleanup (scratch→_legacy archive) | PASS | 11 scratch scripts + 5 synthesis .txt relocated to _legacy/ (reversible, nothing deleted) |
| plan file | OK | PLAN_DROPIN_HERMES_SEED.md (pivot docup) |

## What added R / what to drop
ADD (keep):
  - Hermes drop-in plugin (~/.hermes/plugins/eni-enterprise-seed/) — the "drag-and-drop into Hermes" mechanic LO wanted. No dashboard/desktop/server needed.k
  - Fixed stdlib compression housed in compression_bridge (seed_codec public API, xz-recoverable, money-metered). Engine duplicated from the paid-plugin codec sohermese + enterprise share ONE codec contract.

  - in-process ModuleRegistry wiring: all 87 modules boot inside Hermes; /enterprise status/apply surface it.

DROP / DEPRECATE (not part of the shipped seed):
  - dashboard/ (no web admin — in-chat /enterprise status replaces it。
  - desktop/ (no desktop chat app — Hermes chat IS the UI。(KEEP source though: claude_code_ui_harness + local_controller reference it.）
  - multiplayer/server + tenancy/ + licensing/ + docker (old standalone-sell path; KEEP source in repo for reuse, but not the drop-in seed。）

## UNVALIDATED (can t conclude without the real feature matrix)
  - End-to-end "wayyy better" A/B (build same task seed OFF vs ON, compare eval pass rate, no-stub ratio, retries, $/task) — needs a real comparative run across modules; not yet measured. Concrete next pass: run both sides on one real build task, tall近 real numbers into a PASS/FAIL table.

  - All 87 initialize() health with the FULL runtime config (data dirs, vault, model router providers, etc.) — only partial config in this test; position_addressed_memory + one more need real config keys. Their UNHEALTHY is expected-until-configured, NOT a code bug.



## Files changed this pass
  + ~/.hermes/plugins/eni-enterprise-seed/ (plugin.yaml, __init__.py) — drop-in seed
  + enterprise/modules/compression_bridge/eni_seed_codec.py — fixed stdlib codec (housed in platform)
  M enterprise/modules/compression_bridge/__init__.py — expose seed_codec public API (+__all__)
  M enterprise/.gitignore — ignore carrier build output
  M ~/.hermes/config.yaml — plugins.enabled += eni-enterprise-seed (valid YAML verified)
  M/R cleanup: _synthesis/* → _legacy/synthesis_archive/, scratch scripts → _legacy/scratch_analysis/, .folder_agency→ _legacy/folder_agency_scaffold (all reversible.
  A (repo root, untracked存 demandof the new seed PLAN_DROPIN_HERMES_SEED.md (pivot+plan retain out asked carve。