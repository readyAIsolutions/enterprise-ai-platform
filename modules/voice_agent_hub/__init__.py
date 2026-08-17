"""voice_agent_hub — voice-driven orchestration of coding agents in a group call.

Grounded in JEVanClief's "We Ran Claude Code By Voice In A Group Call
(The Future of Work?)" (https://www.youtube.com/watch?v=McuxQvaWlNM).
The hub parses spoken utterances via keyword triggers, routes them to
target coding agents (including someone else's Claude Code), dispatches
commands for work, supports interruption, manages local-data access, and
triggers structured workflows by keywords in conversations.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .voice_agent_hub import (  # noqa: F401
    CodingAgent,
    GroupCallSession,
    Intent,
    KeywordEngine,
    KeywordRule,
    Participant,
    PsychometricWorkload,
    Scale,
    VoiceAgentHub,
    VoiceCommand,
    VoiceCommandStatus,
    _DEFAULT_KEYWORD_RULES,
)

logger = logging.getLogger("eni.modules.voice_agent_hub")


@module(
    name="voice_agent_hub",
    version="1.0.0",
    config_defaults={
        "max_interrupts": 3,
        "default_local_data_access": False,
        "max_utterances_per_session": 1000,
    },
)
class VoiceAgentHubModule(Module):
    """Enterprise module wrapping the voice_agent_hub orchestrator."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.hub: Optional[VoiceAgentHub] = None
        self._event_bus = None

    async def initialize(self) -> None:
        try:
            self.hub = VoiceAgentHub()
            self._status = HealthStatus.HEALTHY
        except Exception:  # pragma: no cover - defensive
            self._status = HealthStatus.UNHEALTHY
            raise

    async def health_check(self) -> HealthStatus:
        return self._status

    async def shutdown(self) -> None:
        self._status = HealthStatus.STOPPING

    def set_event_bus(self, event_bus: Any) -> None:
        """Attach the platform event bus for cross-module publishing."""
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(
                Event.create(topic=topic, source=self.name, payload=payload)
            )

    # ------------------------------------------------------------------
    # Facade methods delegating to the hub
    # ------------------------------------------------------------------

    def parse_utterance(self, text: str, speaker: str) -> List[VoiceCommand]:
        """Parse a spoken utterance into voice commands."""
        assert self.hub is not None
        commands = self.hub.parse_utterance(text, speaker)
        self._publish(
            "voice_agent_hub.parsed",
            {"utterance": text, "speaker": speaker, "command_count": len(commands)},
        )
        return commands

    def dispatch(
        self,
        command: VoiceCommand,
        runner: Optional[Any] = None,
    ) -> VoiceCommand:
        """Dispatch a voice command to its target agent."""
        assert self.hub is not None
        result = self.hub.dispatch(command, runner=runner)
        self._publish(
            "voice_agent_hub.dispatched",
            {
                "command_id": result.id,
                "intent": result.intent.value,
                "status": result.status.value,
            },
        )
        return result

    def interrupt(self, agent_name: str) -> bool:
        """Interrupt the running task on an agent."""
        assert self.hub is not None
        interrupted = self.hub.interrupt(agent_name)
        self._publish(
            "voice_agent_hub.interrupted",
            {"agent_name": agent_name, "interrupted": interrupted},
        )
        return interrupted

    def grant_local_data_access(self, agent_name: str) -> None:
        assert self.hub is not None
        self.hub.grant_local_data_access(agent_name)

    def revoke_local_data_access(self, agent_name: str) -> None:
        assert self.hub is not None
        self.hub.revoke_local_data_access(agent_name)

    def can_access_local_data(self, agent_name: str) -> bool:
        assert self.hub is not None
        return self.hub.can_access_local_data(agent_name)

    def run_scale_review(self, speaker: str) -> Dict[str, object]:
        assert self.hub is not None
        return self.hub.run_scale_review(speaker)

    def run_catalog_expansion(self, speaker: str) -> Dict[str, object]:
        assert self.hub is not None
        return self.hub.run_catalog_expansion(speaker)

    def run_frontend_review(self, speaker: str) -> Dict[str, object]:
        assert self.hub is not None
        return self.hub.run_frontend_review(speaker)


def create_voice_agent_hub_module(
    config: Optional[Dict[str, Any]] = None,
) -> VoiceAgentHubModule:
    """Factory for creating a VoiceAgentHubModule instance."""
    return VoiceAgentHubModule(config=config or {})


__all__ = [
    "CodingAgent",
    "GroupCallSession",
    "Intent",
    "KeywordEngine",
    "KeywordRule",
    "Participant",
    "PsychometricWorkload",
    "Scale",
    "VoiceAgentHub",
    "VoiceAgentHubModule",
    "VoiceCommand",
    "VoiceCommandStatus",
    "_DEFAULT_KEYWORD_RULES",
    "create_voice_agent_hub_module",
]
