"""Multiplayer agent triage — pure-stdlib problem/wins classifier.

Grounded in the JEVanClief transcript *"Alpha Launch 24 Hours in: AI multiplayer
Problems and Wins!"* (https://www.youtube.com/watch?v=e3RgzvuYTBY). The video is a
post-mortem of the first 24 hours of an AI *multiplayer* product — many human
users and AI coding agents operating together inside one shared workspace. The
creator catalogues the concrete failures seen at alpha scale and the wins that
made the launch promising.

Failures observed in the transcript (these become the triage categories):
  - Requests reading too large a slice of a workspace/container.
  - Deployments failing (Azure blob storage / file-name "naming" issues that
    leave an agent stuck in "thinking mode").
  - Workspace files not showing even though the agent had access (a deployment
    glitch).
  - A read failing the sandbox / "can't return the turn" — which needed a
    fallback so the whole system does not crash.
  - Token-usage / cost monitoring (the creator worried about API fees).

Wins observed in the transcript:
  - Token efficiency: every user together barely spent $30 in a day (vs the
    creator dropping ~$200 solo), through hundreds of files and tool calls.
  - A knowledge-corpus upload (Ari's markdown website of loops/folders/ideas)
    that the agent can research and recommend from.
  - A community "choose your own adventure" template with memories/states/casts.
  - Explainers/animations and workflow processes (Craig's videos).
  - Organizations / shared workspaces enabling people to work together
    ("the Google Docs of AI").

This module exposes a network-free, deterministic triage engine that classifies
such observations into problem/win categories, assigns a severity, computes a
confidence score, and aggregates an incident summary. It is stdlib-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "SEVERITIES",
    "PROBLEM_TYPES",
    "WIN_TYPES",
    "TriageResult",
    "WinRecord",
    "MultiplayerTriageEngine",
    "classify_problem",
    "classify_win",
    "analyze_token_spend",
    "summarize_incidents",
]

# Ordered from least to most severe.
SEVERITIES: List[str] = ["low", "medium", "high", "critical"]

_SEVERITY_WEIGHT: Dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

# ---------------------------------------------------------------------------
# Problem categories grounded in the transcript.
# Each spec: keywords matched (case-insensitive) against symptom text, a
# recommended remediation drawn from what the creator said he was doing to fix
# the issue, and a default severity.
# ---------------------------------------------------------------------------
PROBLEM_TYPES: Dict[str, Dict[str, Any]] = {
    "read_size": {
        "keywords": [
            "large read", "read size", "how large", "request", "response",
            "workspace read", "container", "chunk",
        ],
        "action": (
            "Reduce per-request read size; containerize requests and cap the "
            "workspace read slice so one large read cannot stall a turn."
        ),
        "default_severity": "medium",
    },
    "deployment": {
        "keywords": [
            "deploy", "blob", "azure", "file name", "naming", "upload",
            "zip", "not deploying", "deployment",
        ],
        "action": (
            "Verify file names and storage deployment path; fix the Azure blob "
            "naming problem and redeploy the workspace/ICM."
        ),
        "default_severity": "high",
    },
    "file_visibility": {
        "keywords": [
            "workspace", "file", "not showing", "visibility", "glitch",
            "didn't show", "did not show", "access",
        ],
        "action": (
            "Re-sync the workspace file index; the agent had access but the "
            "files were not surfaced — likely a deployment glitch."
        ),
        "default_severity": "medium",
    },
    "sandbox": {
        "keywords": [
            "sandbox", "fail", "failed", "crash", "return the turn", "turn",
            "timeout", "can't return", "cannot return",
        ],
        "action": (
            "Wrap reads with a safe fallback so a sandbox failure returns the "
            "turn cleanly instead of crashing the whole system."
        ),
        "default_severity": "high",
    },
    "stuck_thinking": {
        "keywords": [
            "stuck", "thinking mode", "infinite", "hang", "loop",
            "not responding",
        ],
        "action": (
            "Add a loop guard; agents stuck in thinking mode usually follow a "
            "deployment/naming problem — correct the inputs and retry."
        ),
        "default_severity": "high",
    },
    "token_usage": {
        "keywords": [
            "token", "cost", "spend", "api fee", "rate limit", "expensive",
            "tokens per minute", "budget",
        ],
        "action": (
            "Monitor token spend per agent and per organization; set budget "
            "alerts and verify rate-limit headroom before scaling access."
        ),
        "default_severity": "low",
    },
}

# ---------------------------------------------------------------------------
# Win categories grounded in the transcript.
# ---------------------------------------------------------------------------
WIN_TYPES: Dict[str, Dict[str, Any]] = {
    "token_efficiency": {
        "keywords": [
            "token", "cost", "spend", "fee", "efficient", "cheap", "saved",
            "rate limit",
        ],
        "title": "Efficient shared token usage",
        "notes": (
            "Many users together spent far less than a single heavy session, "
            "through hundreds of files, tool calls and different chats."
        ),
    },
    "knowledge_corpus": {
        "keywords": [
            "knowledge", "corpus", "markdown", "index", "research",
            "recommend", "wiki", "documentation", "examples",
        ],
        "title": "Shared knowledge corpus",
        "notes": (
            "Uploaded markdown/docs become an index the agent can research and "
            "recommend from for any new chat."
        ),
    },
    "community_template": {
        "keywords": [
            "choose your own", "adventure", "template", "multiverse",
            "memories", "states", "casts", "d&d", "dnd",
        ],
        "title": "Community template with memories and states",
        "notes": (
            "A single-model folder/zip template that tracks what happened and "
            "when, enabling interactive experiences."
        ),
    },
    "collaboration": {
        "keywords": [
            "organization", "org", "shared workspace", "team", "collaborate",
            "work together", "access", "google docs",
        ],
        "title": "Cross-user collaboration",
        "notes": (
            "People form organizations, control access, and work together in "
            "shared workspaces — the 'Google Docs of AI' goal."
        ),
    },
    "workflow_automation": {
        "keywords": [
            "explainer", "animation", "video", "process", "workflow",
            "automate", "phases", "kicking off",
        ],
        "title": "Workflow automation",
        "notes": (
            "Users chain processes/phases, including explainer videos and "
            "animations, inside the workspace."
        ),
    },
}


@dataclass
class TriageResult:
    """Result of classifying a single multiplayer-agent problem observation.

    Attributes:
        problem_type: One of ``PROBLEM_TYPES`` keys.
        severity: One of ``SEVERITIES``.
        confidence: Fraction of the category's keywords matched (0.0-1.0).
        matched_signals: The keyword substrings actually matched.
        symptom: The original symptom text (truncated for storage).
        recommended_action: Remediation drawn from the transcript.
        is_critical: True when severity is "high" or "critical".
    """

    problem_type: str
    severity: str
    confidence: float
    matched_signals: List[str] = field(default_factory=list)
    symptom: str = ""
    recommended_action: str = ""
    is_critical: bool = False


@dataclass
class WinRecord:
    """A classified "win" — something that went well at alpha scale."""

    win_type: str
    title: str
    notes: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


def _norm(text: str) -> str:
    """Lower-case and collapse whitespace for keyword matching."""
    return " ".join(str(text).lower().split())


def _match_category(text: str, keywords: Sequence[str]) -> List[str]:
    """Return the subset of keywords that appear in the normalized text."""
    return [kw for kw in keywords if kw in text]


def classify_problem(
    observation: Dict[str, Any],
    default_severity: Optional[str] = None,
) -> TriageResult:
    """Classify a problem observation into one of the transcript's categories.

    ``observation`` should carry the symptom under ``symptom`` or
    ``description`` (both are scanned). An optional ``severity`` hint overrides
    the category default; ``default_severity`` is used when the text matches
    nothing.

    The most specific (most keyword matches) category wins. When multiple
    categories tie, they are ordered by keyword length so the more specific
    category is preferred, then by severity.
    """
    symptom = str(
        observation.get("symptom") or observation.get("description") or ""
    )
    text = _norm(symptom)
    hint_severity = str(
        observation.get("severity") or default_severity or ""
    ).lower()

    best_type: Optional[str] = None
    best_matches: List[str] = []
    best_ratio = 0.0

    for ptype, spec in PROBLEM_TYPES.items():
        keywords = spec["keywords"]
        matches = _match_category(text, keywords)
        if not matches:
            continue
        ratio = len(matches) / max(len(keywords), 1)
        # Prefer the category with more matches; break ties by a longer
        # matched keyword (more specific) and by severity weight.
        if (
            best_type is None
            or len(matches) > len(best_matches)
            or (
                len(matches) == len(best_matches)
                and max(map(len, matches)) > max(map(len, best_matches))
            )
        ):
            best_type = ptype
            best_matches = matches
            best_ratio = round(ratio, 2)

    if best_type is None:
        severity = hint_severity if hint_severity in SEVERITIES else "low"
        return TriageResult(
            problem_type="unknown",
            severity=severity,
            confidence=0.0,
            matched_signals=[],
            symptom=symptom,
            recommended_action=(
                "No known category matched; inspect logs and the deployment "
                "process before widening access."
            ),
            is_critical=severity in ("high", "critical"),
        )

    spec = PROBLEM_TYPES[best_type]
    if hint_severity in SEVERITIES:
        severity = hint_severity
    else:
        severity = spec["default_severity"]
        # Escalate when multiple distinct signals matched.
        if len(best_matches) >= 3:
            weight = _SEVERITY_WEIGHT[severity] + 1
            severity = SEVERITIES[min(weight, len(SEVERITIES)) - 1]

    return TriageResult(
        problem_type=best_type,
        severity=severity,
        confidence=best_ratio,
        matched_signals=best_matches,
        symptom=symptom,
        recommended_action=spec["action"],
        is_critical=severity in ("high", "critical"),
    )


def classify_win(observation: Dict[str, Any]) -> Optional[WinRecord]:
    """Classify a win observation into a transcript-grounded win category.

    The observation should carry a description (scanned for keywords) plus an
    optional ``metrics`` dict and ``notes``. Returns None when nothing matches.
    """
    description = str(observation.get("description") or "")
    text = _norm(description)

    best_type: Optional[str] = None
    best_matches: List[str] = []

    for wtype, spec in WIN_TYPES.items():
        matches = _match_category(text, spec["keywords"])
        if not matches:
            continue
        if (
            best_type is None
            or len(matches) > len(best_matches)
            or (
                len(matches) == len(best_matches)
                and max(map(len, matches)) > max(map(len, best_matches))
            )
        ):
            best_type = wtype
            best_matches = matches

    if best_type is None:
        return None

    spec = WIN_TYPES[best_type]
    metrics = dict(observation.get("metrics") or {})
    return WinRecord(
        win_type=best_type,
        title=spec["title"],
        notes=observation.get("notes") or spec["notes"],
        metrics=metrics,
    )


def analyze_token_spend(calls: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-agent token/cost spend across a set of API calls.

    Grounded in the transcript's cost win: the creator worried about "$200 in a
    single day" solo, while all alpha users together "barely spent $30 in API
    fees" across hundreds of files and processes.

    Each ``calls`` item may carry ``tokens`` and/or ``cost_usd`` and an optional
    ``agent`` label. Returns totals plus a per-agent breakdown.
    """
    total_tokens = 0
    total_cost = 0.0
    per_agent: Dict[str, Dict[str, float]] = {}

    for call in calls:
        tokens = int(call.get("tokens") or 0)
        cost = float(call.get("cost_usd") or 0.0)
        agent = str(call.get("agent") or "shared")
        total_tokens += tokens
        total_cost += cost
        bucket = per_agent.setdefault(agent, {"tokens": 0.0, "cost_usd": 0.0})
        bucket["tokens"] += tokens
        bucket["cost_usd"] += cost

    return {
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 2),
        "num_calls": len(calls),
        "per_agent": per_agent,
    }


