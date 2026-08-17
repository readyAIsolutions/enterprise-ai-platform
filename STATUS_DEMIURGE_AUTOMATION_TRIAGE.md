# STATUS — DEMIURGE: automation_triage module build

Build ledger entry for the new platform module `automation_triage`, grounded in
four REAL JE Van Clief transcripts (ENI Enterprise Platform).

## Source transcripts used
  * SjlCJIU9ODs  — "The Ladder That Explains Every AI Failure (And How to Avoid Them)"
  * 956DPSPX4wg  — "You're Automating The Wrong Layer (How 30,000 People Build AI Without Frameworks)"
  * ZMDXs59Ntjc  — "The Real Skill in AI: Knowing What Not to Automate"
  * AZ1l-oaD3tk  — "Afternoon Tea #2: Stop Building Production-Ready AI. Solve for One Client First"

## Module surface (created)
  * modules/automation_triage/__init__.py            — @module("automation_triage") + facade + factory
  * modules/automation_triage/triage.py              — pure, network-free core logic
  * modules/automation_triage/tests/test_automation_triage.py — unit tests

Exported API:
  triage_task(task_repr, context) -> TriageDecision      (the ladder)
  detect_wrong_layer(task_repr, attempted_layer, context) -> WrongLayerReport
  what_not_to_automate(task_repr, context) -> NotAutoDecision
  scope_for_one_client(proposal_reqs, context) -> ScopeVerdict
  enums: AutomationLayer (LAYER_0/1/2/3), TriageAction
  module: AutomationTriageModule + create_automation_triage_module(config=None)

## Test results (REAL)
  python3 -m pytest modules/automation_triage/tests -q
  => 17 passed, 0 failed, 0 errors  (0.03s)

  Full-suite regression: python3 -m pytest modules -q
  => 4318 passed, 1 skipped, 0 failed

  Registration check:
  $ PYTHONPATH="/home/hunter/Desktop/Enterprise Builder" python3 -c \
      "from enterprise.platform_kernel import _MODULE_REGISTRY; \
       import enterprise.modules.automation_triage; \
       print('automation_triage' in _MODULE_REGISTRY)"
  => True

## PASS / FAIL board
  [PASS] Module factory + platform decorator registration
  [PASS] Lifecycle initialize / health_check (healthy) / shutdown
  [PASS] Ladder: raw layer 0 SERVE_RAW for one-off/prototype
  [PASS] Ladder: layer 2 WRAP_IN_FLOW for repeatable high-volume flow
  [PASS] Ladder: layer 3 BUILD_SYSTEM when flow generates learning data
  [PASS] Judgment guard: KEEP_HUMAN for judgment/strategy/negotiation tasks
  [PASS] Wrong-layer: flags under-leveled raw output; flags over-automation of judgment
  [PASS] What-not-to-automate: mechanics yes, judgment stays human
  [PASS] One-client guard: defer production features until client validated
  [PASS] Manifest updated (valid JSON) + built_modules registration
  [FAIL] none

## What adds R / what to drop
ADDS R (value, grounded in transcripts):
  - The ladder is a ready-made "should I automate this / at what layer" advisor —
    directly useful as a pre-flight gate before building agents/flows.
  - Wrong-layer detection operationalizes the core thesis of 956DPSPX4wg: catch
    teams pouring effort into commoditized raw output instead of context flows.
  - "What not to automate" guard turns the "questions become valuable" idea into
    a per-task keep-human decision.
  - One-client scoping guard operationalizes AZ1l-oaD3tk: blocks premature
    production infra before a validated single-client use case.

DROP (kept minimal; do not add):
  - NOT adding fake enterprise features that the transcripts don't teach
    (billing, RBAC tables, multi-tenant engines, audit trails, dashboards).
  - No network I/O anywhere in core — fully unit-testable offline.

## Commit
branch: upgrade/demiurge-enterprise-boost
commit: see `git log -1` for SHA (feat(automation_triage): ...)
