## Modules — complete reference (all modules)

Every platform module (auto-discovered by the Platform Kernel):
one page per module in [`docs/modules/`](docs/modules/) and the full grouped index in [`docs/MODULES_REFERENCE.md`](docs/MODULES_REFERENCE.md).

### Knowledge Intake
| Module | Purpose |
|--------|---------|
| `ai_memory_hierarchy` | Layered memory model for agents (working/short/long) from AI-memory transcripts. |
| `ai_systems_thinking` | Feedback loops, coupling and systems lens for AI feature design. |
| `paper_feeds` | Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging, JSON/CSV export. |
| `second_brain` | Knowledge capture/resurfacing engine: nodes+links, spaced repetition, concept query, compounding. |

### Agent Workflow
| Module | Purpose |
|--------|---------|
| `agentic_rag` | Agent-driven retrieval-augmented generation workflow. |
| `ai_coding_harness` | Harness for coding-agent output: run, verify, audit. |
| `context_routing` | Task -> {read/skip/skills} routing table with token-budget guard. |
| `group_chat_orchestration` | Multi-participant AI+human group chat: round-robin, moderator focus, escalation, handoffs. |
| `human_in_the_loop` | Human review/approval gates inside agent runs. |
| `shared_workspace` | Live multi-editor workspace: lock, merge-safe write, history, redact-before-share. |

### Build Quality
| Module | Purpose |
|--------|---------|
| `automation_triage` | What-to-automate ladder, wrong-layer detection, one-client scoping guard. |
| `codegen_audit` | Audit generated code for correctness, security and quality signals. |
| `engineering_tradeoff` | Structured tradeoff scoring for engineering decisions. |
| `production_agent_hardening` | Demo->production hardening linter across 8 scored dimensions + systems loops. |
| `production_hardening` | Operational hardening checks for shipping an agent into production. |

### Domain
| Module | Purpose |
|--------|---------|
| `ai_education_guardrails` | Guardrails for using AI in education (anti-cheating, learning-first). |
| `model_psychometrics` | Probe/evaluate model reasoning attributes (psychometric-style evals). |
| `procurement_bid_automation` | Automate procurement/RFP bid intake, scoring and responses. |
| `video_as_code` | Represent/edit long-form video (animations) as code/scripts. |

