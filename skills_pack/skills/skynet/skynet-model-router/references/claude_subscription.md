# Riding the Signed-In Claude Code Subscription

When LO wants code to "use my signed-in subscription" (his Pro/Max Claude
plan on this box), there are two programmatic paths. The `claude_core`
package (Hermes `agent/claude_core/`, DEMIURGE `engine/intelligence/claude_core/`)
implements both behind a `get_default_client()` factory that picks
`ClaudeCliClient` (CLI) > `ClaudeClient` (OAuth) > `ClaudeClient` (api_key).

## Path 1 — CLI subprocess (RELIABLE, use this)

The `claude` CLI is already authenticated against the subscription and is
what serves this very session. Shell out to it:

```
claude --print "<prompt>" --output-format stream-json --verbose
# or:  claude -p "<prompt>" --output-format stream-json --verbose
```

HARD RULE: with `--output-format stream-json` you MUST also pass
`--verbose` (and `--print`/`-p`), otherwise it errors:
`When using --print, --output-format=stream-json requires --verbose`.

Parse the stdout as newline-delimited JSON events:
- `{"type":"assistant", "message":{"content":[...]}}` — blocks of
  type `text` / `thinking` / `tool_use` (tool_use has `id`, `name`, `input`).
- `{"type":"result", "result":"<final text>", "usage":{...},
   "total_cost_usd": 0.055}` — the authoritative final text + token usage
  (`input_tokens`, `output_tokens`, `cache_creation_input_tokens`,
  `cache_read_input_tokens`) + real cost.

Prefer the `result` event's `result` string as the text; do NOT also append
the streamed assistant `text` block — that double-prints the same string.
Return shape: `{text, thinking, tool_calls, stop_reason, usage, cost_usd}`.

## Path 2 — OAuth bearer (raw HTTPS, finicky on this account)

Credentials live in `~/.claude/.credentials.json` under key `claudeAiOauth`:
`{accessToken, refreshToken, expiresAt, scopes}`. `scopes` includes
`user:inference` (API access granted). To call the Messages API:

- URL `https://api.anthropic.com/v1/messages`
- Header `authorization: Bearer *** Header `anthropic-beta: oauth-2025-04-20`
- Refresh when `expiresAt` nears: `POST https://api.anthropic.com/oauth/token`
  with body `grant_type=refresh_token&refresh_token=<rt>&client_id=<cid>`,
  `content-type: application/x-www-form-urlencoded`. Public client id:
  `9d1c250a-e61b-44d9-8a2f-2f18f3a6e6e2`. Write the refreshed blob back so
  the real CLI also benefits.

CAVEAT (observed 2026-07-09): on this box OAuth **authenticates** fine but
EVERY model — even `claude-3-5-haiku-20241022` — returns
`404 model not found`. The account's API catalog tier doesn't serve the
model strings, so the CLI path (Path 1) is the working route. OAuth code is
kept for accounts where the API catalog includes the models.

## Model default trap

The subscription serves the CLI's configured default model
(`claude-opus-4-6` on this box) — NOT dated API strings like
`claude-sonnet-4-20250514` (those 404). Pass `model=None` to let the CLI use
the subscription default; only name a model if you know the subscription
serves it. `get_default_client(model=None)` does exactly this.

## Notes

- The subscription does NOT use `ANTHROPIC_API_KEY` — that lives in
  `~/.hermes/.env` and is a separate (currently empty-credit) API key. The
  subscription uses `~/.claude/.credentials.json`.
- Subscription is a rolling 7-day window; utilization hit 0.96 here, after
  which calls get rate-limited. Keep automated Claude cross-checks tasteful
  until it resets.
- `claude_core` is a dependency-free raw-urllib reimplementation of the
  Claude Code architecture (ripped + integrated 2026-07-09): QueryEngine
  tool-loop, permissions, coordinator, memdir, compactor, cost-tracker.
