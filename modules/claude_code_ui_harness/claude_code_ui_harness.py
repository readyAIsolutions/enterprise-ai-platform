"""Claude Code UI Harness — a custom front-end for driving & observing Claude Code.

Built directly from the real pulled JE Van Clief transcript
``data/transcripts/JEVanClief/J2GLzkaUrBc.md`` titled
"I'm Building a Custom Front End for Claude Code (Here's the Plan)".

What the transcript is about
----------------------------
David wanted a front-end UI that allows him to *control* Claude and to
*monitor / observe how the agents are working* instead of living inside VS
Code. Running Claude Code / the Claude CLI against an Anthropic *subscription*
keeps cost down versus firing raw API calls for everything, so a good harness
also *tracks usage*. The plan surveys existing open-source repos ("let's not
reinvent the wheel ... let's look at each of those repos") and adds a custom
front-end that can expose a *web service* and navigate a workspace — not just
simple folders but a *mind map or web map* of the agent's workflow.

Development is driven through a *PRD markdown* document describing the target
*stacks*, *integrations*, the *goal / targeting*, and which *breaks down steps
and structure for early phase to late phase* (rather than "build the whole
thing at once"). That PRD can then be fed to a second Claude acting as an
*auditor*, and finally dropped into a workspace so Claude Code can just
"read the PRD for the front end" and build it.

This module is stdlib-only and network-free; everything is computed locally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ViewMode(str, Enum):
    """How a workspace / agent workflow may be presented in the UI.

    Mirrors the transcript's idea of navigating "not just simple folders ...
    but maybe something like a mind map or a web map".
    """

    FOLDERS = "folders"
    MIND_MAP = "mind_map"
    WEB_MAP = "web_map"


class SessionStatus(str, Enum):
    """Lifecycle of a Claude Code driver session running under the harness."""

    RUNNING = "running"
    IDLE = "idle"
    COMPLETED = "completed"
    FAILED = "failed"


class PlanPhaseKind(str, Enum):
    """Meaningful phase labels for the PRD step breakdown.

    The transcript asks Claude to break the build "into steps rather than
    build the whole thing once", staged from *early phase* to *late phase*.
    """

    EARLY = "early"
    MID = "mid"
    LATE = "late"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ClaudeSession:
    """A Claude Code / Claude CLI session driven through the UI harness.

    Grounded in the transcript's motivation of *controlling* Claude and
    *observing how the agents are working* rather than staring at VS Code.
    """

    session_id: str
    label: str
    status: SessionStatus = SessionStatus.IDLE
    tool: str = "cli"                      # "cli" | "desktop" | "mobile"
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    message_count: int = 0


@dataclass
class UsageRecord:
    """One unit of Claude usage observed through the front-end.

    The transcript stresses that driving Claude Code against the Anthropic
    *subscription* "doesn't cost as much" as hitting the raw API for
    everything, and that a front-end "can even track usage".
    """

    session_id: str
    messages: int
    input_tokens: int
    output_tokens: int
    via_api: bool = False                  # False => billed via subscription


@dataclass
class WorkspaceNode:
    """A single node in the navigable view of the agent's workspace.

    ``kind`` is one of "folder" / "file"; ``links`` carries child or map-edge
    references so the same tree can be laid out as plain folders or as a
    mind/web map.
    """

    name: str
    path: str
    kind: str = "file"                     # "folder" | "file"
    depth: int = 0
    links: List["WorkspaceNode"] = field(default_factory=list)


@dataclass
class PlanPhase:
    """One staged chunk of the PRD: from early phase to late phase."""

    name: str
    kind: PlanPhaseKind = PlanPhaseKind.EARLY
    steps: List[str] = field(default_factory=list)
    structure: List[str] = field(default_factory=list)


@dataclass
class PrdDocument:
    """A product-requirements document the way the transcript describes it.

    The transcript says a PRD "describes what kind of stacks you need, right?
    What your integrations might be, what you're trying to do, targeting",
    and Claude is asked to "break it into steps" staged early -> late.
    """

    title: str
    goal: str
    stacks: List[str] = field(default_factory=list)
    integrations: List[str] = field(default_factory=list)
    targeting: str = ""
    phases: List[PlanPhase] = field(default_factory=list)


@dataclass
class AuditFinding:
    """A concern raised when a second (auditor) pass re-reads a PRD.

    The transcript: "you can actually feed this into another version of
    Claude and have it act as that auditor and it can kind of redo it there."
    """

    severity: str                           # "warn" | "error"
    message: str


# ---------------------------------------------------------------------------
# Workspace navigation (folders / mind map / web map)
# ---------------------------------------------------------------------------


def _build_tree(root: Path, depth: int, max_depth: int) -> List[WorkspaceNode]:
    """Walk a real local directory into WorkspaceNode folders/files."""
    nodes: List[WorkspaceNode] = []
    if depth > max_depth or not root.is_dir():
        return nodes
    try:
        entries = sorted(
            root.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower()),
        )
    except OSError:
        return nodes
    for entry in entries:
        kind = "folder" if entry.is_dir() else "file"
        node = WorkspaceNode(
            name=entry.name, path=str(entry), kind=kind, depth=depth
        )
        if kind == "folder":
            node.links = _build_tree(entry, depth + 1, max_depth)
        nodes.append(node)
    return nodes


class WorkspaceNavigator:
    """Present a workspace as folders, a mind map, or a web map.

    Grounded in: "navigate the folders not just simple folders like this ...
    but maybe something like a mind map or a web map."
    """

    def __init__(self, max_depth: int = 6) -> None:
        self.max_depth = max_depth

    def tree(self, workspace: str | Path) -> List[WorkspaceNode]:
        root = Path(workspace)
        if not root.is_dir():
            return []
        return _build_tree(root, depth=0, max_depth=self.max_depth)

    def navigate(self, workspace: str | Path, view: ViewMode = ViewMode.FOLDERS):
        """Return either the folder tree or a map of connected nodes."""
        nodes = self.tree(workspace)
        if view == ViewMode.FOLDERS or not nodes:
            return nodes
        # Mind / web map: flatten to a single root with every node linked,
        # capturing the cross-links the interactive UI would draw.
        map_root = WorkspaceNode(
            name="workspace", path=str(workspace), kind="folder", depth=0
        )
        seen: List[WorkspaceNode] = []

        def collect(ns: Sequence[WorkspaceNode]) -> None:
            for n in ns:
                seen.append(n)
                collect(n.links)

        collect(nodes)
        map_root.links = seen
        return map_root

    def paths(self, workspace: str | Path) -> List[str]:
        """Flat, ordered list of every folder/file path found in the workspace."""
        collected: List[str] = []

        def walk(ns: Sequence[WorkspaceNode]) -> None:
            for n in ns:
                collected.append(n.path)
                walk(n.links)

        walk(self.tree(workspace))
        return collected


# ---------------------------------------------------------------------------
# Session + usage management
# ---------------------------------------------------------------------------


class SessionManager:
    """Track Claude Code sessions the harness is controlling & observing."""

    def __init__(self) -> None:
        self._sessions: Dict[str, ClaudeSession] = {}

    def register(self, session: ClaudeSession) -> ClaudeSession:
        self._sessions[session.session_id] = session
        return session

    def start(self, session_id: str, label: str, tool: str = "cli") -> ClaudeSession:
        return self.register(
            ClaudeSession(
                session_id=session_id, label=label, tool=tool,
                status=SessionStatus.RUNNING,
            )
        )

    def mark(self, session_id: str, status: SessionStatus) -> Optional[ClaudeSession]:
        session = self._sessions.get(session_id)
        if session is not None:
            session.status = status
        return session

    def get(self, session_id: str) -> Optional[ClaudeSession]:
        return self._sessions.get(session_id)

    def all(self) -> List[ClaudeSession]:
        return list(self._sessions.values())

    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values()
                   if s.status == SessionStatus.RUNNING)


class UsageTracker:
    """Track usage through the UI and compare subscription vs. API cost.

    Grounded in: "you can use your Anthropic subscription, so it doesn't
    cost as much. If you did API calls for all of this, it'd be really ..."
    i.e. a front-end should track usage and favor the subscription path.
    """

    def __init__(self, per_api_1k_input: float = 3.0,
                 per_api_1k_output: float = 15.0) -> None:
        # USD per 1000 tokens for the API path (approximate list rates).
        self._records: List[UsageRecord] = []
        self._per_api_1k_input = per_api_1k_input
        self._per_api_1k_output = per_api_1k_output

    def record(self, usage: UsageRecord) -> UsageRecord:
        self._records.append(usage)
        return usage

    def totals(self) -> Dict[str, Any]:
        messages = sum(r.messages for r in self._records)
        input_tokens = sum(r.input_tokens for r in self._records)
        output_tokens = sum(r.output_tokens for r in self._records)
        api_tokens = sum(
            r.input_tokens + r.output_tokens for r in self._records if r.via_api
        )
        return {
            "sessions_tracked": len({
                r.session_id for r in self._records
            }),
            "messages": messages,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "subscription_tokens": input_tokens + output_tokens - api_tokens,
            "api_tokens": api_tokens,
        }

    def estimated_api_cost(self) -> float:
        """What the observed API-flagged usage would cost (used to argue for
        the subscription path the transcript prefers)."""
        cost = 0.0
        for r in self._records:
            if r.via_api:
                cost += (
                    r.input_tokens / 1000 * self._per_api_1k_input
                    + r.output_tokens / 1000 * self._per_api_1k_output
                )
        return round(cost, 4)

    def subscription_savings(self) -> float:
        """Money saved by routing work through the Claude-code subscription."""
        return round(self.estimated_api_cost(), 4)


# ---------------------------------------------------------------------------
# PRD authoring + auditing
# ---------------------------------------------------------------------------

PHASE_ORDER = [PlanPhaseKind.EARLY, PlanPhaseKind.MID, PlanPhaseKind.LATE]


def render_prd(doc: PrdDocument) -> str:
    """Render a PrdDocument into markdown.

    Mirrors the transcript's instruction to produce a *PRD markdown* that
    "describes what we are trying to do and breaks down steps and structure
    for early phase to late phase".
    """
    lines: List[str] = []
    lines.append(f"# {doc.title} — Product Requirements Document")
    lines.append("")
    lines.append("## Goal / Targeting")
    lines.append(doc.goal)
    if doc.targeting:
        lines.append("")
        lines.append(doc.targeting)
    lines.append("")
    lines.append("## Stacks")
    if doc.stacks:
        lines.extend(f"- {s}" for s in doc.stacks)
    else:
        lines.append("- _(none specified)_")
    lines.append("")
    lines.append("## Integrations")
    if doc.integrations:
        lines.extend(f"- {i}" for i in doc.integrations)
    else:
        lines.append("- _(none specified)_")
    lines.append("")
    lines.append("## Phases (early -> late)")
    ordered = sorted(doc.phases, key=lambda p: PHASE_ORDER.index(p.kind))
    for phase in ordered:
        lines.append(f"### {phase.kind.value} phase — {phase.name}")
        lines.append("#### Steps")
        for step in phase.steps:
            lines.append(f"- {step}")
        if phase.structure:
            lines.append("#### Structure")
            lines.extend(f"- {s}" for s in phase.structure)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


class PrdBuilder:
    """Build a phased PRD markdown the way the transcript outlines.

    The transcript explicitly tells Claude to "make a PRD markdown of this
    for Claude code" describing stacks, integrations, goal/targeting, and to
    "break it into steps rather than build the whole thing at once", staged
    "for early phase to late phase".
    """

    @staticmethod
    def build(
        title: str,
        goal: str,
        stacks: Sequence[str] = (),
        integrations: Sequence[str] = (),
        targeting: str = "",
        phases: Sequence[PlanPhase] = (),
    ) -> PrdDocument:
        return PrdDocument(
            title=title,
            goal=goal,
            stacks=list(stacks),
            integrations=list(integrations),
            targeting=targeting,
            phases=list(phases),
        )

    @classmethod
    def build_markdown(cls, doc: PrdDocument) -> str:
        return render_prd(doc)


class PrdAuditor:
    """A second pass over a PRD, standing in for the transcript's "another
    version of Claude ... act as that auditor and it can kind of redo it"."""

    def audit(self, doc: PrdDocument) -> List[AuditFinding]:
        findings: List[AuditFinding] = []
        if not doc.stacks:
            findings.append(AuditFinding(
                "error", "No stacks described; PRD should state what stacks you need."
            ))
        if not doc.integrations:
            findings.append(AuditFinding(
                "warn",
                "No integrations listed; the transcript says the PRD should "
                "cover your possible integrations.",
            ))
        ordered = [p for p in doc.phases if p.kind in PHASE_ORDER]
        if len(ordered) < 2 or not any(
            p.kind == PlanPhaseKind.EARLY for p in ordered
        ):
            findings.append(AuditFinding(
                "error",
                "PRD is not staged early -> late; it risks 'build the whole "
                "thing at once' instead of breaking down steps.",
            ))
        for phase in doc.phases:
            if not phase.steps:
                findings.append(AuditFinding(
                    "warn",
                    f"Phase '{phase.name}' has no steps; break it into steps.",
                ))
        return findings


