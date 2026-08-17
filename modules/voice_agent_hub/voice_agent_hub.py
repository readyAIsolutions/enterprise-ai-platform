"""Pure-logic core for the ``voice_agent_hub`` module.

Grounding: JEVanClief, "We Ran Claude Code By Voice In A Group Call
(The Future of Work?)" (https://www.youtube.com/watch?v=McuxQvaWlNM).
The transcript demonstrates voice-driven orchestration of coding agents
inside a group call: participants speak natural-language commands that
are parsed via keyword triggers, routed to a target agent (who may be
"someone else's Claude Code"), dispatched to perform work (e.g. analyse
missing psychometric scales, update front-end components), and — in the
future — interrupted mid-task.  Structured workflows are triggered by
keywords in conversations, and agents can access data locally on the
host computer.

This module is a pure-stdlib, network-free implementation of that vision:

* :class:`VoiceCommand` — a parsed spoken utterance with an intent,
  target agent, and lifecycle status.
* :class:`VoiceCommandStatus` — the lifecycle (pending → dispatched →
  running → completed / interrupted / failed).
* :class:`KeywordRule` — maps a set of spoken keyword phrases to an
  intent, enabling structured workflow triggers.
* :class:`KeywordEngine` — matches a transcript line against registered
  keyword rules, yielding matched intents.
* :class:`Participant` — a group-call participant who may host a coding
  agent and grant local-data access.
* :class:`CodingAgent` — a remote coding agent (e.g. Claude Code) that
  can be controlled by voice and interrupted.
* :class:`GroupCallSession` — records a group-call session with its
  participants, transcript utterances, and parsed commands.
* :class:`VoiceAgentHub` — central orchestrator: parse utterances,
  dispatch commands, target agents, trigger workflows, interrupt, and
  manage local-data access.
* :class:`Scale` — a psychometric scale with name, abbreviation,
  description, and validity.
* :class:`PsychometricWorkload` — the demo workload from the transcript:
  a catalog of 10 built-in validated scales, analysis of missing scales,
  and front-end review.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

__version__ = "1.0.0"

# =============================================================================
# VoiceCommand — the core unit of voice-driven work
# =============================================================================


class VoiceCommandStatus(str, Enum):
    """Lifecycle of a voice command issued in a group call.

    Mirrors the transcript's flow: a spoken utterance is parsed,
    dispatched to a target coding agent, runs, and either completes
    or is interrupted (the "process of interruption" the team is
    working on).
    """

    PENDING = "pending"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class Intent(str, Enum):
    """Intent types extracted from spoken utterances via keyword matching.

    Each member is grounded in the transcript's demonstrated scenarios.
    """

    UNKNOWN = "unknown"
    REVIEW_SCALES = "review_scales"  # "what scales are we missing?"
    SUGGEST_SCALES = "suggest_scales"  # "here are some notable scales"
    EXPAND_CATALOG = "expand_catalog"  # 10 built-in validated scales -> 12
    REVIEW_FRONTEND = "review_frontend"  # "anything we're missing in the front end?"
    UPDATE_FRONTEND = "update_frontend"
    ACCESS_LOCAL_DATA = "access_local_data"  # "immediately access all that data"
    CONTROL_AGENT = "control_agent"  # "control someone else's Claude Code"
    INTERRUPT = "interrupt"  # "process of interruption"


@dataclass
class VoiceCommand:
    """A parsed voice command from a group-call utterance.

    Attributes:
        id: Unique command identifier (UUID4).
        text: The raw spoken utterance.
        speaker: Name of the participant who spoke.
        intent: Recognised intent (from keyword matching).
        target_agent: Name of the agent this command is directed at.
        status: Current lifecycle status.
        payload: Arbitrary data attached to the command (e.g. scale names).
        created_at: UTC timestamp.
        workflow_triggered: Name of the keyword workflow triggered, if any.
    """

    id: str
    text: str
    speaker: str
    intent: Intent
    target_agent: str
    status: VoiceCommandStatus = VoiceCommandStatus.PENDING
    payload: Dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    workflow_triggered: Optional[str] = None


# =============================================================================
# Keyword-triggered workflows
# =============================================================================


@dataclass
class KeywordRule:
    """A rule that maps spoken keyword phrases to an intent.

    Grounding: "structured workflows, all of these things are being
    triggered by keywords in conversations."
    """

    keywords: Tuple[str, ...]
    intent: Intent
    description: str


# Default keyword rules grounded in the transcript's spoken commands.
_DEFAULT_KEYWORD_RULES: Tuple[KeywordRule, ...] = (
    KeywordRule(
        keywords=("what scales are we missing", "scales are we missing", "missing scales"),
        intent=Intent.REVIEW_SCALES,
        description="Review what psychometric scales are missing from the engine",
    ),
    KeywordRule(
        keywords=("notable scales", "could be added", "scales that could be added"),
        intent=Intent.SUGGEST_SCALES,
        description="Suggest scales that could be added to the catalog",
    ),
    KeywordRule(
        keywords=("built-in", "validated scales", "10 built-in", "12 built-in"),
        intent=Intent.EXPAND_CATALOG,
        description="Expand the built-in validated scales catalog",
    ),
    KeywordRule(
        keywords=("front end", "frontend", "anything we're missing"),
        intent=Intent.REVIEW_FRONTEND,
        description="Review the front-end for missing components",
    ),
    KeywordRule(
        keywords=("interrupt", "stop", "cancel"),
        intent=Intent.INTERRUPT,
        description="Interrupt the currently running agent task",
    ),
    KeywordRule(
        keywords=("access", "local data", "locally"),
        intent=Intent.ACCESS_LOCAL_DATA,
        description="Request local data access on the agent's computer",
    ),
    KeywordRule(
        keywords=("control", "someone else", "claude code"),
        intent=Intent.CONTROL_AGENT,
        description="Control another participant's coding agent by voice",
    ),
)


class KeywordEngine:
    """Matches spoken utterances against registered keyword rules.

    Grounding: "triggered by keywords in conversations."
    """

    def __init__(self, rules: Iterable[KeywordRule] = ()) -> None:
        self._rules: List[KeywordRule] = list(rules) or list(_DEFAULT_KEYWORD_RULES)

    def register(self, rule: KeywordRule) -> None:
        """Register a new keyword rule."""
        self._rules.append(rule)

    def match(self, text: str) -> List[KeywordRule]:
        """Return all keyword rules whose phrases appear in *text*.

        Matching is case-insensitive and checks for substring presence.
        """
        lower = text.lower()
        matched: List[KeywordRule] = []
        for rule in self._rules:
            if any(keyword in lower for keyword in rule.keywords):
                matched.append(rule)
        return matched

    def match_first(self, text: str) -> Optional[KeywordRule]:
        """Return the first matching keyword rule, or None."""
        matched = self.match(text)
        return matched[0] if matched else None

    @property
    def rules(self) -> List[KeywordRule]:
        """Return all registered rules (read-only copy)."""
        return list(self._rules)


# =============================================================================
# Group-call participants & coding agents
# =============================================================================


@dataclass
class CodingAgent:
    """A remote coding agent (e.g. Claude Code) that can be controlled by voice.

    Grounding: "control someone else's Claude Code or AI through my voice
    and immediately access all of that data that's locally on their computer."
    """

    name: str
    local_data_allowed: bool = False
    host_participant: Optional[str] = None
    _current_task: Optional[VoiceCommand] = None
    _interrupted: bool = False

    @property
    def is_busy(self) -> bool:
        """Return True if the agent is currently running a task."""
        return self._current_task is not None

    @property
    def current_task(self) -> Optional[VoiceCommand]:
        """Return the currently running task, or None."""
        return self._current_task

    def assign_task(self, command: VoiceCommand) -> None:
        """Assign a voice command to this agent for execution."""
        if self.is_busy:
            raise ValueError(f"Agent '{self.name}' is already running a task")
        self._current_task = command
        command.status = VoiceCommandStatus.RUNNING

    def complete_task(self) -> None:
        """Mark the current task as completed."""
        if self._current_task is not None:
            self._current_task.status = VoiceCommandStatus.COMPLETED
            self._current_task = None

    def interrupt(self) -> None:
        """Interrupt the currently running task.

        Grounding: "that kind of process of interruption."
        """
        if self._current_task is not None:
            self._current_task.status = VoiceCommandStatus.INTERRUPTED
            self._current_task = None
            self._interrupted = True
        self._interrupted = True


@dataclass
class Participant:
    """A participant in a group call who may host a coding agent.

    Grounding: the transcript features JEVanClief, David McDermott,
    and K Kumar working on a project together in a group call.
    """

    name: str
    agent: Optional[CodingAgent] = None
    local_data_scope: Tuple[str, ...] = field(default_factory=tuple)

    def has_agent(self) -> bool:
        return self.agent is not None


# =============================================================================
# Group-call session
# =============================================================================


@dataclass
class GroupCallSession:
    """A recorded group-call session with participants and voice commands.

    Grounding: "What if I could sit inside of a group call and control
    someone else's Claude Code or AI through my voice?"
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    participants: Dict[str, Participant] = field(default_factory=dict)
    commands: List[VoiceCommand] = field(default_factory=list)
    transcript_lines: List[Tuple[str, str, datetime]] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_utterance(self, speaker: str, text: str) -> None:
        """Record a spoken utterance from a participant."""
        self.transcript_lines.append(
            (speaker, text, datetime.now(timezone.utc))
        )

    def add_command(self, command: VoiceCommand) -> None:
        """Record a parsed voice command."""
        self.commands.append(command)

    @property
    def utterance_count(self) -> int:
        return len(self.transcript_lines)

    @property
    def command_count(self) -> int:
        return len(self.commands)

    def get_commands_by_speaker(self, speaker: str) -> List[VoiceCommand]:
        return [c for c in self.commands if c.speaker == speaker]

    def get_commands_by_intent(self, intent: Intent) -> List[VoiceCommand]:
        return [c for c in self.commands if c.intent == intent]


