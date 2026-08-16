---
name: skynet-linux-router
description: >
  Linux-native SKYNET model router for Hermes. Discovers available models,
  maps task types to optimal provider/model combos, includes fallback chains,
  and self-healing patterns. Uses the working skynet package at
  ~/Desktop/SKYNET/skynet/ (all 25 modules verified) plus a standalone
  companion script that doesn't need the skynet package.
commands:
  - /skynet-route
  - /skynet-discover
  - /skynet-health
  - /skynet-test
version: 1
metadata:
  platform: linux
  verified: 2026-07-23
  skynet_version: 3.0.0
  modules: 23/23 HEALTHY
---

# SKYNET Linux Model Router

Routes Hermes tasks to the optimal model/provider on THIS Linux box.
Works both WITH the full `skynet` Python package (at `~/Desktop/SKYNET/skynet/`)
and WITHOUT it via the standalone companion script.

## Provider landscape (this box)

| Provider   | Model                   | Port/URL                            | Best For                   |
|-----------|-------------------------|-------------------------------------|----------------------------|
| airllm    | Mistral-7B (local)      | http://127.0.0.1:8913/v1           | simple, classification, formatting |
| claude-sub| claude-sonnet-5 (local) | http://127.0.0.1:8912/v1           | heavy reasoning, architecture, review |
| groq      | llama-3.3-70b            | https://api.groq.com/openai/v1     | creative, writing, brainstorming |
| cerebras  | gemma-4-31b              | https://api.cerebras.ai/v1         | general, qa, extraction |
| sambanova | DeepSeek-V3.2            | https://api.sambanova.ai/v1        | code, implementation, debugging |
| deepinfra | Qwen3.5-397B-A17B        | https://api.deepinfra.com/v1/openai| research, analysis, heavy reasoning |
| openrouter| auto (fallback)          | https://openrouter.ai/api/v1       | fallback, experimental |
| gemini    | gemini-pro (fallback)    | via Google API                     | last-resort fallback |

## Task routing matrix

Use this table to pick the right provider for each task type:

| Task Type        | Primary    | Fallback 1 | Fallback 2 | Fallback 3 |
|-----------------|------------|------------|------------|------------|
| code            | sambanova  | deepinfra  | claude-sub | groq       |
| implementation  | sambanova  | deepinfra  | claude-sub | groq       |
| refactoring     | sambanova  | claude-sub | deepinfra  | groq       |
| debugging       | sambanova  | claude-sub | deepinfra  | groq       |
| deep-reasoning  | sambanova  | claude-sub | deepinfra  | groq       |
| architecture    | claude-sub | sambanova  | deepinfra  | groq       |
| orchestration   | sambanova  | claude-sub | deepinfra  | groq       |
| review          | claude-sub | sambanova  | deepinfra  | groq       |
| security-audit  | claude-sub | deepinfra  | sambanova  | groq       |
| research        | deepinfra  | claude-sub | sambanova  | cerebras   |
| analysis        | deepinfra  | claude-sub | sambanova  | cerebras   |
| heavy-reasoning | claude-sub | deepinfra  | sambanova  | openrouter |
| creative        | groq       | sambanova  | cerebras   | openrouter |
| writing         | groq       | cerebras   | sambanova  | openrouter |
| brainstorming   | groq       | cerebras   | sambanova  | openrouter |
| general         | groq       | cerebras   | sambanova  | airllm     |
| qa              | cerebras   | groq       | sambanova  | airllm     |
| classification  | airllm     | cerebras   | groq       | —          |
| formatting      | airllm     | cerebras   | groq       | —          |
| extraction      | cerebras   | groq       | sambanova  | airllm     |
| fallback        | openrouter | gemini     | groq       | —          |

## Quick start: route a task without the skynet package

The companion script works standalone (no dependencies beyond Python 3 stdlib):

```bash
# Route a task
python3 ~/.hermes/skills/hermes-cli/skynet-linux-router/scripts/model_router.py route "fix the memory leak in the trading bot"

# Check provider health
python3 ~/.hermes/skills/hermes-cli/skynet-linux-router/scripts/model_router.py health

# Full test suite
python3 ~/.hermes/skills/hermes-cli/skynet-linux-router/scripts/model_router.py test

# One-line status
python3 ~/.hermes/skills/hermes-cli/skynet-linux-router/scripts/model_router.py status

# Discover all providers
python3 ~/.hermes/skills/hermes-cli/skynet-linux-router/scripts/model_router.py discover
```

## Using the full skynet package

The skynet package at `/home/hunter/Desktop/SKYNET/skynet/` has 25 modules,
all verified working on this Linux box. Set `SKYNET_ROOT` correctly:

