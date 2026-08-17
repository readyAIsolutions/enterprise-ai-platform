"""Claude Code UI Harness — Enterprise Module wrapper.

Grounded in the real pulled JE Van Clief transcript
``data/transcripts/JEVanClief/J2GLzkaUrBc.md`` — "I'm Building a Custom Front
End for Claude Code (Here's the Plan)". The transcript's plan is a custom
front-end UI to *control* Claude Code and *monitor / observe how the agents
are working*, tracking usage to favor the Anthropic subscription (vs raw API
cost), presenting the workspace as folders / a mind map / a web map, and
driving the build through a phased *PRD markdown* (early -> late) that a
second Claude can audit before being dropped into the workspace for Claude
Code to read and implement.

Export surface:
  * ClaudeCodeUiHarness   — network-free facade tying the workflow together.
  * SessionManager/ClaudeSession — control & observe Claude Code sessions.
  * UsageTracker/UsageRecord — usage tracking (subscription vs API savings).
  * WorkspaceNavigator/WorkspaceNode — folders / mind map / web map views.
  * PrdBuilder/PrdDocument/PlanPhase/PrdAuditor/AuditFinding — phased PRD + audit.
  * ClaudeCodeUiHarnessModule — ENI platform Module wrapper.
  * create_claude_code_ui_harness_module(config) — factory for the platform.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from enterprise.platform_kernel import Event, HealthStatus, Module, module

from .claude_code_ui_harness import (  # noqa: F401
    AuditFinding, ClaudeCodeUiHarness, ClaudeSession, PlanPhase, PlanPhaseKind,
    PrdAuditor, PrdBuilder, PrdDocument, SessionManager, SessionStatus,
    UsageRecord, UsageTracker, ViewMode, WorkspaceNavigator, WorkspaceNode,
    render_prd,
)

logger = logging.getLogger("eni.claude_code_ui_harness")
__version__ = "1.0.0"


@module(
    name="claude_code_ui_harness",
    version="1.0.0",
    config_defaults={
        "publish_events": True,
        "workspace_root": ".",
        "max_depth": 6,
        "default_view": "folders",
    },
)
class ClaudeCodeUiHarnessModule(Module):
    """ENI platform wrapper around the Claude Code UI harness."""

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config)
        self._event_bus: Optional[Any] = None  # wired via set_event_bus
        self.harness: Optional[ClaudeCodeUiHarness] = None

    async def initialize(self) -> None:
        self.harness = ClaudeCodeUiHarness(
            workspace_root=self._config.get("workspace_root", "."),
            max_depth=int(self._config.get("max_depth", 6)),
        )
        self.status = HealthStatus.HEALTHY
        logger.info("claude_code_ui_harness module initialized")

    async def health_check(self) -> HealthStatus:
        return (HealthStatus.HEALTHY if self.harness is not None
                else HealthStatus.UNHEALTHY)

    async def shutdown(self) -> None:
        self.harness = None
        self.status = HealthStatus.UNKNOWN

    # ------------------------------------------------------------- event bus
    def set_event_bus(self, event_bus: Any) -> None:
        """Wire the platform EventBus into this module (may replace an old one)."""
        self._event_bus = event_bus

    def _publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish an event only when an event bus is present (not None)."""
        bus = self._event_bus
        if bus is not None:
            bus.publish(Event.create(topic, source=self.name, payload=payload))

    # ------------------------------------------------------------- facade
    def start_session(self, session_id: str, label: str,
                      tool: str = "cli") -> ClaudeSession:
        h = self._require()
        session = h.start_session(session_id, label, tool)
        self._publish("claude_code_ui_harness.session.started",
                      {"session_id": session.session_id, "label": session.label})
        return session

    def observe(self, session_id: str) -> Optional[ClaudeSession]:
        """Monitor how an agent is working (observation pane)."""
        return self._require().observe(session_id)

    def track_usage(self, usage: UsageRecord) -> UsageRecord:
        recorded = self._require().track_usage(usage)
        self._publish("claude_code_ui_harness.usage.recorded",
                      {"session_id": usage.session_id,
                       "messages": usage.messages})
        return recorded

    def usage_summary(self) -> Dict[str, Any]:
        return self._require().usage_summary()

    def view(self, view: ViewMode = ViewMode.FOLDERS):
        """Navigate the workspace as folders, a mind map, or a web map."""
        return self._require().view(view)

    def build_prd(self, **kwargs) -> PrdDocument:
        return self._require().build_prd(**kwargs)

    def render_prd(self, doc: PrdDocument) -> str:
        return self._require().render_prd(doc)

    def audit_prd(self, doc: PrdDocument) -> List[AuditFinding]:
        findings = self._require().audit_prd(doc)
        self._publish("claude_code_ui_harness.prd.audited",
                      {"title": doc.title, "findings": len(findings)})
        return findings

    def _require(self) -> ClaudeCodeUiHarness:
        if self.harness is None:
            raise RuntimeError("claude_code_ui_harness not initialized")
        return self.harness


def create_claude_code_ui_harness_module(
    config: Optional[dict[str, Any]] = None,
) -> ClaudeCodeUiHarnessModule:
    """Factory used by the platform to build this module."""
    return ClaudeCodeUiHarnessModule(config=config or {})


__all__ = [
    "AuditFinding", "ClaudeCodeUiHarness", "ClaudeCodeUiHarnessModule",
    "ClaudeSession", "PlanPhase", "PlanPhaseKind", "PrdAuditor", "PrdBuilder",
    "PrdDocument", "SessionManager", "SessionStatus", "UsageRecord",
    "UsageTracker", "ViewMode", "WorkspaceNavigator", "WorkspaceNode",
    "create_claude_code_ui_harness_module", "render_prd",
]