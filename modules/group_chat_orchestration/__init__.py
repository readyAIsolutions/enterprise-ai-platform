"""Group Chat Orchestration module — multi-participant AI + human group chat.

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
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

from .chat import (  # noqa: F401
    AI, HUMAN, GroupChat, Handoff, start_group,
)

logger = logging.getLogger("eni.group_chat_orchestration")
__version__ = "1.0.0"


def _demo_participants() -> List[Dict[str, Any]]:
    """The transcript's recurring scene: 2 humans + 3 AI in one room."""
    return [
        {"name": "moderator", "role": "driver", "kind": "human"},
        {"name": "curriculum_ai", "role": "curriculum", "kind": "ai"},
        {"name": "critic_ai", "role": "critic", "kind": "ai"},
        {"name": "synthesis_ai", "role": "synthesis", "kind": "ai"},
        {"name": "domain_expert", "role": "domain", "kind": "human"},
    ]


@module(
    name="group_chat_orchestration",
    version="1.0.0",
    config_defaults={"max_rounds": 8, "focus_threshold": 0.5},
)
class GroupChatOrchestrationModule(Module):
    """Platform wrapper exposing the group-chat orchestrator as a module."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._chats: Dict[str, GroupChat] = {}

    async def initialize(self) -> None:
        self._chats = {}
        self.status = HealthStatus.HEALTHY

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    async def shutdown(self) -> None:
        self._chats = {}
        self.status = HealthStatus.UNKNOWN

    # facade — lift lives of the underlying GroupChat to module level
    def start_group(
        self,
        name: str,
        participants: List[Dict[str, Any]],
        topic: str,
        moderator: Optional[str] = None,
        order: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        chat = GroupChat.start_group(name, participants, topic, moderator, order)
        self._chats[name] = chat
        return chat.stats()

    def _chat(self, name: str) -> GroupChat:
        if name not in self._chats:
            raise KeyError(f"no group chat named {name!r}")
        return self._chats[name]

    def submit_message(self, chat_name: str, participant: str, text: str) -> Dict[str, Any]:
        return self._chat(chat_name).submit_message(participant, text).to_dict()

    def next_speaker(self, chat_name: str, after: Optional[str] = None) -> str:
        return self._chat(chat_name).next_speaker(after=after)

    def escalate_to_human(
        self, chat_name: str, reason: str, by_participant: str,
    ) -> Dict[str, Any]:
        return self._chat(chat_name).escalate_to_human(
            reason, by_participant
        ).to_dict()

    def handoff_to_agent(
        self, chat_name: str, by_participant: str, to_participant: str,
        payload: Any = None, note: str = "",
    ) -> Dict[str, Any]:
        return self._chat(chat_name).handoff_to_agent(
            by_participant, to_participant, payload, note
        ).to_dict()

    def summarize_round(self, chat_name: str) -> Dict[str, Any]:
        return self._chat(chat_name).summarize_round()

    def stats(self, chat_name: Optional[str] = None) -> Dict[str, Any]:
        if chat_name is None:
            return {k: c.stats() for k, c in self._chats.items()}
        return self._chat(chat_name).stats()

    def demo(self, topic: str = "Design a new course curriculum") -> Dict[str, Any]:
        """Start a running example mirroring the transcript's 2-human/3-AI room."""
        return self.start_group("demo", _demo_participants(), topic)


def create_group_chat_orchestration_module(
    config: Optional[dict[str, Any]] = None,
) -> GroupChatOrchestrationModule:
    return GroupChatOrchestrationModule(config=config or {})


__all__ = [
    "GroupChat", "Handoff", "GroupChatOrchestrationModule",
    "create_group_chat_orchestration_module", "start_group",
    "HUMAN", "AI", "__version__",
]
