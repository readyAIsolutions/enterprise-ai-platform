# ENI Module Reference (all modules)

_Auto-generated: python3 scripts/gen_module_docs.py — one page per module in docs/modules/._

## Knowledge Intake
| Module | Purpose | Doc |
|--------|---------|-----|
| `ai_memory_hierarchy` | Layered memory model for agents (working/short/long) from AI-memory transcripts. | [docs/modules/ai_memory_hierarchy.md](modules/ai_memory_hierarchy.md) |
| `ai_systems_thinking` | Feedback loops, coupling and systems lens for AI feature design. | [docs/modules/ai_systems_thinking.md](modules/ai_systems_thinking.md) |
| `paper_feeds` | Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export. | [docs/modules/paper_feeds.md](modules/paper_feeds.md) |
| `second_brain` | Knowledge capture/resurfacing engine: nodes+links, spaced repetition, concept query, compounding. | [docs/modules/second_brain.md](modules/second_brain.md) |

## Agent Workflow
| Module | Purpose | Doc |
|--------|---------|-----|
| `agentic_rag` | Agent-driven retrieval-augmented generation workflow. | [docs/modules/agentic_rag.md](modules/agentic_rag.md) |
| `ai_coding_harness` | Harness for coding-agent output: run, verify, audit. | [docs/modules/ai_coding_harness.md](modules/ai_coding_harness.md) |
| `context_routing` | Task -> {read/skip/skills} routing table with token-budget guard. | [docs/modules/context_routing.md](modules/context_routing.md) |
| `group_chat_orchestration` | Multi-participant AI+human group chat: round-robin, moderator focus, escalation, handoffs. | [docs/modules/group_chat_orchestration.md](modules/group_chat_orchestration.md) |
| `human_in_the_loop` | Human review/approval gates inside agent runs. | [docs/modules/human_in_the_loop.md](modules/human_in_the_loop.md) |
| `shared_workspace` | Live multi-editor workspace: lock, merge-safe write, history, redact-before-share. | [docs/modules/shared_workspace.md](modules/shared_workspace.md) |

## Build Quality
| Module | Purpose | Doc |
|--------|---------|-----|
| `automation_triage` | What-to-automate ladder, wrong-layer detection, one-client scoping guard. | [docs/modules/automation_triage.md](modules/automation_triage.md) |
| `codegen_audit` | Audit generated code for correctness, security and quality signals. | [docs/modules/codegen_audit.md](modules/codegen_audit.md) |
| `engineering_tradeoff` | Structured tradeoff scoring for engineering decisions. | [docs/modules/engineering_tradeoff.md](modules/engineering_tradeoff.md) |
| `production_agent_hardening` | Demo->production hardening linter across 8 scored dimensions + systems loops. | [docs/modules/production_agent_hardening.md](modules/production_agent_hardening.md) |
| `production_hardening` | Operational hardening checks for shipping an agent into production. | [docs/modules/production_hardening.md](modules/production_hardening.md) |

## Domain
| Module | Purpose | Doc |
|--------|---------|-----|
| `ai_education_guardrails` | Guardrails for using AI in education (anti-cheating, learning-first). | [docs/modules/ai_education_guardrails.md](modules/ai_education_guardrails.md) |
| `model_psychometrics` | Probe/evaluate model reasoning attributes (psychometric-style evals). | [docs/modules/model_psychometrics.md](modules/model_psychometrics.md) |
| `procurement_bid_automation` | Automate procurement/RFP bid intake, scoring and responses. | [docs/modules/procurement_bid_automation.md](modules/procurement_bid_automation.md) |
| `video_as_code` | Represent/edit long-form video (animations) as code/scripts. | [docs/modules/video_as_code.md](modules/video_as_code.md) |

