"""prd_audit — pure-logic PRD-gated workflow engine.

Grounded in JEVanClief's "I'm Building a Custom Front End for Claude Code"
(J2GLzkaUrBc).  The transcript teaches a PRD-gated build workflow:

  1. Have Claude generate a PRD markdown document for the WHOLE task BEFORE
     building anything ("I'm actually going to have it make a PRD document...
     a PRD markdown of this for Claude code... that describes what we are
     trying to do and breaks down steps and structure for early phase to late
     phase, right? So, just trying to get it to kind of break it into steps
     rather than build the whole thing at once.").
  2. Feed that PRD to a SECOND auditor instance to re-review it ("you can
     actually feed this into another version of Claude and have it act as
     that auditor and it can kind of redo it there, which is really cool.").
  3. Drop the approved PRD into a workspace and execute against it ("When
     this is done, I can download it, drop it into my workspace, and actually
     have it build the front end inside of this workspace... 'Hey, read the
     PRD for the front end.'").

This module encodes that gate in pure, deterministic, stdlib-only Python:

  * :class:`PrdDocument`       — a structured product-requirements document
    with the canonical sections: goals, scope, acceptance-criteria, risks,
    tasks.  Parsed from / serialized to markdown.
  * :class:`PrdValidator`      — the "second auditor" instance.  Runs
    deterministic completeness / vagueness / scope-creep / test-coverage
    checks and produces :class:`AuditFinding` items with a severity.
    (Also exported as ``Auditor``.)
  * :class:`PrdGate`           — the execution gate.  Blocks execution until
    the audit passes a configurable threshold, mirroring "drop it into the
    workspace and build against it" only once the PRD is sound.

No network, no numpy/pandas/requests — pure stdlib (re, dataclasses, enum).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

__all__ = [
    "AuditSeverity",
    "AuditFinding",
    "AuditReport",
    "Task",
    "PrdDocument",
    "PrdValidator",
    "Auditor",
    "PrdGate",
    "GateDecision",
    "PrdGateBlocked",
    "audit_prd",
    "SECTIONS",
]

# ---------------------------------------------------------------------------
# Canonical section model
# ---------------------------------------------------------------------------

#: Canonical PRD sections (order matters for serialization / reporting).
SECTIONS: Tuple[str, ...] = (
    "goals",
    "scope",
    "acceptance-criteria",
    "risks",
    "tasks",
)

#: Accepted markdown header spellings -> canonical key.
_SECTION_SYNONYMS: Dict[str, str] = {
    "goal": "goals",
    "goals": "goals",
    "objective": "goals",
    "objectives": "goals",
    "scope": "scope",
    "in-scope": "scope",
    "in scope": "scope",
    "acceptance criteria": "acceptance-criteria",
    "acceptance-criteria": "acceptance-criteria",
    "acceptance": "acceptance-criteria",
    "risks": "risks",
    "risk": "risks",
    "risk register": "risks",
    "tasks": "tasks",
    "task": "tasks",
    "steps": "tasks",
    "plan": "tasks",
}

_SEP_RE = re.compile(r"[^a-z0-9]+")


def _norm_header(text: str) -> str:
    """Normalise a markdown header name to a lookup key."""
    return _SEP_RE.sub(" ", text.strip().lower()).strip()


def _resolve_section(header: str) -> Optional[str]:
    """Map a raw markdown header to a canonical section key (or ``None``)."""
    norm = _norm_header(header)
    if norm in _SECTION_SYNONYMS:
        return _SECTION_SYNONYMS[norm]
    # fuzzy: drop leading 'product requirement' style qualifiers
    for alias, canon in _SECTION_SYNONYMS.items():
        if norm.endswith(" " + alias) or norm.endswith(alias):
            return canon
    return None


# ---------------------------------------------------------------------------
# Core domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """A single planned step in the PRD's task breakdown.

    Grounding: the transcript explicitly asks Claude to "break it into steps
    rather than build the whole thing at once" and to describe "steps and
    structure for early phase to late phase".
    """

    id: str
    description: str
    acceptance_test: Optional[str] = None
    done: bool = False

    @property
    def is_planned(self) -> bool:
        return not self.done

    @property
    def has_acceptance_test(self) -> bool:
        return bool(self.acceptance_test and self.acceptance_test.strip())


class AuditSeverity(Enum):
    """Severity of a single audit finding.  Ordering is intentional.

    Deterministic ordering lets a gate reason about *error* vs *warning*
    budgets: INFO < WARNING < ERROR.
    """

    INFO = 0
    WARNING = 1
    ERROR = 2

    #: numeric weight used for scoring (deterministic).
    @property
    def weight(self) -> int:
        return self.value

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, AuditSeverity):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: object) -> bool:
        if not isinstance(other, AuditSeverity):
            return NotImplemented
        return self.value <= other.value

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, AuditSeverity):
            return NotImplemented
        return self.value > other.value

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, AuditSeverity):
            return NotImplemented
        return self.value >= other.value


@dataclass(frozen=True)
class AuditFinding:
    """A single deterministic audit finding.

    Attributes:
        code:        stable machine-readable rule identifier.
        severity:    :class:`AuditSeverity`.
        section:     canonical section the finding belongs to (or ``"document"``).
        message:     human-readable explanation.
        suggestion:  optional remediation hint.
    """

    code: str
    severity: AuditSeverity
    section: str
    message: str
    suggestion: str = ""

    def __lt__(self, other: "AuditFinding") -> bool:
        # Sort by severity (higher first), then code — deterministic ordering.
        return (self.severity.value, self.code) > (other.severity.value, other.code)


class PrdDocument:
    """Structured product requirements document.

    Holds the five canonical sections as structured data and can be parsed
    from / serialized to the markdown form that a Claude-code build workflow
    drops into a workspace.
    """

    def __init__(
        self,
        title: str = "Untitled PRD",
        goals: Optional[Iterable[str]] = None,
        scope: Optional[Iterable[str]] = None,
        out_of_scope: Optional[Iterable[str]] = None,
        acceptance_criteria: Optional[Iterable[str]] = None,
        risks: Optional[Iterable[str]] = None,
        tasks: Optional[Iterable[Task]] = None,
    ) -> None:
        self.title: str = title.strip() or "Untitled PRD"
        self.goals: List[str] = _as_list(goals)
        self.scope: List[str] = _as_list(scope)
        self.out_of_scope: List[str] = _as_list(out_of_scope)
        self.acceptance_criteria: List[str] = _as_list(acceptance_criteria)
        self.risks: List[str] = _as_list(risks)
        self.tasks: List[Task] = list(tasks or [])

    # -- completeness -------------------------------------------------------

    @property
    def missing_sections(self) -> List[str]:
        """Canonical sections that are absent or empty."""
        return [s for s in SECTIONS if not self.content_of(s)]

    @property
    def is_complete(self) -> bool:
        return not self.missing_sections

    def content_of(self, section: str) -> List[str]:
        """Return the raw content list for a canonical section key."""
        key = section.lower().replace("-", "-")
        if key == "goals":
            return self.goals
        if key == "scope":
            return self.scope
        if key in ("acceptance-criteria", "acceptance_criteria"):
            return self.acceptance_criteria
        if key == "risks":
            return self.risks
        if key == "tasks":
            return [t.description for t in self.tasks]
        raise KeyError(f"unknown section: {section!r}")

    # -- construction helpers ----------------------------------------------

    def add_goal(self, goal: str) -> "PrdDocument":
        self.goals.append(goal)
        return self

    def add_acceptance_criterion(self, criterion: str) -> "PrdDocument":
        self.acceptance_criteria.append(criterion)
        return self

    def add_risk(self, risk: str) -> "PrdDocument":
        self.risks.append(risk)
        return self

    def add_task(self, task: Task) -> "PrdDocument":
        self.tasks.append(task)
        return self

    # -- markdown round-trip -----------------------------------------------

    @classmethod
    def from_markdown(cls, markdown: str) -> "PrdDocument":
        """Parse a PRD markdown document into a :class:`PrdDocument`.

        Recognises ``#``-style section headers (any depth) via
        :func:`_resolve_section`; bullet items (``-``/``*``) under a section
        become list entries.  Task bullets may carry a completion checkbox
        (``- [x]`` / ``- [ ]``) and an acceptance test as a ``(test: ...)``
        or ``[test] ...`` suffix.
        """
        title = "Untitled PRD"
        title_m = re.search(r"^\s*#\s+(.+?)\s*$", markdown, re.MULTILINE)
        if title_m and _resolve_section(title_m.group(1)) is None:
            title = title_m.group(1).strip()

        current: Optional[str] = None
        raw: Dict[str, List[str]] = {s: [] for s in SECTIONS}
        out_of_scope: List[str] = []

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            header = re.match(r"^#{1,6}\s+(.+)$", line)
            if header:
                section = _resolve_section(header.group(1).strip())
                current = section
                if section == "scope":
                    # remember explicit out-of-scope bullets separately
                    pass
                continue
            if current is None:
                continue
            if line.startswith("out of scope"):
                current = None
                continue
            # bullet or plain text
            item = _strip_bullet(line)
            if current == "scope" and _norm_header(item).startswith("out of scope"):
                out_of_scope.append(_strip_out_of_scope(item))
                continue
            # keep the raw line for the tasks section so checkbox/tests survive
            raw[current].append(line if current == "tasks" else item)

        tasks = [_parse_task_bullet(b) for b in raw["tasks"]]

        return cls(
            title=title,
            goals=raw["goals"],
            scope=raw["scope"],
            out_of_scope=out_of_scope,
            acceptance_criteria=raw["acceptance-criteria"],
            risks=raw["risks"],
            tasks=tasks,
        )

    def to_markdown(self) -> str:
        """Serialize the document back to PRD markdown."""
        lines: List[str] = [f"# {self.title}", ""]
        _emit(lines, "Goals", self.goals)
        _emit(lines, "Scope", self.scope)
        if self.out_of_scope:
            lines.append("### Out of scope")
            for item in self.out_of_scope:
                lines.append(f"- {item}")
            lines.append("")
        _emit(lines, "Acceptance criteria", self.acceptance_criteria)
        _emit(lines, "Risks", self.risks)
        lines.append("## Tasks")
        if self.tasks:
            for t in self.tasks:
                box = "[x]" if t.done else "[ ]"
                test = f" (test: {t.acceptance_test})" if t.acceptance_test else ""
                lines.append(f"- {box} {t.description}{test}")
        else:
            lines.append("- [ ] (no tasks defined)")
        lines.append("")
        return "\n".join(lines)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"PrdDocument(title={self.title!r}, "
            f"goals={len(self.goals)}, scope={len(self.scope)}, "
            f"criteria={len(self.acceptance_criteria)}, risks={len(self.risks)}, "
            f"tasks={len(self.tasks)})"
        )


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------


def _as_list(items: Optional[Iterable[str]]) -> List[str]:
    if items is None:
        return []
    return [str(i).strip() for i in items if str(i).strip()]


def _strip_bullet(line: str) -> str:
    """Remove leading bullet/markdown markers from a line."""
    m = re.match(r"^[-*+]\s*(\[[ xX]\]\s*)?(.*)$", line)
    if m:
        return m.group(2).strip()
    return line


_TASK_TEST_RE = re.compile(r"^(?P<desc>.+?)[\s(]+(?P<tag>test:)\s*(?P<test>.+?)[)\]]?$", re.IGNORECASE)


def _parse_task_bullet(line: str) -> Task:
    """Parse a task bullet into a :class:`Task`, extracting an acceptance test."""
    done = bool(re.match(r"^[-*+]\s*\[[xX]\]", line))
    desc = _strip_bullet(line)
    acceptance_test: Optional[str] = None
    m = _TASK_TEST_RE.match(desc)
    if m:
        test = m.group("test").strip()
        # a "test:" suffix inside parens/brackets
        if test.endswith(")") or test.endswith("]"):
            test = test[:-1].strip()
        # drop a wrapping pair of quotes left over from the source markdown
        if len(test) >= 2 and test[0] in "'\"" and test[-1] == test[0]:
            test = test[1:-1].strip()
        if test:
            acceptance_test = test
            desc = m.group("desc").strip().rstrip("( ")
    return Task(id=_slug(desc), description=desc or line, acceptance_test=acceptance_test, done=done)


def _slug(text: str) -> str:
    """Deterministic short id for a task description."""
    words = re.findall(r"[a-zA-Z0-9]+", text.lower())[:3]
    return "_".join(words) if words else "task"


def _strip_out_of_scope(line: str) -> str:
    """Strip a leading 'out of scope' qualifier from a bullet."""
    return re.sub(r"^out\s+of\s+scope[\s:,-]*", "", line, flags=re.IGNORECASE).strip()


def _emit(lines: List[str], heading: str, items: List[str]) -> None:
    lines.append(f"## {heading}")
    if items:
        for item in items:
            lines.append(f"- {item}")
    else:
        lines.append("(none)")
    lines.append("")


# ---------------------------------------------------------------------------
# Heuristics for the auditor
# ---------------------------------------------------------------------------

#: Terms that make an acceptance criterion vague / unmeasurable.
_VAGUE_TERMS: Tuple[str, ...] = (
    "etc",
    "etc.",
    "et cetera",
    "stuff",
    "things",
    "as needed",
    "when needed",
    "as appropriate",
    "fast",
    "quickly",
    "better",
    "nicely",
    "good",
    "easy",
    "maybe",
    "probably",
    "should work",
    "just works",
    "basically",
    "whatever",
    "tbd",
    "todo",
    "later",
    "and so on",
)

#: Terms suggesting open-ended scope / scope creep.
_SCOPE_CREEP_TERMS: Tuple[str, ...] = (
    "and more",
    "and so on",
    "etc",
    "et cetera",
    "eventually",
    "later",
    "maybe",
    "could also",
    "also could",
    "we'll see",
    "we will see",
    "in the future",
    "phase 2",
    "phase ii",
    "v2",
    "backlog",
    "out of scope for now",
    "whatever else",
)

#: Words that imply a measurable, testable target.
_MEASURABLE_MARKERS: Tuple[str, ...] = (
    "must",
    "shall",
    "will",
    "expect",
    "within",
    "under",
    "at least",
    "no more than",
    "at most",
    "exactly",
    "%",
    "ms",
    "seconds",
    "minutes",
    "hours",
    "times",
    "p95",
    "p99",
    "concurrent",
    "requests",
)

_MIN_CRITERION_LEN = 12


def _has_measurable_target(text: str) -> bool:
    """True if the text carries a numeric token or a measurable keyword."""
    lowered = text.lower()
    if re.search(r"\d", lowered):
        return True
    return any(marker in lowered for marker in _MEASURABLE_MARKERS)


def _contains_vague_term(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _VAGUE_TERMS)


def _contains_scope_creep(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _SCOPE_CREEP_TERMS)


# ---------------------------------------------------------------------------
# Audit report
# ---------------------------------------------------------------------------


@dataclass
class AuditReport:
    """Aggregate result of running the :class:`PrdValidator` over a PRD."""

    document_title: str
    findings: List[AuditFinding] = field(default_factory=list)

    def add(self, finding: AuditFinding) -> "AuditReport":
        self.findings.append(finding)
        return self

    # -- severity buckets ---------------------------------------------------

    def by_severity(self, severity: AuditSeverity) -> List[AuditFinding]:
        return [f for f in self.findings if f.severity is severity]

    @property
    def errors(self) -> List[AuditFinding]:
        return self.by_severity(AuditSeverity.ERROR)

    @property
    def warnings(self) -> List[AuditFinding]:
        return self.by_severity(AuditSeverity.WARNING)

    @property
    def info(self) -> List[AuditFinding]:
        return self.by_severity(AuditSeverity.INFO)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def total(self) -> int:
        return len(self.findings)

    # -- scoring ------------------------------------------------------------

    def weighted_score(self) -> int:
        """Deterministic weighted sum of findings (higher = worse)."""
        return sum(f.severity.weight for f in self.findings)

    def score(self) -> float:
        """Normalized readiness in [0.0, 1.0]; 1.0 is a perfect PRD.

        Score drops by severity weight, capped at 0.0.  A perfect PRD with no
        findings scores 1.0.
        """
        total_weight = self.weighted_score()
        return max(0.0, 1.0 - (total_weight / 100.0))

    def passes(self, *, max_errors: int = 0, max_warnings: int = 10, min_score: float = 0.6) -> bool:
        """Deterministic pass/fail against a gate threshold."""
        return (
            self.error_count <= max_errors
            and self.warning_count <= max_warnings
            and self.score() >= min_score
        )

    def sorted_findings(self) -> List[AuditFinding]:
        return sorted(self.findings)

    def to_dict(self) -> Dict[str, object]:
        return {
            "title": self.document_title,
            "total": self.total,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "info": len(self.info),
            "score": round(self.score(), 4),
            "findings": [
                {
                    "code": f.code,
                    "severity": f.severity.name,
                    "section": f.section,
                    "message": f.message,
                    "suggestion": f.suggestion,
                }
                for f in self.sorted_findings()
            ],
        }


# ---------------------------------------------------------------------------
# The auditor (second-instance re-reviewer)
# ---------------------------------------------------------------------------


class PrdValidator:
    """Deterministic PRD auditor.

    Grounding: the transcript has a *second* Claude instance act as an auditor
    that re-reviews the generated PRD before it is dropped into the workspace.
    This class encodes that review as a fixed set of deterministic rules, so
    the same input always yields the same findings (no LLM in the loop).
    """

    def __init__(
        self,
        *,
        max_goals: int = 8,
        scope_creep_terms: Optional[Iterable[str]] = None,
    ) -> None:
        self.max_goals = max_goals
        self.scope_creep_terms = tuple(scope_creep_terms) if scope_creep_terms else _SCOPE_CREEP_TERMS

    # -- public API ---------------------------------------------------------

    def validate(self, document: PrdDocument) -> AuditReport:
        """Run every rule over the document and return the report."""
        report = AuditReport(document_title=document.title)
        self._check_required_sections(document, report)
        self._check_measurable_goals(document, report)
        self._check_vague_acceptance_criteria(document, report)
        self._check_acceptance_tests(document, report)
        self._check_scope_creep(document, report)
        self._check_risks(document, report)
        return report

    # -- rules --------------------------------------------------------------

    def _check_required_sections(self, doc: PrdDocument, report: AuditReport) -> None:
        """Every canonical section must be present and non-empty."""
        for section in SECTIONS:
            if not doc.content_of(section):
                report.add(
                    AuditFinding(
                        code="MISSING_SECTION",
                        severity=AuditSeverity.ERROR,
                        section=section,
                        message=f"Required PRD section '{section}' is missing or empty.",
                        suggestion=(
                            f"Add a '## {section}' section describing the "
                            "deliverable before executing."
                        ),
                    )
                )

    def _check_measurable_goals(self, doc: PrdDocument, report: AuditReport) -> None:
        """Goals that are vague or too numerous are a planning smell."""
        if not doc.goals:
            return  # already flagged as MISSING_SECTION
        for goal in doc.goals:
            if _contains_vague_term(goal) and not _has_measurable_target(goal):
                report.add(
                    AuditFinding(
                        code="VAGUE_GOAL",
                        severity=AuditSeverity.WARNING,
                        section="goals",
                        message=(
                            f"Goal contains vague language and no measurable "
                            f"target: {goal!r}"
                        ),
                        suggestion="Reword the goal with a concrete, measurable outcome.",
                    )
                )
        if len(doc.goals) > self.max_goals:
            report.add(
                AuditFinding(
                    code="GOAL_PROLIFERATION",
                    severity=AuditSeverity.WARNING,
                    section="goals",
                    message=(
                        f"{len(doc.goals)} goals exceeds the recommended "
                        f"maximum of {self.max_goals}; objectives are drifting."
                    ),
                    suggestion="Consolidate goals around a single north-star outcome.",
                )
            )

    def _check_vague_acceptance_criteria(self, doc: PrdDocument, report: AuditReport) -> None:
        """Each acceptance criterion must be specific and testable."""
        for idx, criterion in enumerate(doc.acceptance_criteria, start=1):
            if not _has_measurable_target(criterion) and (
                len(criterion) < _MIN_CRITERION_LEN or _contains_vague_term(criterion)
            ):
                report.add(
                    AuditFinding(
                        code="VAGUE_ACCEPTANCE_CRITERION",
                        severity=AuditSeverity.ERROR,
                        section="acceptance-criteria",
                        message=(
                            f"Acceptance criterion #{idx} is vague and has no "
                            f"measurable target: {criterion!r}"
                        ),
                        suggestion=(
                            "Specify a verifiable threshold (e.g. numeric, "
                            "time-bound, or a 'must/shall' invariant)."
                        ),
                    )
                )

    def _check_acceptance_tests(self, doc: PrdDocument, report: AuditReport) -> None:
        """If criteria exist, at least one task must carry an acceptance test."""
        if not doc.acceptance_criteria:
            return
        tested = [t for t in doc.tasks if t.has_acceptance_test]
        if not tested:
            report.add(
                AuditFinding(
                    code="NO_ACCEPTANCE_TESTS",
                    severity=AuditSeverity.ERROR,
                    section="tasks",
                    message=(
                        "Acceptance criteria are defined but no task provides "
                        "an acceptance test (none are marked '(test: ...)')."
                    ),
                    suggestion=(
                        "Add an acceptance test to each task, e.g. "
                        "'- [ ] Build endpoint (test: GET /health returns 200)'."
                    ),
                )
            )

    def _check_scope_creep(self, doc: PrdDocument, report: AuditReport) -> None:
        """Open-ended scope language is a scope-creep indicator."""
        scope_text = " ".join(doc.scope)
        goals_text = " ".join(doc.goals)
        combined = f"{scope_text} {goals_text} {_oob_text(doc)}"
        for term in self.scope_creep_terms:
            if term in combined.lower():
                report.add(
                    AuditFinding(
                        code="SCOPE_CREEP",
                        severity=AuditSeverity.WARNING,
                        section="scope",
                        message=(
                            f"Scope contains the open-ended term {term!r}; "
                            "boundaries are unclear and the build may drift."
                        ),
                        suggestion=(
                            "Narrow the scope to a concrete increment and move "
                            "the rest to an explicit 'Out of scope' list."
                        ),
                    )
                )
        if doc.out_of_scope and not _oob_text(doc).strip():
            pass
        # Unsized task explosion is also a creep signal.
        if len(doc.tasks) > 25:
            report.add(
                AuditFinding(
                    code="SCOPE_CREEP_TASK_EXPLOSION",
                    severity=AuditSeverity.WARNING,
                    section="tasks",
                    message=(
                        f"{len(doc.tasks)} tasks without clear prioritisation; "
                        "the plan has grown beyond a single buildable increment."
                    ),
                    suggestion="Split the plan into phases, each with its own PRD.",
                )
            )

    def _check_risks(self, doc: PrdDocument, report: AuditReport) -> None:
        """An empty risks register is itself a risk."""
        if not doc.risks:
            report.add(
                AuditFinding(
                    code="NO_RISKS",
                    severity=AuditSeverity.WARNING,
                    section="risks",
                    message="No risks were recorded in the PRD.",
                    suggestion=(
                        "List at least one concrete risk and its mitigation "
                        "before treating the PRD as build-ready."
                    ),
                )
            )


#: Alias matching the transcript's "auditor" role.
Auditor = PrdValidator


def _oob_text(doc: PrdDocument) -> str:
    return " ".join(doc.out_of_scope)


# ---------------------------------------------------------------------------
# The execution gate
# ---------------------------------------------------------------------------


class PrdGateBlocked(Exception):
    """Raised when a PRD does not clear the audit threshold."""

    def __init__(self, decision: "GateDecision") -> None:
        self.decision = decision
        super().__init__(decision.reason)


@dataclass(frozen=True)
class GateDecision:
    """Outcome of a :class:`PrdGate` evaluation."""

    approved: bool
    score: float
    errors: int
    warnings: int
    reason: str
    report: AuditReport


class PrdGate:
    """Execution gate that blocks until the audit passes a threshold.

    Grounding: the workflow only drops the PRD into the workspace *after* it
    has been written and audited.  This gate enforces that ordering: if the
    audit does not clear ``max_errors`` / ``max_warnings`` / ``min_score``,
    execution is blocked and no build proceeds against an unsound PRD.
    """

    def __init__(
        self,
        *,
        max_errors: int = 0,
        max_warnings: int = 10,
        min_score: float = 0.6,
        validator: Optional[PrdValidator] = None,
    ) -> None:
        if max_errors < 0 or max_warnings < 0:
            raise ValueError("error/warning budgets must be >= 0")
        if not (0.0 <= min_score <= 1.0):
            raise ValueError("min_score must be in [0.0, 1.0]")
        self.max_errors = max_errors
        self.max_warnings = max_warnings
        self.min_score = min_score
        self.validator = validator or PrdValidator()

    # -- core ---------------------------------------------------------------

    def evaluate(self, report: AuditReport) -> GateDecision:
        """Evaluate a finished audit report against the threshold."""
        approved = report.passes(
            max_errors=self.max_errors,
            max_warnings=self.max_warnings,
            min_score=self.min_score,
        )
        if approved:
            reason = (
                f"PRD cleared gate: score={report.score():.2f} "
                f"(errors={report.error_count}/{self.max_errors}, "
                f"warnings={report.warning_count}/{self.max_warnings})."
            )
        else:
            reason = (
                f"PRD BLOCKED: score={report.score():.2f} "
                f"(errors={report.error_count}/{self.max_errors}, "
                f"warnings={report.warning_count}/{self.max_warnings}). "
                "Revise the PRD and re-audit before executing."
            )
        return GateDecision(
            approved=approved,
            score=report.score(),
            errors=report.error_count,
            warnings=report.warning_count,
            reason=reason,
            report=report,
        )

    def enforce(self, report: AuditReport) -> GateDecision:
        """Like :meth:`evaluate` but raises :class:`PrdGateBlocked` on failure."""
        decision = self.evaluate(report)
        if not decision.approved:
            raise PrdGateBlocked(decision)
        return decision

    def evaluate_document(self, document: PrdDocument) -> GateDecision:
        """Audit a document and gate it in one step."""
        report = self.validator.validate(document)
        return self.evaluate(report)

    def enforce_document(self, document: PrdDocument) -> GateDecision:
        """Audit and gate a document, blocking on failure."""
        report = self.validator.validate(document)
        return self.enforce(report)


def audit_prd(
    markdown_or_doc: str,
    validator: Optional[PrdValidator] = None,
) -> AuditReport:
    """Audit a PRD given as markdown (or a :class:`PrdDocument`).

    Convenience entry point mirroring the transcript step of handing the
    generated PRD to the second auditor instance for re-review.
    """
    doc = markdown_or_doc if isinstance(markdown_or_doc, PrdDocument) else PrdDocument.from_markdown(markdown_or_doc)
    return (validator or PrdValidator()).validate(doc)
