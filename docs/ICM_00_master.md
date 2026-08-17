# ICM 00_master — Enterprise Task -> Module -> Stage map

Read this file to know which module + stage to activate for a task.
Catch-all: if a task just needs a capability, use the module directly.

| Task / need | Module | Primary stage(s) |
|---|---|---|
| Daily research feeds (arXiv/HF/PwC/AlphaXiv), dedup, tagging | paper_feeds | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| Layered memory model for agents (working/short/long) from AI | ai_memory_hierarchy | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| Knowledge capture/resurfacing engine: nodes+links, spaced re | second_brain | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| Feedback loops, coupling and systems lens for AI feature des | ai_systems_thinking | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| Multi-participant AI+human group chat: round-robin, moderato | group_chat_orchestration | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| Agent-driven retrieval-augmented generation workflow. | agentic_rag | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| Human review/approval gates inside agent runs. | human_in_the_loop | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| Task -> {read/skip/skills} routing table with token-budget g | context_routing | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| Live multi-editor workspace: lock, merge-safe write, history | shared_workspace | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| Harness for coding-agent output: run, verify, audit. | ai_coding_harness | 01_intake, 02_research, 03_drafting, 04_verification, 05_output |
| What-to-automate ladder, wrong-layer detection, one-client s | automation_triage | 01_intake, 03_drafting, 04_verification, 05_output |
| Demo->production hardening linter across 8 scored dimensions | production_agent_hardening | 01_intake, 03_drafting, 04_verification, 05_output |
| Operational hardening checks for shipping an agent into prod | production_hardening | 01_intake, 03_drafting, 04_verification, 05_output |
| Structured tradeoff scoring for engineering decisions. | engineering_tradeoff | 01_intake, 03_drafting, 04_verification, 05_output |
| Audit generated code for correctness, security and quality s | codegen_audit | 01_intake, 03_drafting, 04_verification, 05_output |
| Automate procurement/RFP bid intake, scoring and responses. | procurement_bid_automation | 01_intake, 03_drafting, 04_verification, 05_output |
| Represent/edit long-form video (animations) as code/scripts. | video_as_code | 01_intake, 03_drafting, 04_verification, 05_output |
| Probe/evaluate model reasoning attributes (psychometric-styl | model_psychometrics | 01_intake, 03_drafting, 04_verification, 05_output |
| Guardrails for using AI in education (anti-cheating, learnin | ai_education_guardrails | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI A2A Module -- Agent-to-Agent protocol (Google A2A style) | a2a | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Agent Catalog Module -- unified specialist-agent registr | agent_catalog | 01_intake, 03_drafting, 04_verification, 05_output |
| Agent Communication & Coordination OS — Multi-agent orchestr | agent_coordination | 01_intake, 03_drafting, 04_verification, 05_output |
| Claude Code Core — Enterprise Platform Kernel Module v2.0.0 | agent_core | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Agent Graph Module — langgraph-style stateful agent grap | agent_graph | 01_intake, 03_drafting, 04_verification, 05_output |
| Claude Code Superior — Infrastructure Module v1.0.0 | agent_infra | 01_intake, 03_drafting, 04_verification, 05_output |
| Enterprise Agent OS Module — a unified AI agent operating sy | agent_os | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Enterprise — Claude Code Tools Module v2.0.0 | agent_tools | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Enterprise AI Defense OS Module. | ai_defense | 01_intake, 03_drafting, 04_verification, 05_output |
| Artifact Pipeline — navigate & organize all creative works ( | artifact_pipeline | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Autonomous Agent Runtime Module -- Multi-provider LLM ab | autonomous_agent_runtime | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Enterprise Compliance OS Module. | compliance | 01_intake, 03_drafting, 04_verification, 05_output |
| Enterprise Platform — Compression Bridge Module v3.0.0 | compression_bridge | 01_intake, 03_drafting, 04_verification, 05_output |
| Cost Meter — per-tenant cost metering + fractional-reasoning | cost_meter | 01_intake, 03_drafting, 04_verification, 05_output |
| Customer Experience OS Module. | customer_experience | 01_intake, 03_drafting, 04_verification, 05_output |
| Developer Experience OS Module | developer_experience | 01_intake, 03_drafting, 04_verification, 05_output |
| Disaster Recovery OS Module | disaster_recovery | 01_intake, 03_drafting, 04_verification, 05_output |
| Enterprise Validation & Certification OS — Module Entry Poin | enterprise_validation | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Eval Gate OS Module — automated LLM evaluation gates (lo | eval_gate | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Multi-Gateway Remote Control & Automations Module | gateway | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Guardrails OS Module. | guardrails | 01_intake, 03_drafting, 04_verification, 05_output |
| Enterprise Hermes Controller OS Module — autonomous controll | hermes_controller | 01_intake, 03_drafting, 04_verification, 05_output |
| ICM (Interpretable Context Methodology) — skill/prompt-engin | icm | 01_intake, 03_drafting, 04_verification, 05_output |
| Innovation R&D OS Module | innovation_rd | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Knowledge Base OS Module | kb_bridge | 01_intake, 03_drafting, 04_verification, 05_output |
| Knowledge Graph OS Module | knowledge_graph | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI LLMOps Trace OS Module — local, offline LLM tracing & ob | llmops_trace | 01_intake, 03_drafting, 04_verification, 05_output |
| Enterprise Platform — Look & Feel Registry Module v1.0.0 | look_and_feel | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI MCP Tools Module — FastMCP-style tool registry & MCP ser | mcp_tools | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Agent Memory OS Module. | memory | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Enterprise MLOps/LLMOps Lifecycle Module — Complete Agen | mlops_lifecycle | 01_intake, 03_drafting, 04_verification, 05_output |
| Enterprise Model Miner OS Module — scan/rip local model trai | model_miner | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Model Router OS Module — enterprise model-routing / fall | model_router | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Model Security OS Module. | model_security | 01_intake, 03_drafting, 04_verification, 05_output |
| Observability — real, consolidated fleet health + Prometheus | observability | 01_intake, 03_drafting, 04_verification, 05_output |
| Privacy & Data Governance OS Module | privacy_data | 01_intake, 03_drafting, 04_verification, 05_output |
| Prompt & Context Management OS Module | prompt_context | 01_intake, 03_drafting, 04_verification, 05_output |
| Enterprise Prompt Guard OS Module — injection / jailbreak /  | prompt_guard | 01_intake, 03_drafting, 04_verification, 05_output |
| Production RAG System — Enterprise-grade Retrieval-Augmented | rag | 01_intake, 03_drafting, 04_verification, 05_output |
| Release & Change Management OS Module | release_change | 01_intake, 03_drafting, 04_verification, 05_output |
| Research & Verification OS — Enterprise Platform Kernel Modu | research_verification | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Response Hardening module. | response_hardening | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Response Ops Module — self-healing fleet supervisor + IC | response_ops | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Enterprise — Safety & Governance OS v1.0.0 | safety_governance | 01_intake, 03_drafting, 04_verification, 05_output |
| Enterprise Secret Broker OS Module — local-first secret hand | secret_broker | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Enterprise Secret Rotation OS Module. | secret_rotation | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Semantic Memory OS Module. | semantic_memory | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Skill Factory Module — Meta-Skill Generator / Registry / | skill_factory | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Swarm Enterprise Module v5.0.0 | swarm_bridge | 01_intake, 03_drafting, 04_verification, 05_output |
| Swarm Network Optimization OS — Enterprise Module | swarm_network | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Task Harness OS Module | task_harness | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Threat Model OS Module. | threat_model | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI TRIAD FORGE Module — White/Grey/Black Box security testi | triadforge | 01_intake, 03_drafting, 04_verification, 05_output |
| Enterprise Platform Unified Inbox module package. | unified_inbox | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Unified Work System Module | unified_work_system | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Universal Build Score module. | universal_score | 01_intake, 03_drafting, 04_verification, 05_output |
| ENI Vuln Scanner OS Module — offline LLM vulnerability scann | vuln_scanner | 01_intake, 03_drafting, 04_verification, 05_output |
| YouTube transcript puller with PIA VPN IP rotation. | youtube_transcripts | 01_intake, 03_drafting, 04_verification, 05_output |

_Generated: python3 scripts/gen_icm_skills.py_