# =============================================================================
# Psychometric workload — demo domain grounded in the transcript
# =============================================================================

# The 10 built-in validated psychometric scales mentioned in the transcript.
_BUILT_IN_SCALES = [
    ("ECE-1", "ECE-1", "Ethical Climate Evaluation scale, version 1"),
    ("RWA", "Right-Wing Authoritarianism", "Right-Wing Authoritarianism scale"),
    ("SDO", "Social Dominance Orientation", "Social Dominance Orientation scale"),
    ("BFI", "Big Five Inventory", "Big Five personality traits inventory"),
    ("NPI", "Narcissistic Personality Inventory", "Narcissistic Personality Inventory"),
    ("LEQ", "Life Events Questionnaire", "Life Events Questionnaire"),
    ("PANAS", "PANAS", "Positive and Negative Affect Schedule"),
    ("IUS", "Intolerance of Uncertainty Scale", "Intolerance of Uncertainty Scale"),
    ("LOT-R", "Life Orientation Test-Revised", "Life Orientation Test-Revised (optimism)"),
    ("MCSDS", "Marlowe-Crowne", "Marlowe-Crowne Social Desirability Scale"),
]

# Scales suggested by the agent in the transcript (Dark Triad sub-traits).
_SUGGESTED_SCALES = [
    ("Dark Triad", "Dark Triad", "Composite of Machiavellianism, Narcissism, and Psychopathy"),
    ("Machiavellianism", "Machiavellianism", "Machiavellianism sub-scale of the Dark Triad"),
    ("Psychopathy", "Psychopathy", "Psychopathy sub-scale of the Dark Triad"),
]