# ---------------------------------------------------------------------------
# Convenience container tying the harness pieces together
# ---------------------------------------------------------------------------


class ClaudeCodeUiHarness:
    """A network-free, stdlib-only harness exposing the transcript's workflow:

    1. Research open-source adapters without reinventing the wheel.
    2. Drive & observe Claude Code sessions (control + monitoring).
    3. Track usage toward the subscription path (vs raw API).
    4. Navigate the workspace as folders, a mind map, or a web map.
    5. Author a phased PRD markdown (early -> late) and audit it.
    """

    def __init__(self, workspace_root: str | Path = ".",
                 max_depth: int = 6) -> None:
        self.workspace_root = Path(workspace_root)
        self.sessions = SessionManager()
        self.usage = UsageTracker()
        self.navigator = WorkspaceNavigator(max_depth=max_depth)
        self.builder = PrdBuilder()
        self.auditor = PrdAuditor()

    # -- research----------------------------------------------------------
    @staticmethod
    def known_open_source_approaches() -> List[str]:
        """Catalog of approaches the transcript points to: downloadable
        front-ends, usage-tracking front-ends, and mobile/remote control —
        researched so the harness doesn't reinvent the wheel."""
        return [
            "downloadable_front_end",
            "usage_tracking_front_end",
            "mobile_remote_control",
        ]

    # -- sessions ----------------------------------------------------------
    def start_session(self, session_id: str, label: str,
                      tool: str = "cli") -> ClaudeSession:
        return self.sessions.start(session_id, label, tool)

    def list_sessions(self) -> List[ClaudeSession]:
        return self.sessions.all()

    def observe(self, session_id: str) -> Optional[ClaudeSession]:
        """Monitor how the agent is working (the UI's observation pane)."""
        return self.sessions.get(session_id)

    # -- usage -------------------------------------------------------------
    def track_usage(self, usage: UsageRecord) -> UsageRecord:
        return self.usage.record(usage)

    def usage_summary(self) -> Dict[str, Any]:
        summary = self.usage.totals()
        summary["estimated_api_cost"] = self.usage.estimated_api_cost()
        summary["subscription_savings"] = self.usage.subscription_savings()
        return summary

    # -- workspace view -----------------------------------------------------
    def view(self, view: ViewMode = ViewMode.FOLDERS):
        return self.navigator.navigate(self.workspace_root, view)

    def workspace_paths(self) -> List[str]:
        return self.navigator.paths(self.workspace_root)

    # -- PRD ----------------------------------------------------------------
    def build_prd(self, **kwargs) -> PrdDocument:
        return self.builder.build(**kwargs)

    def render_prd(self, doc: PrdDocument) -> str:
        return render_prd(doc)

    def audit_prd(self, doc: PrdDocument) -> List[AuditFinding]:
        return self.auditor.audit(doc)


__all__ = [
    "AuditFinding", "ClaudeCodeUiHarness", "ClaudeSession", "PlanPhase",
    "PlanPhaseKind", "PrdAuditor", "PrdBuilder", "PrdDocument",
    "SessionManager", "SessionStatus", "UsageRecord", "UsageTracker",
    "ViewMode", "WorkspaceNavigator", "WorkspaceNode", "render_prd",
]