def summarize_incidents(
    problems: Sequence[TriageResult],
    wins: Sequence[WinRecord],
) -> Dict[str, Any]:
    """Build a compact incident summary from classified problems and wins."""
    problem_counts: Dict[str, int] = {}
    severity_counts: Dict[str, int] = {}
    critical: List[str] = []
    for p in problems:
        problem_counts[p.problem_type] = problem_counts.get(p.problem_type, 0) + 1
        severity_counts[p.severity] = severity_counts.get(p.severity, 0) + 1
        if p.is_critical:
            critical.append(p.problem_type)

    win_counts: Dict[str, int] = {}
    for w in wins:
        win_counts[w.win_type] = win_counts.get(w.win_type, 0) + 1

    return {
        "problems": {
            "total": len(problems),
            "by_type": problem_counts,
            "by_severity": severity_counts,
            "critical_types": sorted(set(critical)),
        },
        "wins": {
            "total": len(wins),
            "by_type": win_counts,
        },
    }


class MultiplayerTriageEngine:
    """Stateful triage engine for multiplayer AI agent operations.

    Collects problem and win observations, classifies them, and exposes an
    aggregate summary plus the list of critical items that need attention
    before onboarding more users (mirroring the transcript's decision to keep
    the alpha small while fixing the biggest issues).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config: Dict[str, Any] = config or {}
        self._problems: List[TriageResult] = []
        self._wins: List[WinRecord] = []

    @property
    def problems(self) -> List[TriageResult]:
        """All problem observations triaged so far (read-only view)."""
        return list(self._problems)

    @property
    def wins(self) -> List[WinRecord]:
        """All win observations recorded so far (read-only view)."""
        return list(self._wins)

    def triage(self, observation: Dict[str, Any]) -> TriageResult:
        """Classify a problem observation and record it."""
        result = classify_problem(observation)
        self._problems.append(result)
        return result

    def record_win(self, observation: Dict[str, Any]) -> Optional[WinRecord]:
        """Classify a win observation and record it (None if no category)."""
        record = classify_win(observation)
        if record is not None:
            self._wins.append(record)
        return record

    def add_problem(self, result: TriageResult) -> None:
        """Directly add a pre-classified problem result."""
        self._problems.append(result)

    def add_win(self, record: WinRecord) -> None:
        """Directly add a pre-classified win record."""
        self._wins.append(record)

    def critical_items(self) -> List[TriageResult]:
        """Return problems that must be fixed before scaling access."""
        return [p for p in self._problems if p.is_critical]

    def summary(self) -> Dict[str, Any]:
        """Aggregate incident summary (counts by type/severity, critical list)."""
        base = summarize_incidents(self._problems, self._wins)
        base["critical_items"] = [
            {
                "problem_type": p.problem_type,
                "severity": p.severity,
                "action": p.recommended_action,
            }
            for p in self.critical_items()
        ]
        return base

    def token_spend(self, calls: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze a batch of API-call records for token/cost usage."""
        return analyze_token_spend(calls)
