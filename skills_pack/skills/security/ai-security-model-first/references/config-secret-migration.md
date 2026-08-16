# Config secret migration — verified recipe (26 providers, live run)

Scenario: move plaintext provider API keys out of `~/.hermes/config.yaml` into a
safe store without breaking auth. Session produced a working migration and caught
two would-be-breaking bugs.

## The failure that must not be repeated

The first-draft migration replaced `api_key: sk-...` with
`api_key: {SECRET:PROVIDER_X_API_KEY}`. This would have **401'd every provider**:

- `{SECRET:...}` is a placeholder only the custom secret_broker/model_router
  understands.
- The real Hermes runtime reads `entry.get("api_key")` and sends its value
  verbatim as the Bearer token. No expansion. Confirmed in
  `hermes_cli/runtime_provider.py` (resolve path for `providers:` entries):

  ```python
  key_env = str(entry.get("key_env", "") or "").strip()
  resolved_api_key = os.getenv(key_env, "").strip() if key_env else ""
  if not resolved_api_key:
      resolved_api_key = str(entry.get("api_key", "") or "").strip()
  ```

  So `{SECRET:X}` as an api_key value → the literal string IS the token.

## Correct approach (what worked)

1. Write every key into `~/.hermes/.env` as `PROVIDER_<NAME>_API_KEY=<key>`.
   - Hermes natively loads `.env` at startup (`hermes_cli/env_loader.py`,
     `load_dotenv`); `agent/credential_pool.py` prefers `.env` over os.environ.
   - Keep `.env` at mode 600.
2. In config.yaml, for each provider, blank the inline `api_key` and add a sibling
   `key_env: PROVIDER_<NAME>_API_KEY` at the **same indentation** as api_key.
   - Bug seen: writing key_env at 3 spaces when api_key was at 4 → YAML unparseable.
   - Validate with `yaml.safe_load` after; assert the provider dict has the
     expected `api_key` (empty) + `key_env` keys.
3. Backup config.yaml (timestamped) before rewriting + a `--restore` flag that
   copies the latest backup back. Verified restore path.
4. Verify: dotenv-load `.env`, then for every `providers:` entry confirm a
   real-length key resolves. Sample result of this session's run:
   `providers with resolvable keys: 26 / 29` — the 3 skipped were the correct ones
   (cohere-local + free-router = `api_key: local` sentinel; openrouter =
   `api_key_env: OPENROUTER_API_KEY`, already env-based).

## Detection gotchas

- **Indentation matters**: provider blocks are `providers:` → 2-space name →
  4-space `api_key`. A regex anchoring the provider name at column 0 finds nearly
  nothing. Parse line-by-line: track current 2-space provider, read its 4-space
  `api_key` line.
- My first parser regex (`^  (\w[\w-]*):\n(?P<body>(?:[ \t]+.*\n?)*?)(?=...)`)
  **catastrophically backtracked** (timeout >180s on a 27 KB file). Replace any
  nested `(?:...\n?)*?` over a whole block with a plain line loop.
- Bug: setting `current_prov = None` before `results.append((prov, raw))` yielded
  all-None names. Capture the provider name into a local first.

## Durable broker master key

`SecretBroker.__init__` sets `_init_cipher`; if `HERMES_MASTER_KEY` env is unset
it uses `secrets.token_bytes(32)` (ephemeral). Consequence: `set_secret` then a
fresh instance → load fails (decrypt error) → starts empty; `list_secrets()` = 0.
Fix (verified): write `HERMES_MASTER_KEY=<base64 token>` into `.env`, clear the
stale store, re-seed from `.env` PROVIDER_* vars. After: fresh instance sees
`len(list_secrets()) == 26` and a `get_secret('PROVIDER_NVIDIA_API_KEY')`
round-trips at full 70-char length. Secrets then persist encrypted-at-rest.

## Final token location

Keys now live in three places, all local: `.env` (Hermes-native runtime auth),
encrypted broker `~/.hermes/secrets.enc` (durable at-rest copy), and the
timestamped config backup (rollback). config.yaml itself holds no plaintext keys.
