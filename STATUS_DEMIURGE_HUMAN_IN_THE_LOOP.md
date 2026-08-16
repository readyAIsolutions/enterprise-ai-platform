# STATUS — Human in the Loop (human_in_the_loop)

**Builder:** subagent (demiurge enterprise boost) · **Date:** 2026-08-17
**Branch:** `upgrade/demiurge-enterprise-boost`
**Module path:** `modules/human_in_the_loop/`
**Source transcript:** `data/transcripts/JEVanClief/30N9gLucrHg.md`
("Afternoon tea: Why Humans Belong in the Compute Layer")

## Summary

New enterprise module implementing a **human-oversight / human-in-the-loop
orchestration** layer, grounded entirely in the pulled transcript's central
thesis that *humans belong inside the compute layer and should never be
removed from it*. The transcript explicitly states:

> "humans in the compute layer is super important. We don't want them removed
> from it. Humans are extremely compute efficient."

and grounds the idea in Douglas Engelbart's 1968 "Augmenting Human Intellect",
with machines and people collaborating through **dialogue** and human taste kept
in the loop.

From that thesis the module builds the mechanical machinery that keeps a human
in the loop:

- **ApprovalPolicy** — evaluates whether an action may proceed autonomously
  (`auto`), needs a conditional human sign-off (`review`), or must be handed to
  a human (`escalate`) based on model **confidence** and **stakes**.
- **confidence-based routing** — auto-proceed when the model is confident and
  stakes are low; escalate the moment confidence drops or stakes rise.
- **EscalationQueue** — prioritized, deadline-bound queue (higher priority for
  high stakes + uncertainty; tighter human deadlines for higher stakes).
- **DecisionAudit** — durable, transparent log of every routing and override
  decision (approver, decision, reason, timestamp).

Pure, network-free engine (`human_in_the_loop.py`), wired into the ENI platform
kernel as a registered module, copied from the proven `second_brain` shape.

## PASS/FAIL Board

| Check | Result |
|-------|--------|
| Module directory created (`modules/human_in_the_loop/`) | **PASS** |
| Core engine `human_in_the_loop.py` (pure logic — no network/numpy/requests) | **PASS** |
| `__init__.py` imports kernel unconditionally + `@module`-registered `HumanInTheLoopModule` | **PASS** |
| Abstract methods (`initialize` / `health_check` / `shutdown`) + `HealthStatus.HEALTHY` on success | **PASS** |
| Engine `self.engine=None` in `__init__`, facades return dicts/lists | **PASS** |
| `create_human_in_the_loop_module(config)` factory + `__all__` | **PASS** |
| pytest run: `PYTHONPATH=... python3 -m pytest modules/human_in_the_loop/tests -q` | **PASS — 12/12 passed** (0 failed, 0 errors) |
| Kernel registration check (`'human_in_the_loop' in _MODULE_REGISTRY`) | **PASS — True** |
| Committed on `upgrade/demiurge-enterprise-boost` (only new module files + this doc touched) | **PASS** |
| Commit SHA of the feature commit (`git rev-parse HEAD`) | see "Commit" below |

## Grounding (transcript consulted)

- `data/transcripts/JEVanClief/30N9gLucrHg.md` — "Afternoon tea: Why Humans
  Belong in the Compute Layer". Deduplicated the heavily repeated transcript
  (8578 raw lines → 2866 unique) to extract the thesis. Key quotes used:
  - "humans in the compute layer is super important. We don't want them removed
    from it. Humans are extremely compute efficient."
  - "having us be augmented or having a new tool is super powerful. I'm
    actually writing a new paper on it based on the ICM ... I'm calling it
    human in the compute layer ... based on a lot of work done in the 1960s
    from Douglas Engelbart ... Augmenting Human Intellect."
  - "using your your lovely human taste ... the environment and your
    interaction layer ... one of the best ways in which a human can interact
    with information."
  - "Instead of clicking or buttons, it's dialogue." (machine–human dialogue
    replaces opaque button-pushing — motivating transparent audit + sign-off).

## Public API (see `__init__.py` `__all__`)

Pure engine (`human_in_the_loop.py`):
- `Action(action_id, description, confidence, stakes, at)` — a work unit.
- `ApprovalPolicy(auto_confidence, review_confidence,
  high_stake_review_threshold, default_approver, max_reviewers)` — `.evaluate(action)`
  returns `{"verdict": auto|review|escalate, "approvers_needed", "reason"}`.
- `EscalationQueue` — `.add/.ordered/.next/.resolve/.expire_overdue`.
- `HumanInTheLoop(policy, now_provider)` — `.route(action)`, `.resolve(id,
  approver, approved, note)`, `.pending()`, `.audit_log()`, `.queue_stats()`.
- `make_human_in_the_loop()` factory alias.

Platform module (`__init__.py`):
- `HumanInTheLoopModule` — `@module(name="human_in_the_loop", version="1.0.0",
  config_defaults={auto_confidence, review_confidence,
  high_stake_review_threshold, default_approver, max_reviewers})`;
  async `initialize` (HEALTHY), `health_check` -> HealthStatus, `shutdown`.
- Facades: `route_action(...)`, `resolve_action(...)`,
  `pending_escalations()`, `audit_log()`, `queue_stats()`.
- `create_human_in_the_loop_module(config=None)` factory.

## Validation

```
$ PYTHONPATH="/home/hunter/Desktop/Enterprise Builder" python3 -m pytest \
      modules/human_in_the_loop/tests -q
............                                                             [100%]
12 passed in 0.03s

$ PYTHONPATH="/home/hunter/Desktop/Enterprise Builder" python3 -c \
      "from enterprise.platform_kernel import _MODULE_REGISTRY; \
       import enterprise.modules.human_in_the_loop; \
       print('human_in_the_loop' in _MODULE_REGISTRY)"
True
```

## Commit

- Feature commit message: `UPGRADE WAVE: add human_in_the_loop module from
  JEVanClief 30N9gLucrHg`
- SHA: recorded via `git log -1` (see final summary).

## UNVALIDATED

- **End-to-end platform boot / orchestrator merge**: not run. The module is
  verified in isolation (registration True), but full ENI platform startup that
  instantiates every registered module has not been exercised here; the
  orchestrator merges `data/build/manifest.json` centrally and was not touched.
- **High-volume / concurrency behavior**: the escalation queue is in-memory and
  single-threaded; no stress or multi-worker test was run.
- **Real-model integration**: confidence values are provided by the caller; no
  live model was invoked, so real-world confidence distributions were not
  validated.
- **Transcript quote fidelity**: the transcript contains heavy self-duplication
  and informal speech; quotes were extracted after deduplication and should be
  treated as thematic grounding, not verbatim transcripts.
