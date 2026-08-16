# claude_core — worked example module map

Ripped from the leaked Claude Code architecture spec (README at
`/home/hunter/demiurgenas_stash/demiurge/knowledge/desktop/Dev/claude-code-backup/README.md`).
Reimplemented as a portable, zero-dependency Python package.

## Package: `claude_core` (11 modules)

| Module | Ripped from Claude Code | Purpose |
|---|---|---|
| `client.py` | `services/api` + Anthropic SDK | `ClaudeClient`: Messages API over raw HTTPS (urllib), streaming SSE, extended thinking, prompt caching, vision, tool use. SDK optional. |
| `query_engine.py` | `QueryEngine.ts` (~46K lines) | `QueryEngine`: agentic tool-loop (stream→tool_calls→execute→re-inject→repeat), 429/5xx backoff, token accounting. |
| `tools.py` | `Tool.ts` | `Tool` base (input_schema + permission model) + `ToolRegistry`. |
| `permissions.py` | `hooks/toolPermission/` | `PermissionGate`: modes `bypassPermissions` / `auto` / `plan` / `default`. |
| `coordinator.py` | `coordinator/` + `AgentTool` + `TeamCreateTool` | `Coordinator` + `SubAgent`: spawn parallel sub-agents, synthesize reports. |
| `memory.py` | `memdir/` + `extractMemories` | `MemDir`: file-backed memory + heuristic auto fact-extraction (no model call). |
| `compactor.py` | `services/compact` + `/compact` | `Compactor`: keep last N turns, collapse the rest into a summary block. |
| `cost_tracker.py` | `cost-tracker.ts` + Hermes `usage_pricing` | `CostTracker` + `MODEL_PRICING` (USD per 1M tokens). |
| `tokenizer.py` | `tokenEstimation.ts` | `TokenEstimator`: heuristic char/4 + CJK bump. |
| `feature_flags.py` | bun:bundle feature flags | `FeatureFlags`: capability gating (DAEMON, COORDINATOR, COMPACT, …). |
| `__init__.py` | — | re-exports all. |

## Hermes integration (site-packages)

- Package: `~/.local/lib/python3.14/site-packages/agent/claude_core/`
- Helper: `agent/claude_code_integration.py` — `make_claude_engine()`,
  `HermesToolBridge`, `claude_compact()`, `claude_extract_memory()`,
  `claude_coordinator()`, process-wide `COST` tracker.
- Transport: `agent/transports/claude_code.py` — registers `api_mode:
  claude_code` (format-compatible with `anthropic_messages`, normalizes via
  claude_core). Registered in `agent/transports/__init__.py`
  `_discover_transports()`.
- Config (hand to user — config.yaml is write-protected):
  ```yaml
  model:
    provider: claude
    api_mode: claude_code
    model: claude-sonnet-4-20250514
  providers:
    claude:
      api_key_env: ANTHROPIC_API_KEY
  ```

## DEMIURGE integration (USB)

- Package copy: `/run/media/hunter/DEMIURGE/engine/intelligence/claude_core/`
- Client: `engine/intelligence/claude_client.py` — `DemiurgeClaude` with
  `score_news()`, `grade_trade()`, `self_review()`, `health_check()`
  (extended thinking + caching + cost). Reads `ANTHROPIC_API_KEY`.
- `scripts/llm_news_score.py` — new `score` action: in-process news scoring
  (replaces the old Claude Code CLI shellout); writes scores atomically +
  prints cost.
- `scripts/self_review.py` — `claude_cross_check()` (opt-in, gated by
  `DEMIURGE_USE_CLAUDE=1`).
- `engine/intelligence/trade_grader.py` — `grade_trade_claude()` (opt-in).

## Gotchas encountered

- `hermes_tools.read_file` inside `execute_code` returns `N|`-prefixed lines →
  corrupted two DEMIURGE files on a read→write round-trip. Recovered by
  stripping `^\s*\d+\|` per line. Use `patch` for appends instead.
- Live call reached Anthropic with a clean `400 credit balance too low` — proves
  the raw client is correct; only the account needs top-up.
