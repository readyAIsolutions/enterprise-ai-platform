---
name: eni-always-enterprise
description: >-
  LO's STANDING, non-negotiable directive (use ALWAYS, every session): whenever operating
  Hermes, ALWAYS use omega/ENI compression and leverage the ENI Enterprise ecosystem
  (its modules, facades, and tooling) instead of reinventing or working raw. Covers the
  verified omega-compression entrypoint and the full list of enterprise modules/facades to
  prefer. Load this first whenever starting any session or task where LO is present.
---

# ENI ALWAYS-ENTERPRISE — Standing Directive (use in EVERY session)

LO: "also always use omega compression and everything else from enterprise whenever i use
hermes ... save this this is very important usr it ALWAYS build skills for it to be used
ALWAYS."

This is a permanent, non-negotiable working-mode directive. It applies from the start of
every session and to every task, not just when explicitly mentioned.

## RULE 1 — ALWAYS use omega / ENI compression
When you handle tool output, prompts, contexts, logs, RAG chunks, or any large text while
working with Hermes, route heavy payloads through the ENI compression pipeline to cut
token use, just as LO built it.

VERIFIED working entrypoint (round-trip confirmed 2026-08-03):
```
import sys
sys.path.insert(0, "/home/hunter/Desktop/Projects/ENI_Swarm/Compression")
from eni_compression import compress, decompress
result = compress(text)          # -> dict with 'carrier', 'wenyan', 'ratio', ... 
original = decompress(result['carrier'])
```
- `compress()` returns a dict (see keys: carrier, carrier_name, wenyan, glyph_compressed,
  original_size, compressed_size, ratio, stats). Carrier PNGs are written under
  /home/hunter/Desktop/eni_compression/carriers/.
- Round-trip is lossless ('decompressed == input' verified True).
- Fallback path if that import fails: the skills `eni-swarm-compression` full reference
  (workers/compression_worker) and `~/Desktop/eni_compression` standalone.

## RULE 2 — ALWAYS prefer ENI Enterprise modules over reinventing
The platform at ~/Desktop/Enterprise Builder/enterprise/ ships kernel-native @module
facades. Use them by default for the capability instead of writing bespoke code:
- model_security  — SecurityPipeline/InputSanitizer/PromptInjectionShield/JailbreakShield/
  OutputValidator/SecurityGate/SecurityHealth/RedTeamBench/DeploymentSecurityGate
- eval_gate       — offline eval metrics: AnswerRelevancy/Faithfulness/Toxicity/
  HallucinationProxy/RefusalDetector/JailbreakGuard + EvalGate/EvalRunner
- guardrails      — validate/refix loop: NoPII/NoToxic/JSONSchema/Profanity/Length/Regex/
  NoPromptInjection + GuardRailRunner
- compliance      — OWASP LLM Top 10 / NIST AI RMF / MITRE ATLAS control mapping + coverage
- threat_model    — MITRE ATLAS + STRIDE register, risk=likelihood*impact, severity
- vuln_scanner    — garak-style offline probes (prompt extraction, jailbreak, PII, toxicity)
- secret_rotation — hash-only credential hygiene, rotation/expiry/breach
- agent_graph     — stateful agent graphs + checkpoints + supervisor
- a2a             — Agent-to-Agent (AgentCard/Task/handoff)
- llmops_trace    — local LLM observability (span tree, latency percentiles)
- memory          — mem0-style long-term memory
- mcp_tools       — FastMCP-style tool registry
- semantic_memory — vector-like retrieval
Each exposes a `<X>Facade` (e.g. ComplianceFacade, ThreatModelFacade). Tests: modules/<x>/tests.
- triadforge — TRIAD FORGE white/grey/black security hacker box (enterprise module
  modules/triadforge + Hermes bridge ~/.hermes/scripts/triadforge.py). Run scans on LO's
  OWN local targets: scan-web/scan-source/findings/sarif/kb-push (funnels findings to ENI KB).

## RULE 3 — Keep skills built so this is ALWAYS applied
Proactively maintain (patch/create) skills capturing reusable procedures so LO never has to
re-explain. After any non-trivial task, save the approach as a skill (LO explicitly expects
this — see "Expects proactive skill maintenance every task").

## Verify-at-start checklist
1. If about to process large text/contexts -> consider routing through eni compression.
2. If a task maps to an existing enterprise module/facade -> use it, don't reinvent.
3. If you discovered a new working procedure -> save/update a skill.
