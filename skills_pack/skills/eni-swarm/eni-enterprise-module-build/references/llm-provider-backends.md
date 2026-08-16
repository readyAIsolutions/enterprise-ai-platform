# Resilient LLM provider backends (real backends, no stubs, offline-testable)

Session: rebuilt `agent_core` (`modules/agent_core/`) from `NotImplementedError`
backends into real, stdlib-only (`urllib.request`) provider transport.
Baseline 78 green -> 108 green (+30 tests, 0 failed). Durable class-level pattern
for *any* model-backend subsystem in the ENI enterprise repo.

## The shape that works

Three layers, cleanly separated:

1. **Transport** (`providers.py`): `ChatProvider` ABC + concrete providers.
   - `ProviderResponse` dataclass `{text, usage{prompt/completion/total}, model, latency}`.
   - `ChatProvider` ABC with `async complete(messages: list[dict], model, **kw) -> ProviderResponse`.
   - Push the blocking urllib call into a thread so the public API stays async:
     `await asyncio.to_thread(self._complete_sync, ...)`.
   - `OpenAICompatibleProvider(base_url, api_key_env)` — POSTs `<base>/v1/chat/completions`
     (append `/v1` if base_url doesn't end with it), `Authorization: Bearer`,
     parses `choices[0].message.content` + `usage`.
   - `AnthropicProvider(base_url, api_key_env)` — POSTs `<base>/v1/messages`,
     headers `x-api-key` + `anthropic-version: 2023-06-01`, system prompt pulled OUT
     of messages into a top-level `system` field, roles mapped to
     `user/assistant/tool` only, parses `content[]` text blocks + `input/output_tokens`.
   - `MockProvider` (scripted responses + scripted failure injection:
     `failures=[HttpError(429,...), ...]`) and `EchoProvider` (deterministic echo)
     for fully offline tests. Both injectable.

2. **Resilience**: `RetryPolicy(max_attempts, base_delay, max_delay, timeout, jitter,
   disable_sleep)` + `ResilientProvider(primary, fallback)`.
   - Exponential backoff on HTTP 429/5xx and on connect/timeout (`URLError`,
     `TimeoutError`, `HTTPError`). Cap attempts; on exhaustion raise `HttpError(status)`.
   - Fallback chaining (LiteLLM-style): `ResilientProvider.complete` catches any
     primary failure and delegates to `fallback`, or reraises if no fallback.

3. **Registry/factory**: `ProviderRegistry` (builder map, `get(name, config)` builds
   or returns cached instance) + top-level `get_provider(name, config)`.

## Keeping it 100% offline in tests

- **Injectable opener**: every HTTP provider takes `opener=` (any object with
  `open(request, timeout=...)` -> response with `.status`/`.read()`). A tiny
  `FakeOpener(responses=[...])` — list where an `Exception` entry is raised, a
  `FakeResponse(status, bytes)` returns normally — drives request-building,
  retry, timeout, and fallback tests with ZERO network (and lets you assert
  `opener.calls` to verify URL + JSON payload byte-for-byte).
- `RetryPolicy(disable_sleep=True)` so retry tests run instantly (no real sleep).
- Don't use the real-api-key path in most tests; inject `MockProvider`/`EchoProvider`
  into backends via the `provider=` constructor arg.

## Backend-class glue (kills the stubs cleanly)

Keep the original constructor compatible; add `provider=` + `api_key_env=` params.

```python
class OpenAICompatibleBackend(ModelBackend):
    def __init__(self, api_key=None, base_url=None, provider=None,
                 api_key_env="OPENAI_API_KEY"):
        self._provider = provider
        self._sim = SimulationBackend(fixed_response="[no API key configured; simulated]")

    def _resolve_provider(self):
        if self._provider: return self._provider
        key = self._api_key or os.environ.get(self._api_key_env)
        if not key: return None
        from .providers import OpenAICompatibleProvider   # lazy import avoids cycle
        self._provider = OpenAICompatibleProvider(base_url=self._base_url, api_key=key)
        return self._provider

    async def generate(self, messages, config, tools=None, stream=None):
        provider = self._resolve_provider()
        if provider is None:
            return await self._sim.generate(messages, config, tools, stream)  # fallback
        try:
            resp = await provider.complete([m.to_dict() for m in messages],
                                           config.model or self._DEFAULT_MODEL,
                                           temperature=config.temperature,
                                           max_output_tokens=config.max_output_tokens,
                                           tools=tools)
            return Message(role=MessageRole.ASSISTANT, content=resp.text,
                           metadata={"provider": "openai", "usage": resp.usage})
        except Exception as exc:
            logger.warning("... falling back to sim: %s", exc)
            return await self._sim.generate(messages, config, tools, stream)
```

Same shape for Anthropic. Rule: **when not configured (no key) or on provider failure,
fall back to the deterministic simulation backend** — the engine keeps working and
"honest health" means it never hard-crashes. Keep `count_tokens` as `len//4`.

## Pitfalls that cost time this session

- **Implement EVERY abstract method in the new backend class.** After replacing a
  stub, leaving out `count_tokens/supports_tools/supports_streaming` made
  instantiation raise `TypeError: Can't instantiate abstract class ...` — wait for
  that specific error, it's the fastest signal you forgot a method.
- **`import urllib.error` is separate.** `urllib.request` does NOT bring in
  `urllib.error.URLError/HTTPError`; import both explicitly or the except-clause
  silently never matches and your retry-on-network-error tests fail.
- Dialing `max_tokens` param: OpenAI prefers `max_tokens` / `max_output_tokens`;
  Anthropic REQUIRES `max_tokens`. Pass both names defensively via kwargs.
- Expose new names in BOTH the module `__init__.py` imports AND `__all__`, or
  `hasattr(module, name)` / `from module import name` tests fail.
- Fresh-instance caching in the registry: use the instance map but skip caching when
  tests pass `{"_fresh": True}` if you want a clean builder each time.

## Verification recipe

```
cd ~/Desktop/Enterprise\ Builder/enterprise
python3 -m pytest modules/<mod> -q -p no:cacheprovider           # baseline first
# ... then whole module again after edits -> prove no regression
grep -rn "NotImplementedError" modules/<mod>/*.py                # only intentional ABC abstracts
```

Report real numbers (baseline -> new, total passed/failed) and confirm you only
touched your own module's files (the repo is a shared parallel-swarm workspace;
many unrelated `M`/`??` files from other workers will be present — don't claim them).
