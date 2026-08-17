# STATUS — group_chat_orchestration (DEMIURGE build)

Date: 2026-08-16
Branch: upgrade/demiurge-enterprise-boost
Commit: 63fdae7f7a0fddebf2ff5ef1855fd20b1a6d7f69
Module: group_chat_orchestration  v1.0.0

## Grounding (REAL transcript content, 4 pulled JE Van Clief videos)

| Video | Title | What it contributed |
|-------|-------|---------------------|
| rWHHnIR30DE | Group Chat AI is game changing | 5-person group chat, 3 are AI; every AI reads all shared context, forms an opinion, reacts → multi-participant roles + round-robin turns + reaction-to-prior-context |
| 0fCQ-4J_jzk | Why I Stopped Building AI Agents and Started Using Claude Cowork | cowork-over-puppet-agents; human stays in the loop and "nips it in the bud" → moderator on-task driver + human-in-the-loop escalation |
| pdoSAWWCDO8 | Claude Design Full Breakdown: GitHub Imports, Skills, and Local Model Handoff | work handoff to specialist/local model while human keeps "active code choice" → handoff_to_agent |
| RZ0AcCLVPFA | AI is the New Compiler | AI as translator "listening to prompts programmatically" + condensing bulky turns → per-round summarize_round |

## PASS / FAIL board

- [x] Core pure module (no network) — modules/group_chat_orchestration/chat.py
- [x] Platform module wrapper (@module decorator) — __init__.py
- [x] Tests — modules/group_chat_orchestration/tests/test_group_chat_orchestration.py
- [x] pytest: 9 passed in ~0.02s (PASS)
- [x] _MODULE_REGISTRY["group_chat_orchestration"] -> True
- [x] Manifest updated (data/build/manifest.json): 4 video ids status built, module group_chat_orchestration
- [x] Committed on upgrade/demiurge-enterprise-boost (63fdae7)
- [x] No network in core or tests

## API

Core class `GroupChat` (+ `Handoff` record, module-level `start_group` factory):
- start_group(name, participants: [{name, role, kind: human|ai}], topic, moderator=None, order=None)
- submit_message(participant, text) -> Handoff(kind='turn')   # hands mic to next speaker
- next_speaker(after=None, kind=None)                          # round-robin picker
- check_focus(text, threshold=0.5) -> 'on_topic'|'off_topic'   # moderator driver
- escalate_to_human(reason, by_participant, human=None) -> Handoff  # pauses room
- resume(by_human=None) -> bool                                # escalation gating
- handoff_to_agent(from, to, payload, note) -> Handoff         # cowork delegation
- summarize_round(round_no=None) -> dict                       # condenser
- transcript() / stats()

Platform module `GroupChatOrchestrationModule` (facade): start_group, submit_message,
next_speaker, escalate_to_human, handoff_to_agent, summarize_round, stats, demo.
Factory: create_group_chat_orchestration_module(config=None).
Config defaults: {max_rounds: 8, focus_threshold: 0.5}.

## What adds R (real value)

- Turn-taking / who-speaks-when: the exact mechanic of the 5-person group chat;
  reusable anywhere you have >1 AI + humans negotiating in a room.
- Human-in-the-loop gating (escalation pauses autonomous turns until a named
  human resumes) — directly the cowork lesson; prevents runaway agents.
- Moderator focus check keeps a multi-agent room on the declared topic.
- Deterministic handoffs make orchestration testable without a live model.
- Agent handoff primitive is the seam you'd plug a real model/router into later.

## What to drop / not build

- Do NOT bake in any specific LLM API call — the pure orchestrator should stay
  model-agnostic; model inference belongs behind the handoff seam, not in the module.
- Drop 'demo()' and the fixed 2-human/3-AI participant preset if you want a leaner
  surface — it's illustrative only, not a real feature.
- The round counters/max_rounds cap are currently advisory (not enforced); either
  wire them into a policy hook or remove them to avoid dead config.

## Notes / issues

- data/build/manifest.json is gitignored (data/); it was force-added+committed by a
  concurrent sibling subagent already containing these 4 entries, so it lives in
  HEAD (commit f7d6188) rather than in this module's commit. On-disk ledger is valid.
- Concurrent sibling subagents were editing the same manifest; final state is a clean
  superset (this module + second_brain), JSON-validated.
