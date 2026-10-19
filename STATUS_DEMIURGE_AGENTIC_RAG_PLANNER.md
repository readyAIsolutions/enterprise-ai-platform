# STATUS — agentic_rag_planner (DEMIURGE)

Module: `enterprise/modules/agentic_rag_planner/`
Source transcript: ColeMedin/p0FERNkpyHE.md — "Introducing RAG 2.0: Agentic RAG + Knowledge Graphs"

## What it is
A **retrieval-strategy planner/router**. Given a user query it DECIDES which
retrieval tool(s) to use — vector/semantic search vs knowledge-graph traversal
vs hybrid — and in what order, then emits a structured `RetrievalPlan`. It does
NOT implement a vector DB or a graph DB; it plans over abstract tool interfaces.
This is the transcript's "the agent picks and chooses how it explores the
knowledge" idea.

Grounding:
- Vector/semantic search = broad conceptual lookup across embedded doc chunks.
- Knowledge graph = precise relationship/entity/temporal questions (how X
  relates to Y, facts represented relationally / changing over time).
- Agent with both tools picks per question, or uses both (hybrid), and can
  refine iteratively (search again / fall back).

## API
- `ToolKind` enum + `VECTOR` / `GRAPH` / `HYBRID` constants
- `RetrievalStep(tool, query, reason)` dataclass
- `RetrievalPlan(steps, rationale, strategy)` with `.tools`, `.is_hybrid()`
- `QueryClassifier.classify(query) -> ClassificationResult` (stdlib regex heuristics)
- `RagPlanner.plan(query)` and `.plan_multi(query, prior_result_counts)` (agentic refinement/fallback)
- `RetrievalTool` Protocol + `RetrievalToolABC` + `InMemoryTool` stub
- `PlanExecutor(tools).execute(plan)` (merge+dedup by id, plan order) / `.execute_counts(plan)`
- `AgenticRagPlannerModule(Module)` + `create_agentic_rag_planner_module(config)`

Pure stdlib, network-free, deterministic.

## Verification
- pytest: **11 passed, 0 failed**
- kernel registration: **True**
