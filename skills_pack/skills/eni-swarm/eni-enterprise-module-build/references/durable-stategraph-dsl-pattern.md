# Durable, resumable LangGraph-style state-graph DSL (agent orchestration)

Session: rebuilt `modules/agent_graph/` in ~/Desktop/Enterprise Builder/enterprise
with a durable `StateGraph`/`DiGraphBuilder` + SQLite checkpointing + conditional
edges + `resume()`. Baseline 48 green -> 75 green (+27 tests). Reusable pattern
for any orchestration / workflow module in the platform, and for the `agent_graph`
module itself.

## The pattern (LangGraph semantics lifted into stdlib-only)

- **Shared mutable state dict**: every node is `(state: dict) -> dict`; run
  merges each node's return into the one shared `state`. The caller's dict is
  deep-copied first (never mutated).
- **Two edge kinds**:
  - static edge `add_edge(a, b)` — fixed next node.
  - conditional edge `add_conditional_edge(a, router)` where
    `router(state) -> next_node_name` (return END/None to terminate). This is
    the LangGraph routing-style conditional (vs. boolean predicate on an edge).
- **Topological order**: Kahn's algorithm over static edges only (conditional
  targets are runtime-only, so exclude them; a static cycle leaves nodes out of
  the result -> raise).
- **Cycle guard**: `max_steps` counter in the run loop; over -> RuntimeError.
- **SQLite checkpoint store** (`SqliteCheckpointStore`), stdlib-only:
  - tables `state_runs` (run_id PK, status running|complete, completed_nodes JSON
    path) + `state_checkpoints` (run_id, seq, node, state_json, result_json).
  - `save_initial` (seq 0) then `save_step` per completed node (append to path).
  - `db_path=None` -> `":memory:"` (tests); else create parent dir on connect.
  - `close()`/`__len__`/`has`/`list_runs`/`clear` for lifecycle + tests.
- **resume(run_id)**: `run(resume=True)` loads last state + completed path,
  routes from the last completed node, and re-executes from there — completed
  nodes are skipped (a node that failed before checkpointing is re-run). Works
  across store re-open, i.e. durable resumption (proved with a tmp-file DB).
- **Supervisor fan-out**: `add_supervisor(name, route_key, workers)` where each
  worker is a callable OR a sub-`StateGraph` that runs inline and folds its final
  state into the parent state.
- Result object: `StateGraphRun` carries `run_id`, `final_state`, `path` (this
  segment), `all_path` (cumulative incl. resumed), `resumed: bool`, `status`.

## Pitfalls that cost real debugging time (learn these)

1. **Static fan-out needs a LIST, not a scalar.** `_static[node]` must map to a
   list of successors. A diamond (a->b, a->c, b->d, c->d) is valid for
   topological_order but a sequential engine cannot run multi-successor fan-out —
   raise a clear error demanding a conditional edge instead of silently picking
   one path.
2. **Entry-point resolution breaks with conditional edges.** Root detection uses
   static incoming edges only, so conditional targets look root-less and the
   real source (decide) looks like just one of several roots. Fix: among the
   roots, ignore "pure leaves" (no conditional, no static edge to a real node —
   only to END/none) and pick the single non-leaf source. Two isolated nodes
   with no edges are still correctly "multiple entry points".
3. **Don't collide with END marker as a node**, but DO allow an explicit START
   node (`add_node(START, fn)` + `add_edge(START, ...)`) — it's the idiomatic way
   to designate entry in a conditional graph.
4. **Keep the store durable but test-clean**: default `db_path` under `data/`,
   tests pass `db_path=None` / a `tmp_path` DB. On the very first contact with a
   default (non-None) store in a smoke test, a real `.db` file lands in `data/`
   — remember to delete it so the tree stays clean.

## Keep-it-green workflow (same as all enterprise module work)

1. Run existing module suite FIRST for the baseline count.
2. Append new classes to the existing module file (preserve `__all__`, add to it,
   add missing typing imports e.g. `Union`); keep existing classes + tests intact.
3. Add the new test file; run the WHOLE module (`pytest modules/<mod> -q
   -p no:cacheprovider`), not just new tests, to prove no regression.
4. Report real numbers and confirm no stray files / no other-worker files touched.
