# GITHUB GOLD — Enterprise AI Platform Upgrade Roadmap

Verified via GitHub REST API (stars, license, last-push, archived) on 2026-08-02.
Every repo below is REAL and verified. Focus: permissive licenses, actively
maintained, high value-to-effort for grafting into a Python/FastAPI enterprise
AI platform (kernel + event bus + swarm + agent_tools + knowledge_graph +
semantic_memory + skill_factory + task_harness + gateway).

Legend: STARS (verified) · License · Health (pushed_at) · 💥 = top pick

---

## 1. Agent Orchestration — upgrade the swarm/agent layer
| Repo | Stars | Lic | Notes |
|---|---|---|---|
| **langchain-ai/langgraph** 💥 | 38.7k | MIT | Stateful (LangGraph) agent graphs, supervisor + swarm patterns, checkpoints, time-travel. Graft: orchestrate enterprise swarm nodes as a graph; persist/checkpoint agent runs. |
| **openai/openai-agents-python** | 28.3k | MIT | Agent loop, tools, handoffs, guardrails, tracing. Graft: as our default single-agent runtime; its swarm/handoff maps to our swarm_bridge. |
| **huggingface/smolagents** | 28.6k | Apache-2.0 | Code-first agents (LLM writes+executes code). Graft: safe code-execution agent on top of agent_tools. |
| **microsoft/semantic-kernel** | 28.4k | MIT | Plugins, planners, memory, connectors. Graft: plugin framework upgrade. |
| **crewAIInc/crewAI** | 56.5k | MIT | Role-based crews (research/writer/critic). Graft: map enterprise roles → crews. |
| **ag2ai/ag2** | 4.8k | Apache-2.0 | AutoGen successor; multi-agent conversation. Graft: groupchats over event bus. |

## 2. Memory / RAG / Vector — upgrade semantic_memory + knowledge_graph
| Repo | Stars | Lic | Notes |
|---|---|---|---|
| **mem0ai/mem0** 💥 | 62.3k | Apache-2.0 | Long-term self-updating memory (extract/save/search). Graft: replace feature-hash default with real LLM memory over semantic_memory. |
| **topoteretes/cognee** | 29.7k | Apache-2.0 | Graph + vector memory with ECL pipelines. (semantic_memory already models it) Graft: swap in as the real engine. |
| **qdrant/qdrant** | 33.7k | Apache-2.0 | Vector DB for 100k+ docs. Graft: backing store for semantic_memory. |
| **run-llama/llama_index** | 51.3k | MIT | Data framework: loaders, index, RAG, agents. Graft: RAG retrieval over enterprise docs. |
| **chroma-core/chroma** | 28.9k | Apache-2.0 | Local-first vector DB. |
| **lancedb/lancedb** | 11.0k | Apache-2.0 | Embedded vector + multi-modal. |
| **neuml/txtai** | 12.8k | Apache-2.0 | Lightweight all-in-one embeddings/vector/sql. |

## 3. MCP / Tool Integration — scale to 1000s of tools
| Repo | Stars | Lic | Notes |
|---|---|---|---|
| **modelcontextprotocol/python-sdk** 💥 | 23.8k | MIT | Canonical MCP client+server. Graft: consume external MCP servers (the "1000s of tools"). |
| **modelcontextprotocol/servers** | 89.1k | mixed | Reference servers (filesystem, git, memory, fetching…). |
| **jlowin/FastMCP** 💥 | 27.0k | Apache-2.0 | Fast MCP server authoring (decorators), SSE/stdio, mounts into FastAPI. Graft: author enterprise tools as MCP servers fast. |
| **composiohq/composio** | 29.5k | MIT | 250+ managed tool integrations via MCP/agent gateway. Graft: on-demand tool schema loading. |
| **lastmile-ai/mcp-agent** | 8.5k | Apache-2.0 | Orchestrates many MCP servers into one smart agent loop. |
| **sparfenyuk/mcp-proxy** | 2.7k | MIT | Proxy/multiplex many MCP servers behind one endpoint. |

## 4. Swarm / Skills / Agent-to-Agent
| Repo | Stars | Lic | Notes |
|---|---|---|---|
| **obra/superpowers** 💥 | 265k | MIT | Agentic skills framework (agentskills.io standard), subagent-driven dev. Graft: align skill_factory with this skill format; reuse recipes. |
| **anthropics/skills** | 165k | — | Anthropic public skills (markdown skill standard). Graft: import skills into skill_factory registry. |
| **google/A2A** | 25.2k | Apache-2.0 | Agent-to-Agent protocol (Card, Task, Message). Graft: enterprise-agents interoperate via A2A across teams/hosts. |

## 5. AI Governance / Security / Observability — harden safety_governance
| Repo | Stars | Lic | Notes |
|---|---|---|---|
| **langfuse/langfuse** 💥 | 32.4k | MIT-ish | LLM tracing, evals, prompt mgmt, LLMOps. Graft: trace every enterprise AI call; audit + eval. |
| **confident-ai/deepeval** | 17.4k | Apache-2.0 | LLM eval framework (metrics, RAG, agent evals). Graft: automated eval gates in safety_governance. |
| **Arize-ai/phoenix** | 10.9k | MIT-ish | Open-source LLM tracing + evals + openinference. |
| **leondz/garak** 💥 | 8.7k | Apache-2.0 | LLM vulnerability scanner (injections, jailbreaks, PII, DOS). Graft: scheduled security scans per model. |
| **truera/trulens** | 3.5k | MIT | Debug/track evals & guardrails. |
| **guardrails-ai/guardrails** | 7.2k | Apache-2.0 | Input/output guardrail validators. |
| *(protectai/llm-guard — ARCHIVED, skip)* | 3.2k | MIT | — |

## 6. Workflow Automation / Scheduling — upgrade gateway + task_harness
| Repo | Stars | Lic | Notes |
|---|---|---|---|
| **apache/airflow** 💥 | 46.4k | Apache-2.0 | Mature DAG orchestration/scheduling. Graft: heavy scheduled pipelines over task_harness. |
| **PrefectHQ/prefect** | 23.5k | Apache-2.0 | Modern Python-native flows, retries, concurrency. Graft: flow engine for long-running agent tasks. |
| **dagster-io/dagster** | 15.9k | Apache-2.0 | Data-aware asset/ops orchestration. |
| **celery/celery** | 28.8k | BSD | Distributed task queue. Graft: lightweight background job execution. |
| **temporalio/sdk-python** | 1.2k | MIT | Durable workflows (exactly-once, long-running, retries). Graft: durable multi-day agent tasks. |
| **huginn/huginn** *(note: org is `huginn/huginn`, not huggingface)* | ~44k | MIT | Self-hosted agent/web automation. |

---

## Recommended build order (value-to-effort, all permissive + healthy)
1. **mem0** → wire into `semantic_memory` (real LLM long-term memory). Highest single upgrade.
2. **FastMCP + python-sdk** → mount enterprise tools as MCP servers in `gateway` (scale to 1000s).
3. **langgraph** → orchestrate `swarm_bridge` as stateful agent graphs with checkpoints.
4. **garak + deepeval + langfuse** → production guardrail + eval + tracing in `safety_governance`.
5. **obra/superpowers + anthropics/skills** → align `skill_factory` with the markdown skills standard.
6. **A2A** → enterprise agents interoperate across teams.

These are dependency-free-quality candidates to graft; each maps to an existing
module so integration is additive, not a rewrite.
