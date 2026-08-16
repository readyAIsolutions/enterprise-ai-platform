# Live free-model pool (ENI swarm)

Probe command — find which free OpenRouter slugs actually answer RIGHT NOW:
```
OPENROUTER_FREE_POOL="tencent/hy3:free qwen/qwen3-coder:free meta-llama/llama-3.3-70b-instruct:free qwen/qwen2.5-72b-instruct:free google/gemma-4-31b-it:free deepseek/deepseek-r1:free" \
  bash ~/.hermes/skills/devops/parallel-build-orchestration/scripts/probe_free_models.sh
```

Seed the rotating picker (one slug per line):
```
mkdir -p ~/.cache/eni_parallel
printf 'tencent/hy3:free\nqwen/qwen3-coder:free\nmeta-llama/llama-3.3-70b-instruct:free\nqwen/qwen2.5-72b-instruct:free\n' > ~/.cache/eni_parallel/live_models.txt
```

Last-known pool (probe 2026-07-09; DRIFTS — re-probe before a big launch):
- LIVE:  tencent/hy3:free
         qwen/qwen3-coder:free
         meta-llama/llama-3.3-70b-instruct:free
         qwen/qwen2.5-72b-instruct:free
- DEAD THIS PASS: google/gemma-4-31b-it:free  (429/404)
                 deepseek/deepseek-r1:free     (429/404)

NOTE: the probe ITSELF burns free-model quota; a probe "pass" can still 429 the
first swarm agent on that slug. Treat a post-probe 429 as "retry / relocate",
not "model dead". See parallel-build-orchestration §FREE-MODEL RATE LIMITS.