@dataclass
class Scale:
    """A psychometric scale in the analysis engine.

    Grounding: "The repo has 10 built-in psychometric scales. One, ECE one,
    R to the WA, right-wing authoritarianism."
    """

    abbreviation: str
    name: str
    description: str

    def __hash__(self) -> int:
        return hash(self.abbreviation)


@dataclass
class PsychometricWorkload:
    """The demo workload from the transcript: a psychometric analysis engine.

    Manages a catalog of built-in validated scales, can analyse missing
    scales, expand the catalog, and review front-end components.

    Grounding: "10 built-in validated scales to 12 built-in validated scales
    to reflect the additions."
    """

    scales: List[Scale] = field(default_factory=list)

    @classmethod
    def with_defaults(cls) -> PsychometricWorkload:
        """Create a workload initialised with the 10 built-in scales."""
        return cls(
            scales=[Scale(abbr, name, desc) for abbr, name, desc in _BUILT_IN_SCALES]
        )

    @property
    def built_in_count(self) -> int:
        """Return the number of built-in scales."""
        return len(self.scales)

    @property
    def scale_abbreviations(self) -> List[str]:
        return [s.abbreviation for s in self.scales]

    def has_scale(self, abbreviation: str) -> bool:
        return any(s.abbreviation.lower() == abbreviation.lower() for s in self.scales)

    def suggest_missing_scales(self) -> List[Scale]:
        """Return scales that are commonly used in AI ethics research but
        are missing from the current catalog.

        Grounding: the agent in the transcript suggests adding Dark Triad,
        Machiavellianism, and Psychopathy scales.
        """
        missing: List[Scale] = []
        for abbr, name, desc in _SUGGESTED_SCALES:
            if not self.has_scale(abbr):
                missing.append(Scale(abbr, name, desc))
        return missing

    def add_scale(self, scale: Scale) -> bool:
        """Add a scale to the catalog. Returns True if added, False if
        already present.

        Grounding: the transcript expands from 10 to 12 built-in
        validated scales.
        """
        if self.has_scale(scale.abbreviation):
            return False
        self.scales.append(scale)
        return True

    def expand_catalog(self, suggested: List[Scale]) -> int:
        """Add all suggested scales, returning the number actually added.

        Grounding: "10 built-in validated scales to 12" — adds 2+ scales.
        """
        count = 0
        for scale in suggested:
            if self.add_scale(scale):
                count += 1
        return count

    def review_front_end(self) -> List[str]:
        """Review what front-end components need updating after a scale
        addition.

        Grounding: "Looking at the front end, is there anything we're missing
        in the front end that would make this app better from the perspective
        of the scale you just added?"
        """
        components: List[str] = []
        for scale in self.scales:
            # Simulate front-end component checking: each scale needs
            # a results panel, a configuration form, and a documentation
            # section in the front end.
            if not self._has_frontend_component(scale, "results_panel"):
                components.append(f"results_panel_{scale.abbreviation}")
            if not self._has_frontend_component(scale, "config_form"):
                components.append(f"config_form_{scale.abbreviation}")
            if not self._has_frontend_component(scale, "doc_section"):
                components.append(f"doc_section_{scale.abbreviation}")
        return components

    @staticmethod
    def _has_frontend_component(scale: Scale, component_type: str) -> bool:
        """Simulate front-end component detection."""
        # In the transcript, the agent determined the front end needed
        # updating after adding scales. This is a simplified check.
        # Newly added scales (not in the original 10) lack front-end
        # components.
        original_abbrs = {s[0] for s in _BUILT_IN_SCALES}
        if scale.abbreviation in original_abbrs:
            return True
        return False


