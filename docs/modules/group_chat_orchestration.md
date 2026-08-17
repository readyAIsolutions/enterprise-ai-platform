# Module: `group_chat_orchestration`

- Category: Agent Workflow · priority 2
- Version: 1.0.0
- Purpose: Multi-participant AI+human group chat: round-robin, moderator focus, escalation, handoffs.
- Skill: `eni-module-group_chat_orchestration` (ICM stages) in skills_pack/skills/eni-modules/group_chat_orchestration/

## What it does
Group Chat Orchestration module — multi-participant AI + human group chat.

Grounded in the pulled JE Van Clief transcripts:

* rWHHnIR30DE "Group Chat AI is game changing" — five-person group chat where
  three of the five participants are AI; each reads the shared context, forms
  an opinion and pipes it back in (multi-participant roles, reaction to prior
  context, round-robin turns).
* 0fCQ-4J_jzk "Why I Stopped Building AI Agents and Started Using Claude
  Cowork" — cowork over puppet agents: the human stays in the loop and "nips
  it in the bud" (moderator focus + human-in-the-loop escalation).
* pdoSAWWCDO8 "Claude Design Full Breakdown: GitHub Imports, Skills, and
  Local Model Handoff" — handing work to a specialist/local model with the
  human keeping "active code choice" (handoff_to_agent).
* RZ0AcCLVPFA "AI is the New Compiler" — AI as translator "listening to those
  prompts programmatically" and condensing bulky turns (per-round summaries).

Export surface:
  * GroupChat — the orchestrator (start_group, submit_message, next_speaker,
    escalate_to_human, summarize_round, handoff_to_agent, ...).
  * Handoff — a turn / escalation / agent / summary handoff record.
  * GroupChatOrchestrationModule — the @module-registered platform wrapper.

## Key API (facade methods)
demo, escalate_to_human, handoff_to_agent, health_check, initialize, next_speaker, shutdown, start_group, stats, submit_message, summarize_round

## Tests
```bash
python3 -m pytest modules/group_chat_orchestration/tests -q
```

## Import
```python
from enterprise.modules.group_chat_orchestration import create_group_chat_orchestration_module
m = create_group_chat_orchestration_module()
```