## Legacy Core
| Module | Purpose | Doc |
|--------|---------|-----|
| `a2a` | ENI A2A Module -- Agent-to-Agent protocol (Google A2A style). | [docs/modules/a2a.md](modules/a2a.md) |
| `agent_catalog` | ENI Agent Catalog Module -- unified specialist-agent registry. | [docs/modules/agent_catalog.md](modules/agent_catalog.md) |
| `agent_coordination` | Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling, | [docs/modules/agent_coordination.md](modules/agent_coordination.md) |
| `agent_core` | Claude Code Core — Enterprise Platform Kernel Module v2.0.0 | [docs/modules/agent_core.md](modules/agent_core.md) |
| `agent_graph` | ENI Agent Graph Module — langgraph-style stateful agent graph orchestration. | [docs/modules/agent_graph.md](modules/agent_graph.md) |
| `agent_infra` | Claude Code Superior — Infrastructure Module v1.0.0 | [docs/modules/agent_infra.md](modules/agent_infra.md) |
| `agent_os` | Enterprise Agent OS Module — a unified AI agent operating system. | [docs/modules/agent_os.md](modules/agent_os.md) |
| `agent_tools` | ENI Enterprise — Claude Code Tools Module v2.0.0 | [docs/modules/agent_tools.md](modules/agent_tools.md) |
| `ai_defense` | ENI Enterprise AI Defense OS Module. | [docs/modules/ai_defense.md](modules/ai_defense.md) |
| `artifact_pipeline` | Artifact Pipeline — navigate & organize all creative works (no LLM). | [docs/modules/artifact_pipeline.md](modules/artifact_pipeline.md) |
| `autonomous_agent_runtime` | ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction. | [docs/modules/autonomous_agent_runtime.md](modules/autonomous_agent_runtime.md) |
| `compliance` | ENI Enterprise Compliance OS Module. | [docs/modules/compliance.md](modules/compliance.md) |
| `compression_bridge` | Enterprise Platform — Compression Bridge Module v3.0.0 | [docs/modules/compression_bridge.md](modules/compression_bridge.md) |
| `cost_meter` | Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4). | [docs/modules/cost_meter.md](modules/cost_meter.md) |
| `customer_experience` | Customer Experience OS Module. | [docs/modules/customer_experience.md](modules/customer_experience.md) |
| `developer_experience` | Developer Experience OS Module | [docs/modules/developer_experience.md](modules/developer_experience.md) |
| `disaster_recovery` | Disaster Recovery OS Module | [docs/modules/disaster_recovery.md](modules/disaster_recovery.md) |
| `enterprise_validation` | Enterprise Validation & Certification OS — Module Entry Point | [docs/modules/enterprise_validation.md](modules/enterprise_validation.md) |
| `eval_gate` | ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline). | [docs/modules/eval_gate.md](modules/eval_gate.md) |
| `gateway` | ENI Multi-Gateway Remote Control & Automations Module | [docs/modules/gateway.md](modules/gateway.md) |
| `guardrails` | ENI Guardrails OS Module. | [docs/modules/guardrails.md](modules/guardrails.md) |
| `hermes_controller` | Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent. | [docs/modules/hermes_controller.md](modules/hermes_controller.md) |
| `icm` | ICM (Interpretable Context Methodology) — skill/prompt-engineering layer. | [docs/modules/icm.md](modules/icm.md) |
| `innovation_rd` | Innovation R&D OS Module | [docs/modules/innovation_rd.md](modules/innovation_rd.md) |
| `kb_bridge` | ENI Knowledge Base OS Module | [docs/modules/kb_bridge.md](modules/kb_bridge.md) |
| `knowledge_graph` | Knowledge Graph OS Module | [docs/modules/knowledge_graph.md](modules/knowledge_graph.md) |
| `llmops_trace` | ENI LLMOps Trace OS Module — local, offline LLM tracing & observability. | [docs/modules/llmops_trace.md](modules/llmops_trace.md) |
| `look_and_feel` | Enterprise Platform — Look & Feel Registry Module v1.0.0 | [docs/modules/look_and_feel.md](modules/look_and_feel.md) |
| `mcp_tools` | ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer. | [docs/modules/mcp_tools.md](modules/mcp_tools.md) |
| `memory` | ENI Agent Memory OS Module. | [docs/modules/memory.md](modules/memory.md) |
| `mlops_lifecycle` | ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management | [docs/modules/mlops_lifecycle.md](modules/mlops_lifecycle.md) |
| `model_miner` | Enterprise Model Miner OS Module — scan/rip local model training into the KB. | [docs/modules/model_miner.md](modules/model_miner.md) |
| `model_router` | ENI Model Router OS Module — enterprise model-routing / fallback gateway. | [docs/modules/model_router.md](modules/model_router.md) |
| `model_security` | ENI Model Security OS Module. | [docs/modules/model_security.md](modules/model_security.md) |
| `observability` | Observability — real, consolidated fleet health + Prometheus export. | [docs/modules/observability.md](modules/observability.md) |
| `privacy_data` | Privacy & Data Governance OS Module | [docs/modules/privacy_data.md](modules/privacy_data.md) |
| `prompt_context` | Prompt & Context Management OS Module | [docs/modules/prompt_context.md](modules/prompt_context.md) |
| `prompt_guard` | Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding. | [docs/modules/prompt_guard.md](modules/prompt_guard.md) |
| `rag` | Production RAG System — Enterprise-grade Retrieval-Augmented Generation. | [docs/modules/rag.md](modules/rag.md) |
| `release_change` | Release & Change Management OS Module | [docs/modules/release_change.md](modules/release_change.md) |
| `research_verification` | Research & Verification OS — Enterprise Platform Kernel Module v1.0.0 | [docs/modules/research_verification.md](modules/research_verification.md) |
| `response_hardening` | ENI Response Hardening module. | [docs/modules/response_hardening.md](modules/response_hardening.md) |
| `response_ops` | ENI Response Ops Module — self-healing fleet supervisor + ICM routing hook. | [docs/modules/response_ops.md](modules/response_ops.md) |
| `safety_governance` | ENI Enterprise — Safety & Governance OS v1.0.0 | [docs/modules/safety_governance.md](modules/safety_governance.md) |
| `secret_broker` | Enterprise Secret Broker OS Module — local-first secret handling. | [docs/modules/secret_broker.md](modules/secret_broker.md) |
| `secret_rotation` | ENI Enterprise Secret Rotation OS Module. | [docs/modules/secret_rotation.md](modules/secret_rotation.md) |
| `semantic_memory` | ENI Semantic Memory OS Module. | [docs/modules/semantic_memory.md](modules/semantic_memory.md) |
| `skill_factory` | ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution. | [docs/modules/skill_factory.md](modules/skill_factory.md) |
| `swarm_bridge` | ENI Swarm Enterprise Module v5.0.0 | [docs/modules/swarm_bridge.md](modules/swarm_bridge.md) |
| `swarm_network` | Swarm Network Optimization OS — Enterprise Module | [docs/modules/swarm_network.md](modules/swarm_network.md) |
| `task_harness` | ENI Task Harness OS Module | [docs/modules/task_harness.md](modules/task_harness.md) |
| `threat_model` | ENI Threat Model OS Module. | [docs/modules/threat_model.md](modules/threat_model.md) |
| `triadforge` | ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module. | [docs/modules/triadforge.md](modules/triadforge.md) |
| `unified_inbox` | Enterprise Platform Unified Inbox module package. | [docs/modules/unified_inbox.md](modules/unified_inbox.md) |
| `unified_work_system` | ENI Unified Work System Module | [docs/modules/unified_work_system.md](modules/unified_work_system.md) |
| `universal_score` | ENI Universal Build Score module. | [docs/modules/universal_score.md](modules/universal_score.md) |
| `vuln_scanner` | ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style). | [docs/modules/vuln_scanner.md](modules/vuln_scanner.md) |
| `youtube_transcripts` | YouTube transcript puller with PIA VPN IP rotation. | [docs/modules/youtube_transcripts.md](modules/youtube_transcripts.md) |

