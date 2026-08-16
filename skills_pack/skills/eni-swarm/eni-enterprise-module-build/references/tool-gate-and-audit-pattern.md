# Tool Permission Gate + Execution Audit (master-class sandbox)

A proven reusable pattern for adding a gated + audited tool surface to an ENI
enterprise module ADDITIVELY — built into `modules/agent_tools/` (gate.py) while
preserving the legacy `PermissionGate` and all pre-existing tests (33 -> 62 green).

## Why a gate/audit instead of a subprocess jail

A subprocess sandbox is risky and not offline-testable. Instead build a
*policy/schema-based virtual sandbox* over the tool-invocation path: declarative
per-tool rules (allow/deny/ask) enforced BEFORE execution, every call written to an
append-only audit log with tamper-detectable integrity. Pure stdlib, fully offline.

## The three components (design that works)

1. **ToolPolicy** — declarative rules: `{tool: "BashTool", level: "deny|allow|ask",
   arg_allow: [...], arg_deny: [...]}`. Rule resolution:
   - most-specific rule wins (exact name > fnmatch wildcard), with a **deny-biased
     tie-break** at equal specificity (deny > ask > allow).
   - argument constraints are enforced BEFORE the rule level: an `arg_deny` hit OR a
     missing `arg_allow` match => DENY even when the tool itself is allow.
   - no matching rule => default level (usually allow; can be deny for fail-closed).
2. **ToolGate** — decision engine + exec wrapper. `evaluate()` = policy-only (no run);
   `run(fn)` = deny->blocked result (fn NOT called), ask->pending result (fn NOT
     called), allow->run+time. Always records the call in the audit.
3. **ToolAudit** — append-only log of (tool, args, allowed, decision, outcome,
   duration_ms, caller). `recent()/search()/all()/count()`. **SHA-256 hash chain**:
   each record stores `prev_hash` + its own `digest = sha256(prev_hash|payload)`;
   `verify_integrity()` recomputes end-to-end and detects ANY tamper (outcome edits,
   arg edits, reordering).

Provide `from_config()` on both policy and gate so a declarative dict
(`{"tool_gate": {"policy": {default, rules[]}}}`) drives everything with no code.

## Wiring into the existing invoke path (layer don't replace)

Do NOT rip out the legacy coarse gate. In `ToolRegistry.invoke`, in order:
coarse `check_permission` (legacy) -> **gate evaluate** (new) -> validate params ->
execute on task with timeout.
- gate DENY  -> raise PermissionError + audit outcome="blocked"
- gate ASK   -> raise PermissionError + audit outcome="pending"
- success    -> audit outcome="success" with duration_ms
- exception  -> audit outcome="error" with duration_ms + error string

Thread-safe (RLock) since the registry and audit are shared. Expose accessors
(`set_tool_gate/get_tool_audit/tool_gate_decision`) and export all new names from
`__init__.py.__all__` so the module surface grows, never shrinks.

## PITFALL: anchored regexes vs JSON-serialized args

Matching arg constraints against `json.dumps(args)` breaks anchored patterns:
`^cat\s` never matches because the serialized arg value starts with `{`, not `cat`.
FIX: match against the JSON string AND against each individual string arg value
(`haystacks = [json_text, *[v for v in args.values() if isinstance(v, str)]]`).
This makes both `^cat\s` (needs raw value) and `rm\s+-rf\s*/` (works on either)
behave correctly. Add tests for both cases.

## PITFALL: test assertions on recent()/seq after appending

When writing audit tests, remember records are 1-indexed and `recent(n)` returns the
LAST n. If you append 15 records then 1 more (16 total), `recent(5)[0].seq == 12`,
not 11. Recompute offsets instead of trusting intuition.

## Test coverage worth keeping (12-18 is the target range)

allow / deny / ask each; default level; arg_deny blocks `rm -rf /`; safe command
passes under allow+arg_deny; arg_allow requires match; exact-beats-wildcard;
deny-bias tie-break; gate no-policy defaults allow; run() deny/ask skip the callable;
run() allow returns result; run() allow error re-raises + records; audit records
every call; search/recent; hash-chain integrity valid + tamper detected (edit outcome,
edit arg); append-only; custom audit injection; from_config; registry invoke records
+ verify_integrity after a real invoke.

## ENI read-compression gotcha (applies to reading this module too)

Large source reads return ENI-compressed carriers (lossy head/tail). Read in small
~50-60 line slices or `grep`/`sed -n 'a,b'`/`awk` for signatures; verify the on-disk
file with `pytest`/`ast.parse`. Do not "repair" files because of this — it's a
tooling display artifact.