```bash
# IMPORTANT: SKYNET_ROOT may be set to a stale path from a USB mount.
# Override it:
export SKYNET_ROOT=/home/hunter/Desktop/SKYNET
export PYTHONPATH=$SKYNET_ROOT:$PYTHONPATH

# Quick status
python3 -c "
import skynet
print(f'SKYNET v{skynet.__version__}')
from skynet.activate import activate
r = activate(verbose=True)
"

# Full health report
python3 -c "
from skynet.activate import health_check
healthy, report = health_check()
print(f'Status: {\"HEALTHY\" if healthy else \"DEGRADED\"}')
print(f'  Modules: {report[\"ok\"]}/{report[\"total\"]}')
print(f'  Time: {report[\"activation_time_ms\"]}ms')
"

# Model discovery (built-in, uses hardcoded catalog)
python3 -c "
from skynet.model_discovery import check_openrouter
models = check_openrouter()
print(f'{len(models)} known free models on OpenRouter')
for m in models[:10]:
    print(f'  {m}')
"

# Route a task with SmartRouter
python3 -c "
from skynet.smart_router import SmartRouter
router = SmartRouter()
task_type = router.classify_task('implement a Redis cache')
model, provider, fallbacks = router.route(task_type)
print(f'Task: implement a Redis cache')
print(f'Type: {task_type}')
print(f'Model: {model}')
print(f'Provider: {provider}')
print(f'Fallbacks: {fallbacks}')
"
```

## Self-healing fallback pattern

When a provider returns an error, follow this pattern:

```python
# Pseudo-pattern for Hermes tool calls
FALLBACK_ORDER = {
    "code": ["sambanova", "deepinfra", "claude-sub", "groq"],
    "reasoning": ["claude-sub", "sambanova", "deepinfra", "openrouter"],
    "creative": ["groq", "cerebras", "sambanova", "openrouter"],
    "general": ["groq", "cerebras", "sambanova", "airllm"],
}
UNHEALTHY = {}  # provider -> cooldown_until_timestamp

def get_model(hermes, task_type, task_prompt):
    """Get best available model with automatic fallback."""
    chain = FALLBACK_ORDER.get(task_type, FALLBACK_ORDER["general"])
    now = time.time()

    for provider in chain:
        if provider in UNHEALTHY and now < UNHEALTHY[provider]:
            continue  # skip cooling-down providers

        try:
            # Use Hermes's built-in model selection with this provider
            result = hermes.use(provider=provider, prompt=task_prompt)
            return result
        except (ConnectionError, TimeoutError, RateLimitError) as e:
            UNHEALTHY[provider] = now + 300  # 5-min cooldown
            continue  # try next fallback

    raise Exception("All providers exhausted — try again later")
```

### Hermes-specific fallback invocation

When calling Hermes models and the primary provider fails, use the provider
name directly as the next fallback:

```
# Primary attempt (code task → sambanova)
hermes chat --yolo -m DeepSeek-V3.2 --provider sambanova "fix the bug in..."

# Fallback 1 (code task → deepinfra)
hermes chat --yolo -m Qwen/Qwen3.5-397B-A17B --provider deepinfra "fix the bug in..."

# Fallback 2 (code task → claude-sub, local)
hermes chat --yolo -m claude-sonnet-5 --provider claude-sub "fix the bug in..."
```

## Model classification heuristic (from companion script)

The script classifies tasks by keyword matching, ordered most-specific-first:

1. **security** / vulnerability / exploit / harden → security-audit → claude-sub
2. **architecture** / design system / infrastructure → architecture → claude-sub
3. **orchestrate** / swarm / multi-agent → orchestration → sambanova
4. **debug** / traceback / seg fault → debugging → sambanova
5. **code** / function / implement / refactor / class / api → code → sambanova
6. **analyze** / examine / methodology → analysis → deepinfra
7. **research** / investigate / survey → research → deepinfra
8. **review** / audit / verify / validate → review → claude-sub
9. **creative** / brainstorm / ideate → creative → groq
10. **write** / draft / compose → writing → groq
11. **extract** / parse / scrape → extraction → cerebras
12. **classify** / category / label → classification → airllm
13. **format** / convert / transform → formatting → airllm
14. "**what is**" / "how many" / trivia → qa → cerebras
15. Everything else → general → groq

## Pitfalls

1. **SKYNET_ROOT env var**: The env may hold a stale path from a USB mount
   (`/run/media/hunter/DEMIURGENAS/demiurge/skynet`). Always validate with
   `os.path.isdir()` and fall back to `/home/hunter/Desktop/SKYNET`.

2. **airllm port 8913**: The local Mistral-7B server can go down. Check with
   `curl -s http://127.0.0.1:8913/v1/models` before routing to it. It has
   a small 8K context window — don't send long prompts to it.

3. **claude-sub port 8912**: The local Claude proxy needs to be running.
   It has 200K context but may throttle under heavy use (it rides LO's
   signed-in subscription).

4. **groq rate limits**: Groq's free tier has aggressive rate limiting.
   Use it for creative/writing tasks, not bulk processing.

5. **deepinfra latency**: Qwen3.5-397B is the slowest provider. Use it
   only for research/analysis tasks that benefit from the massive model.

6. **openrouter**: Don't hardcode model IDs with `:free` suffix — those
   are from the skynet package's catalog and may not be current. Use the
   Hermes provider config instead.

## Verification

Run the full test suite before trusting the router:

```bash
python3 ~/.hermes/skills/hermes-cli/skynet-linux-router/scripts/model_router.py test
```

Expected output: all 7 routing tests pass, 23/23 modules healthy, both
local providers reachable.