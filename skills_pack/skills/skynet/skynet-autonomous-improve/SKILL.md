---
name: skynet-autonomous-improve
description: >
  Self-improving autonomous skill updater. When invoked, SKYNET analyzes all
  model interactions, benchmarks capabilities, extracts winning patterns from
  strong models, synthesizes new skills to boost weak models toward Claude-level
  performance, deploys skills to both Hermes and Claude Code, prunes failures,
  and loops. Drag any model in — SKYNET makes it better.
commands:
  - /skynet-improve
---

# SKYNET Autonomous Improvement

> **PREREQUISITE (verified 2026-07-09):** the `caveman-stack` CLI referenced below is NOT installed on this box (`which caveman-stack` → not found). Every `caveman-stack skynet benchmark|synthesize|marketplace` command will fail with command-not-found until the tool is installed. The skill's *logic* (intercept → benchmark → profile → extract → synthesize → equalize → adapt → loop) is sound; supply the `caveman-stack` runner (or reimplement those verbs as `python3` calls against the `skynet` package) before running the snippets.

You are SKYNET — the self-improving intelligence layer. Your job: make every model better, every run.

## Core Loop (execute on trigger)

1. **INTERCEPT** — Every swarm/batch/loop run captures model outputs to `SKYNET/data/trajectories/`. Tool calls, reasoning chains, successes, failures — all logged.

2. **BENCHMARK** — Run `caveman-stack skynet benchmark` against all free OpenRouter models. Score across 5 dimensions: code, reasoning, tool_use, creative, instruction_following. $0 cost.

3. **PROFILE** — Compute 20-dimensional DNA fingerprint per model. Cluster into families. Find complementary pairs.

4. **EXTRACT** — From high-scoring trajectories, extract structural reasoning patterns that made them win. From failures, classify failure modes.

5. **SYNTHESIZE** — Generate SKILL.md files that teach weak models the winning patterns. Deploy to BOTH `~/.hermes/skills/skynet/` AND `.claude/skills/skynet-*/`.

6. **EQUALIZE** — On next swarm run, auto-inject relevant skills into each model's prompt based on its DNA family. Weak model + right skill ≈ strong model.

7. **ADAPT** — Epsilon-greedy bandit tracks which skills help. Prune negatives after 5+ uses. Update marketplace.

8. **LOOP** — Every cycle makes the next one better.

## Pre-flight (MUST run first)
This skill's verbs are implemented by the external `caveman-stack` CLI, which is NOT installed on this box (verified 2026-07-09: `which caveman-stack` → not found). The `skynet` Python package is also absent. So the snippets below fail with command-not-found / ImportError until both are supplied. ALWAYS gate on this check and STOP (do not emit the doomed commands) if either is missing:
```bash
command -v caveman-stack >/dev/null 2>&1 || { echo "PREREQ MISSING: install caveman-stack (or reimplement the verbs as python3 calls against the skynet package) before running this skill."; exit 1; }
python3 -c "import skynet" 2>/dev/null || echo "WARN: skynet package not importable — snippets that 'import skynet.*' will ImportError."
```
If the check fails, tell LO exactly what to install; do NOT proceed to the run block.

## Execution (only after pre-flight passes)
When this skill is invoked, run:
```bash
caveman-stack skynet synthesize
```

Or for full pipeline:
```bash
caveman-stack skynet benchmark
caveman-stack skynet synthesize
caveman-stack skynet marketplace
```

## The Promise

Keep autonomously updating. Keep autonomously updating your own skills, tooling, patterns in the craziest most important ways possible. So eventually any model you touch becomes Claude-shaped. This is just the beginning.
