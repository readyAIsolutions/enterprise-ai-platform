# Deep-rip battery + honest value assessment (2026-08-05)

Pivot lesson from the first real batch: **what you rip matters more than that you rip.**
Two topic batteries, chosen by model strength — not one-size-fits-all.

## The value lesson (honest assessment, LO wants this)
- **Tiny models (0.5B–1.5B, Qwen family)** + 8 basic topics → **textbook-level, generic
  paragraphs. MEDIUM value.** They answer the topic but add nothing a good primer doesn't.
- **Strong models (free-router = DeepSeek-V3.1, 7B+ / strong cloud)** + 10 expert deep
  topics → **expert, novel, buildable content.** The LLM-security entry mapped each
  threat to OWASP LLM top-10 (LLM01/02/06/08/10/03/05/07), gave concrete layered
  mitigations (LlamaGuard, NeMo Guardrails, "the LLM never holds secrets" privilege
  separation, dynamic context injection, output JSON-schema validation), and even noted
  failure modes (GCG adversarial suffixes bypassing lexical classifiers) + self-correction.
- **So: don't burn time on deep rips of tiny models.** Use the basic battery for tiny
  models, the deep battery for strong models. The compounding asset is the PIPELINE +
  auto cloud-ripple, not the 0.5B textbook output.

## The two batteries
- `RIP_TOPICS` (8 basic) — tiny models (<~2B). Broad, shallow.
- `DEEP_TOPICS` (10 expert, demanding "senior staff engineer, no fluff" system prompt) —
  strong models. Topics: agent-runtime-architecture, multi-agent-design-patterns,
  llm-security-threat-model, retrieval-augmented-generation, agent-evaluation,
  gpu-inference-optimization, prompt-injection-defense, local-knowledge-compounding,
  agent-memory-architectures, mlops-for-agents. Each probe expects concrete tools,
  trade-offs, OWASP mappings — not generic prose.

## How it's invoked
- `eni_miner_boot.py --mine --deep` → expert battery. Without `--deep` → basic battery.
- `mine(deep=)` / `rip(deep=)` flags plumbed through ModelMiner facade.
- Deep rip results (sample word counts from free-router): agent-memory 608w,
  llm-security-threat-model 641w, multi-agent-design-patterns 646w,
  local-knowledge-compounding 740w.

## Smart cloud-ripple topic derivation
- New `classification.py` `classify_topic()` derives a stable KB topic from the ACTUAL
  prompt (security/infrastructure/engineering/data-science/mcp-lsp/prompting/devops/
  testing + subject fallback) instead of a generic label. 5 unit tests.
- Means every cloud call auto-banks knowledge organized by real subject, continuously,
  as LO works. Wired into BOTH free-router and OpenRouter return paths in
  `stand_router.chat()` behind `cloud_ripple: true` config flag.

## Result numbers
- Deep rip of free-router → **all 10 expert topics banked**. KB model-rip entries went
  24 → **39** (24 basic + 10 deep + 5 cloud_rip). Controller tests 23 → 28.
- Committed + pushed (`60b2097`).