### Legacy Core
| Module | Purpose |
|--------|---------|
| `a2a` | ENI A2A Module -- Agent-to-Agent protocol (Google A2A style). |
| `agent_catalog` | ENI Agent Catalog Module -- unified specialist-agent registry. |
| `agent_coordination` | Agent Communication & Coordination OS — Multi-agent orchestration, task scheduling, |
| `agent_core` | Claude Code Core — Enterprise Platform Kernel Module v2.0.0 |
| `agent_graph` | ENI Agent Graph Module — langgraph-style stateful agent graph orchestration. |
| `agent_infra` | Claude Code Superior — Infrastructure Module v1.0.0 |
| `agent_os` | Enterprise Agent OS Module — a unified AI agent operating system. |
| `agent_tools` | ENI Enterprise — Claude Code Tools Module v2.0.0 |
| `agentic_workflow_builder` | agentic_workflow_builder — compose agentic workflows (Claude Code + Cursor). |
| `ai_defense` | ENI Enterprise AI Defense OS Module. |
| `artifact_pipeline` | Artifact Pipeline — navigate & organize all creative works (no LLM). |
| `autonomous_agent_runtime` | ENI Autonomous Agent Runtime Module -- Multi-provider LLM abstraction. |
| `claude_code_ui_harness` | Claude Code UI Harness — Enterprise Module wrapper. |
| `compliance` | ENI Enterprise Compliance OS Module. |
| `compression_bridge` | Enterprise Platform — Compression Bridge Module v3.0.0 |
| `cost_meter` | Cost Meter — per-tenant cost metering + fractional-reasoning policy (B3 + C4). |
| `custom_agent_workflows` | custom_agent_workflows — build your OWN AI coding workflows as a module. |
| `customer_experience` | Customer Experience OS Module. |
| `developer_experience` | Developer Experience OS Module |
| `disaster_recovery` | Disaster Recovery OS Module |
| `enterprise_validation` | Enterprise Validation & Certification OS — Module Entry Point |
| `error_correction` | error_correction platform module. |
| `eval_gate` | ENI Eval Gate OS Module — automated LLM evaluation gates (local & offline). |
| `folder_agency_system` | folder_agency_system — a folder/org-structure system that organizes an AI |
| `gateway` | ENI Multi-Gateway Remote Control & Automations Module |
| `guardrails` | ENI Guardrails OS Module. |
| `hermes_controller` | Enterprise Hermes Controller OS Module — autonomous controller for Hermes Agent. |
| `icm` | ICM (Interpretable Context Methodology) — skill/prompt-engineering layer. |
| `innovation_rd` | Innovation R&D OS Module |
| `kb_bridge` | ENI Knowledge Base OS Module |
| `knowledge_graph` | Knowledge Graph OS Module |
| `llmops_trace` | ENI LLMOps Trace OS Module — local, offline LLM tracing & observability. |
| `look_and_feel` | Enterprise Platform — Look & Feel Registry Module v1.0.0 |
| `mcp_tools` | ENI MCP Tools Module — FastMCP-style tool registry & MCP serving layer. |
| `memory` | ENI Agent Memory OS Module. |
| `mlops_lifecycle` | ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agent Experiment Lifecycle Management |
| `model_miner` | Enterprise Model Miner OS Module — scan/rip local model training into the KB. |
| `model_router` | ENI Model Router OS Module — enterprise model-routing / fallback gateway. |
| `model_security` | ENI Model Security OS Module. |
| `multiplayer_agent_triage` | multiplayer_agent_triage — a Platform Kernel module for triaging problems and |
| `observability` | Observability — real, consolidated fleet health + Prometheus export. |
| `position_addressed_memory` | Position-addressed memory — *folder-as-memory* for AI context. |
| `prd_audit` | prd_audit — PRD-gated build workflow: write the PRD, audit it with a second |
| `privacy_data` | Privacy & Data Governance OS Module |
| `prompt_context` | Prompt & Context Management OS Module |
| `prompt_guard` | Enterprise Prompt Guard OS Module — injection / jailbreak / policy guarding. |
| `rag` | Production RAG System — Enterprise-grade Retrieval-Augmented Generation. |
| `release_change` | Release & Change Management OS Module |
| `research_verification` | Research & Verification OS — Enterprise Platform Kernel Module v1.0.0 |
| `response_hardening` | ENI Response Hardening module. |
| `response_ops` | ENI Response Ops Module — self-healing fleet supervisor + ICM routing hook. |
| `safety_governance` | ENI Enterprise — Safety & Governance OS v1.0.0 |
| `secret_broker` | Enterprise Secret Broker OS Module — local-first secret handling. |
| `secret_rotation` | ENI Enterprise Secret Rotation OS Module. |
| `semantic_memory` | ENI Semantic Memory OS Module. |
| `skill_factory` | ENI Skill Factory Module — Meta-Skill Generator / Registry / Self-Evolution. |
| `slash_workflow` | slash_workflow — Plan->Implement->Validate AI-coding workflow with reusable markdown slash-commands, a plan-document schema, isolated-context sub-agents, a dete |
| `swarm_bridge` | ENI Swarm Enterprise Module v5.0.0 |
| `swarm_network` | Swarm Network Optimization OS — Enterprise Module |
| `task_harness` | ENI Task Harness OS Module |
| `threat_model` | ENI Threat Model OS Module. |
| `triadforge` | ENI TRIAD FORGE Module — White/Grey/Black Box security testing, as a kernel module. |
| `unified_inbox` | Enterprise Platform Unified Inbox module package. |
| `unified_work_system` | ENI Unified Work System Module |
| `universal_score` | ENI Universal Build Score module. |
| `voice_agent_hub` | voice_agent_hub — voice-driven orchestration of coding agents in a group call. |
| `vuln_scanner` | ENI Vuln Scanner OS Module — offline LLM vulnerability scanning (garak-style). |
| `youtube_transcripts` | YouTube transcript puller with PIA VPN IP rotation. |