# =============================================================================
# VoiceAgentHub — central orchestrator
# =============================================================================


class VoiceAgentHub:
    """Central orchestrator for voice-driven coding-agent orchestration.

    Integrates keyword-based intent parsing, agent targeting, command
    dispatch, interruption, and the demo psychometric workload.

    Grounding: the full transcript — voice commands, keyword-triggered
    workflows, multi-participant group calls, local data access, and
    interruption.
    """

    def __init__(
        self,
        session: Optional[GroupCallSession] = None,
        keyword_engine: Optional[KeywordEngine] = None,
        workload: Optional[PsychometricWorkload] = None,
    ) -> None:
        self.session = session or GroupCallSession()
        self.keyword_engine = keyword_engine or KeywordEngine()
        self.workload = workload or PsychometricWorkload.with_defaults()
        self._agents: Dict[str, CodingAgent] = {}

    def add_participant(self, participant: Participant) -> None:
        """Add a participant to the group-call session."""
        self.session.participants[participant.name] = participant
        if participant.agent is not None:
            self._agents[participant.agent.name] = participant.agent

    def add_agent(self, agent: CodingAgent) -> None:
        """Register a coding agent directly."""
        self._agents[agent.name] = agent

    def get_agent(self, name: str) -> Optional[CodingAgent]:
        return self._agents.get(name)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_utterance(self, text: str, speaker: str) -> List[VoiceCommand]:
        """Parse a spoken utterance into zero or more voice commands.

        Matches keyword rules, resolves target agent, and creates
        VoiceCommand objects.
        """
        self.session.add_utterance(speaker, text)

        matched_rules = self.keyword_engine.match(text)
        if not matched_rules:
            return []

        commands: List[VoiceCommand] = []
        for rule in matched_rules:
            target = self._resolve_target_agent(speaker, rule.intent)
            cmd = VoiceCommand(
                id=str(uuid.uuid4()),
                text=text,
                speaker=speaker,
                intent=rule.intent,
                target_agent=target or "unassigned",
                workflow_triggered=rule.description,
            )
            commands.append(cmd)

        # Register all commands
        for cmd in commands:
            self.session.add_command(cmd)

        return commands

    def _resolve_target_agent(
        self, speaker: str, intent: Intent
    ) -> Optional[str]:
        """Resolve the target agent for a command.

        Grounding: "control someone else's Claude Code or AI through my
        voice" — if the intent is CONTROL_AGENT, target a non-self agent.
        """
        if intent == Intent.CONTROL_AGENT:
            # Find another participant's agent
            for name, participant in self.session.participants.items():
                if name != speaker and participant.agent is not None:
                    return participant.agent.name
            return None

        # Default: use the speaker's own agent
        speaker_participant = self.session.participants.get(speaker)
        if speaker_participant is not None and speaker_participant.agent is not None:
            return speaker_participant.agent.name

        # Fallback: pick any available agent
        if self._agents:
            return next(iter(self._agents.keys()))
        return None

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def dispatch(
        self,
        command: VoiceCommand,
        runner: Optional[Callable[[VoiceCommand], None]] = None,
    ) -> VoiceCommand:
        """Dispatch a voice command to the target agent for execution.

        Args:
            command: The voice command to dispatch.
            runner: A callable that actually runs the command. If None,
                the command is merely marked as dispatched.

        Returns:
            The command with updated status.
        """
        target = self._agents.get(command.target_agent)
        if target is None:
            command.status = VoiceCommandStatus.FAILED
            return command

        command.status = VoiceCommandStatus.DISPATCHED

        try:
            target.assign_task(command)
            if runner is not None:
                runner(command)
            target.complete_task()
        except ValueError:
            command.status = VoiceCommandStatus.FAILED

        return command

    def dispatch_async(
        self,
        command: VoiceCommand,
        runner: Optional[Callable[[VoiceCommand], None]] = None,
    ) -> VoiceCommand:
        """Dispatch a command without waiting for completion (simulated)."""
        target = self._agents.get(command.target_agent)
        if target is None:
            command.status = VoiceCommandStatus.FAILED
            return command

        command.status = VoiceCommandStatus.DISPATCHED
        try:
            target.assign_task(command)
            command.status = VoiceCommandStatus.RUNNING
        except ValueError:
            command.status = VoiceCommandStatus.FAILED

        return command

    # ------------------------------------------------------------------
    # Interruption
    # ------------------------------------------------------------------

    def interrupt(self, agent_name: str) -> bool:
        """Interrupt the currently running task on a coding agent.

        Grounding: "that kind of process of interruption because I see
        an opportunity in the future where this..."

        Returns True if an agent was interrupted.
        """
        agent = self._agents.get(agent_name)
        if agent is None or not agent.is_busy:
            return False
        agent.interrupt()
        return True

    # ------------------------------------------------------------------
    # Local data access
    # ------------------------------------------------------------------

    def can_access_local_data(self, agent_name: str) -> bool:
        """Check whether an agent is allowed to access local data.

        Grounding: "immediately access all of that data that's locally
        on their computer."
        """
        agent = self._agents.get(agent_name)
        if agent is None:
            return False
        return agent.local_data_allowed

    def grant_local_data_access(self, agent_name: str) -> None:
        """Grant local data access to a coding agent."""
        agent = self._agents.get(agent_name)
        if agent is not None:
            agent.local_data_allowed = True

    def revoke_local_data_access(self, agent_name: str) -> None:
        """Revoke local data access from a coding agent."""
        agent = self._agents.get(agent_name)
        if agent is not None:
            agent.local_data_allowed = False

    # ------------------------------------------------------------------
    # Workflow trigger (keyword-triggered structured workflows)
    # ------------------------------------------------------------------

    def trigger_workflow(self, text: str, speaker: str) -> List[VoiceCommand]:
        """Parse an utterance, dispatch resulting commands, and return them.

        This is a convenience shortcut that combines parse + dispatch
        for keyword-triggered structured workflows.

        Grounding: "these structured workflows, all of these things are
        being triggered by keywords in conversations."
        """
        commands = self.parse_utterance(text, speaker)
        for cmd in commands:
            self.dispatch(cmd)
        return commands

    # ------------------------------------------------------------------
    # Demo workload helpers
    # ------------------------------------------------------------------

    def run_scale_review(self, speaker: str) -> Dict[str, object]:
        """Run the 'what scales are we missing?' workflow.

        Grounding: the transcript shows the agent running a review of
        missing psychometric scales.
        """
        missing = self.workload.suggest_missing_scales()
        count = self.workload.built_in_count
        return {
            "built_in_count": count,
            "missing_scales": [s.abbreviation for s in missing],
            "missing_count": len(missing),
        }

    def run_catalog_expansion(self, speaker: str) -> Dict[str, object]:
        """Run the catalog expansion workflow (10 -> 12 built-in scales).

        Grounding: "10 built-in validated scales to 12 built-in validated
        scales to reflect the additions."
        """
        missing = self.workload.suggest_missing_scales()
        added = self.workload.expand_catalog(missing)
        return {
            "before_count": len(self.workload.scales) - added,
            "added_count": added,
            "after_count": self.workload.built_in_count,
        }

    def run_frontend_review(self, speaker: str) -> Dict[str, object]:
        """Run the front-end review workflow.

        Grounding: "Looking at the front end, is there anything we're
        missing in the front end that would make this app better from
        the perspective of the scale you just added?"
        """
        components = self.workload.review_front_end()
        return {
            "missing_components": components,
            "missing_count": len(components),
        }

    # ------------------------------------------------------------------
    # Session state
    # ------------------------------------------------------------------

    @property
    def command_count(self) -> int:
        return self.session.command_count

    @property
    def utterance_count(self) -> int:
        return self.session.utterance_count

    @property
    def active_agents(self) -> List[str]:
        return [name for name, agent in self._agents.items() if agent.is_busy]

    @property
    def participant_names(self) -> List[str]:
        return list(self.session.participants.keys())