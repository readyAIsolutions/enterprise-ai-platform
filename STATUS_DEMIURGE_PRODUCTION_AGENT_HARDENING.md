# STATUS — DEMIURGE: production_agent_hardening module

Date: 2026-08-16
Branch: upgrade/demiurge-enterprise-boost
Module: modules/production_agent_hardening (v1.0.0)
Transcripts grounded on (JE Van Clief):
  * ezRtp6K6zwE  "Two Engineers on Why Your Agent Demo Will Not Survive Production"
  * NWyTsKTKka8  "Systems Thinking for People Who Build With AI"

================================================================================
1. WHAT IT IS
================================================================================
A hardening linter + readiness gate + systems-thinking lens that converts a
demo AI agent spec into a production posture. Pure, deterministic, dependency
free (stdlib only) so it unit-tests with zero network.

Scored dimensions (weights sum to 100):
  error_handling 15 | retries 10 | observability 20 | secrets 15
  cost_bounds 10 | graceful_failure 10 | deterministic 10 | demo_trap 10

API:
  harden_spec(spec, weights=None, fail_on=None) -> HardeningReport
      {score 0..100, findings[], criticals[], passed, warnings, summary}
  run_readiness_check(spec, min_score=70, required=[...]) -> dict
      {ready, score, critical_blocks, required_missing, report}
  systems_feedback_loop(spec) -> dict
      {feedback_loops[], loop_count, coupling, systems_verdict}
Module (platform decorator): ProductionAgentHardeningModule with facade
  .harden/.readiness/.systems + create_production_agent_hardening_module()

================================================================================
2. TEST / REGISTRATION BOARD
================================================================================
pytest:    python3 -m pytest modules/production_agent_hardening/tests -q
RESULT:    16 passed in 0.03s          -> PASS (16/16)
Registration: _MODULE_REGISTRY['production_agent_hardening']
           <class '...ProductionAgentHardeningModule'> -> PASS

Real measured numbers (demo vs production spec):
  demo spec  -> score 10.0, criticals = [error_handling, retries,
                observability, secrets, graceful_failure, demo_trap], ready=False
  prod spec  -> score 95.0, passed 7/8, criticals 0,          ready=True
  feedback-loop analysis -> 2 loops detected in a coupled agent graph,
                coupling 0.42, verdict flags unbounded loops as cost/drift risk.

================================================================================
3. WHAT THIS ADDS TO THE PLATFORM (R)
================================================================================
R1  Production-readiness linting the platform previously had no answer for:
    it could build/wire modules, but could not judge "is this agent shippable?".
R2  The "demo trap" detector — finds canned/hardcoded/mock-reply landmarks, the
    exact failure mode the "Demo Will Not Survive Production" engineers describe.
R3  A CI-grade readiness gate (run_readiness_check) returning a machine-readable
    {ready, critical_blocks, required_missing} verdict usable in a pipeline.
R4  A systems-thinking lens (feedback loops + coupling) from the second
    transcript — quantifies the emergence/cascade risk that demos ignore.
R5  Grounded, citable provenance: every dimension maps back to a transcript
    lesson (e.g. observability <- "understand how things are running").

================================================================================
4. WHAT TO DROP / NOT SHIP AS-IS (O)
================================================================================
O1  The scoring thresholds are opinionated defaults (70 gate, weight table).
    They are a sensible starting point, not calibrated on production telemetry —
    calibrate once real incident data exists.
O2  systems_feedback_loop synthesis neglects loop gains/delays; it detects
    existence, not magnitude. Fine for a linter, not a control-theory model.
O3  No transport: it is pure logic and deliberately does NOT talk to the
    runtime. Keeping it network-free is what makes it unit-testable; wiring it
    into the platform EventBus/lifecycle is a separate (future) concern.
================================================================================
