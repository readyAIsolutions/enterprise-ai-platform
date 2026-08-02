"""
Documentation Standards
=======================
Enterprise documentation quality standards and validation.
Ensures documentation is current, searchable, versioned, owned,
task-oriented, example-driven, accessible, source-linked, and
part of the definition of done.

Quality Standards:
    1.  Current (not stale)
    2.  Searchable
    3.  Versioned
    4.  Owned
    5.  Task-oriented
    6.  Example-driven
    7.  Accessible
    8.  Linked to source
    9.  In definition of done
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import json
import logging
import re

logger = logging.getLogger(__name__)


class DocStatus(Enum):
    """Status of a documentation artifact."""
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    STALE = "stale"           # Not updated in SLA period
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class DocQualityGate(Enum):
    """Quality gates for documentation assessment."""
    CURRENT = "current"
    SEARCHABLE = "searchable"
    VERSIONED = "versioned"
    OWNED = "owned"
    TASK_ORIENTED = "task_oriented"
    EXAMPLE_DRIVEN = "example_driven"
    ACCESSIBLE = "accessible"
    SOURCE_LINKED = "source_linked"
    IN_DEFINITION_OF_DONE = "in_definition_of_done"


@dataclass
class DocStandard:
    """Definition of a documentation quality standard."""
    gate: DocQualityGate
    name: str
    description: str
    weight: float = 1.0  # Importance weight (0-1)
    sla_days: Optional[int] = None  # Max days before considered stale
    required_patterns: List[str] = field(default_factory=list)
    auto_check: bool = True
    fix_guide: str = ""


# --- Documentation Standards ---

DOC_STANDARDS: List[DocStandard] = [
    DocStandard(
        gate=DocQualityGate.CURRENT,
        name="Current",
        description=(
            "Documentation must be up to date. Content older than the SLA "
            "period without updates must be flagged as stale and reviewed."
        ),
        weight=1.0,
        sla_days=90,
        fix_guide="Review and update document content. Verify all commands, "
                  "APIs, and screenshots reflect current state.",
    ),
    DocStandard(
        gate=DocQualityGate.SEARCHABLE,
        name="Searchable",
        description=(
            "All documentation must be indexed and discoverable through "
            "the organization's documentation platform. Documents must "
            "have meaningful titles, descriptions, and tags."
        ),
        weight=0.9,
        fix_guide="Add document to the documentation index. Include meta "
                  "description, keywords, and relevant tags.",
    ),
    DocStandard(
        gate=DocQualityGate.VERSIONED,
        name="Versioned",
        description=(
            "Documentation must be versioned alongside the code it describes. "
            "Each version of the software should have its corresponding "
            "documentation version available."
        ),
        weight=0.8,
        fix_guide="Ensure documentation is in the same repo as the code. "
                  "Tag documentation releases with version numbers.",
    ),
    DocStandard(
        gate=DocQualityGate.OWNED,
        name="Owned",
        description=(
            "Every documentation artifact must have a clear owner (individual "
            "or team) responsible for its accuracy and currency. Ownership "
            "is tracked in CODEOWNERS or OWNERS.md."
        ),
        weight=0.9,
        required_patterns=[r"OWNER[S]?\.md", r"CODEOWNERS"],
        fix_guide="Add an owner field or ensure the doc path is covered "
                  "in CODEOWNERS.",
    ),
    DocStandard(
        gate=DocQualityGate.TASK_ORIENTED,
        name="Task-Oriented",
        description=(
            "Documentation should be organized around tasks developers "
            "need to accomplish, not just feature descriptions. Each "
            "doc should answer 'How do I...?' questions."
        ),
        weight=0.7,
        required_patterns=[r"(?i)how[ -]to|getting[ -]started|guide|tutorial"],
        fix_guide="Restructure content around user tasks. Start each section "
                  "with a task-oriented heading (e.g., 'How to deploy').",
    ),
    DocStandard(
        gate=DocQualityGate.EXAMPLE_DRIVEN,
        name="Example-Driven",
        description=(
            "Documentation must include practical, copy-pasteable examples "
            "for key workflows. Examples must be tested and verified."
        ),
        weight=0.7,
        required_patterns=[r"```", r"# Example", r"(?i)example"],
        fix_guide="Add code examples for each key workflow. Ensure examples "
                  "are tested in CI.",
    ),
    DocStandard(
        gate=DocQualityGate.ACCESSIBLE,
        name="Accessible",
        description=(
            "Documentation must be accessible: readable by screen readers, "
            "proper heading hierarchy, alt text on images, sufficient "
            "color contrast, and keyboard-navigable."
        ),
        weight=0.6,
        fix_guide="Run accessibility checker on docs site. Add alt text. "
                  "Ensure proper heading nesting (H1 → H2 → H3).",
    ),
    DocStandard(
        gate=DocQualityGate.SOURCE_LINKED,
        name="Linked to Source",
        description=(
            "Documentation should link to relevant source code files, "
            "APIs, and configuration. Maintain bidirectional traceability "
            "between docs and code."
        ),
        weight=0.6,
        required_patterns=[r"github\.com|source|blob/|tree/"],
        fix_guide="Add links to source files referenced in documentation. "
                  "Use permalinks to specific commits/lines.",
    ),
    DocStandard(
        gate=DocQualityGate.IN_DEFINITION_OF_DONE,
        name="In Definition of Done",
        description=(
            "Documentation updates are part of the definition of done. "
            "No feature is complete without corresponding documentation. "
            "PR template includes a documentation checklist."
        ),
        weight=1.0,
        fix_guide="Update PR template to include documentation checklist. "
                  "Enforce in code review that docs are updated.",
    ),
]


@dataclass
class DocAssessment:
    """Result of assessing a document against a single standard."""
    standard: DocStandard
    passed: bool
    score: float  # 0.0 to 1.0
    details: str = ""
    last_checked: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate": self.standard.gate.value,
            "name": self.standard.name,
            "passed": self.passed,
            "score": round(self.score, 2),
            "details": self.details,
            "last_checked": self.last_checked.isoformat(),
        }


@dataclass
class DocReport:
    """Complete documentation quality report for a project or document."""
    doc_path: str
    doc_title: str
    owner: str
    last_updated: Optional[datetime]
    status: DocStatus
    assessments: List[DocAssessment]
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def overall_score(self) -> float:
        """Calculate weighted overall quality score (0-100)."""
        if not self.assessments:
            return 0.0
        total_weight = sum(a.standard.weight for a in self.assessments)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(a.score * a.standard.weight for a in self.assessments)
        return (weighted_sum / total_weight) * 100

    @property
    def passed_gates(self) -> int:
        return sum(1 for a in self.assessments if a.passed)

    @property
    def total_gates(self) -> int:
        return len(self.assessments)

    @property
    def grade(self) -> str:
        """Letter grade based on overall score."""
        score = self.overall_score
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    @property
    def is_stale(self) -> bool:
        """Check if documentation is stale based on SLA."""
        if not self.last_updated:
            return True
        for std in DOC_STANDARDS:
            if std.gate == DocQualityGate.CURRENT and std.sla_days:
                age = datetime.utcnow() - self.last_updated
                return age > timedelta(days=std.sla_days)
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_path": self.doc_path,
            "doc_title": self.doc_title,
            "status": self.status.value,
            "is_stale": self.is_stale,
            "overall_score": round(self.overall_score, 1),
            "grade": self.grade,
            "passed_gates": self.passed_gates,
            "total_gates": self.total_gates,
            "assessments": [a.to_dict() for a in self.assessments],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def get_doc_standards() -> List[DocStandard]:
    """Get all documentation quality standards."""
    return DOC_STANDARDS


def assess_doc_content(content: str, last_updated: Optional[datetime] = None) -> List[DocAssessment]:
    """Assess document content against all quality standards.

    This is a heuristic assessment based on content analysis.
    """
    assessments: List[DocAssessment] = []

    for standard in DOC_STANDARDS:
        passed = True
        score = 1.0
        details_parts: List[str] = []

        if standard.gate == DocQualityGate.CURRENT:
            if last_updated and standard.sla_days:
                age_days = (datetime.utcnow() - last_updated).days
                if age_days > standard.sla_days:
                    passed = False
                    score = max(0.0, 1.0 - (age_days - standard.sla_days) / 30)
                    details_parts.append(f"Last updated {age_days} days ago (SLA: {standard.sla_days})")
                else:
                    details_parts.append(f"Updated {age_days} days ago (within SLA)")

        elif standard.gate == DocQualityGate.SEARCHABLE:
            # Check for title, description-like content
            has_heading = bool(re.search(r"^#\s+", content, re.MULTILINE))
            has_description = len(content.strip()) > 100
            if not has_heading:
                passed = False
                score = 0.5
                details_parts.append("No top-level heading found")
            if not has_description:
                score -= 0.2
                details_parts.append("Content too short for meaningful search indexing")
            if passed:
                details_parts.append("Has heading and sufficient content for indexing")

        elif standard.gate == DocQualityGate.EXAMPLE_DRIVEN:
            # Check for code blocks or example markers
            has_code_blocks = "```" in content
            has_examples = bool(re.search(r"(?i)example|sample|usage", content))
            if not (has_code_blocks or has_examples):
                passed = False
                score = 0.3
                details_parts.append("No code blocks or examples found")
            elif has_code_blocks and has_examples:
                score = 1.0
                details_parts.append("Contains both code blocks and example markers")
            else:
                score = 0.7
                details_parts.append("Partial examples found")

        elif standard.gate == DocQualityGate.TASK_ORIENTED:
            task_patterns = [r"(?i)how[ -]to", r"(?i)getting[ -]started",
                           r"(?i)guide", r"(?i)tutorial", r"(?i)step[s]?\s*\d"]
            matches = sum(1 for p in task_patterns if re.search(p, content))
            if matches == 0:
                passed = False
                score = 0.3
                details_parts.append("No task-oriented patterns found")
            else:
                score = min(1.0, matches * 0.25)
                details_parts.append(f"{matches} task-oriented patterns found")

        elif standard.gate == DocQualityGate.SOURCE_LINKED:
            link_patterns = [r"github\.com", r"source", r"blob/", r"tree/",
                           r"\[source\]", r"\[code\]", r"http"]
            matches = sum(1 for p in link_patterns if re.search(p, content, re.IGNORECASE))
            if matches == 0:
                passed = False
                score = 0.3
                details_parts.append("No source links found")
            else:
                score = min(1.0, matches * 0.33)
                details_parts.append(f"{matches} source link patterns found")

        elif standard.gate == DocQualityGate.ACCESSIBLE:
            # Check heading hierarchy
            headings = re.findall(r"^(#{1,6})\s", content, re.MULTILINE)
            has_h1 = any(h == "#" for h in headings)
            if not has_h1:
                passed = False
                score = 0.5
                details_parts.append("Missing H1 heading")
            else:
                details_parts.append("Heading structure present")

        else:
            # VERSIONED, OWNED, IN_DEFINITION_OF_DONE are structural/process
            # checks that need repo-level context; mark as neutral
            details_parts.append("Requires structural/process validation")

        details = "; ".join(details_parts) if details_parts else "Compliant"
        assessments.append(DocAssessment(
            standard=standard,
            passed=passed,
            score=score,
            details=details,
        ))

    return assessments


def validate_documentation(
    doc_path: str,
    content: str,
    doc_title: str = "",
    owner: str = "",
    last_updated: Optional[datetime] = None,
) -> DocReport:
    """Validate a documentation artifact against all quality standards.

    This is the main entry point for documentation validation.
    """
    # Determine status based on age
    status = DocStatus.PUBLISHED
    if last_updated:
        for std in DOC_STANDARDS:
            if std.gate == DocQualityGate.CURRENT and std.sla_days:
                age = datetime.utcnow() - last_updated
                if age > timedelta(days=std.sla_days):
                    status = DocStatus.STALE
                break

    assessments = assess_doc_content(content, last_updated)

    return DocReport(
        doc_path=doc_path,
        doc_title=doc_title or doc_path,
        owner=owner,
        last_updated=last_updated,
        status=status,
        assessments=assessments,
    )


def assess_doc_quality(
    docs: Dict[str, Dict[str, Any]],
) -> List[DocReport]:
    """Assess quality of multiple documents.

    Args:
        docs: Dict mapping doc_path to {title, content, owner, last_updated}.

    Returns:
        List of DocReport, one per document.
    """
    reports = []
    for doc_path, doc_info in docs.items():
        report = validate_documentation(
            doc_path=doc_path,
            content=doc_info.get("content", ""),
            doc_title=doc_info.get("title", ""),
            owner=doc_info.get("owner", ""),
            last_updated=doc_info.get("last_updated"),
        )
        reports.append(report)
    return reports


def generate_doc_report(
    docs: Dict[str, Dict[str, Any]],
    output_format: str = "summary",
) -> str:
    """Generate a documentation quality report.

    Args:
        docs: Dict mapping doc_path to doc info.
        output_format: 'summary', 'json', or 'detailed'.

    Returns:
        Formatted report string.
    """
    reports = assess_doc_quality(docs)

    if output_format == "summary":
        if not reports:
            return "No documents to report."

        lines = ["Documentation Quality Report", "=" * 30, ""]
        avg_score = sum(r.overall_score for r in reports) / len(reports)
        stale_count = sum(1 for r in reports if r.is_stale)
        lines.append(f"Documents: {len(reports)}")
        lines.append(f"Average Score: {avg_score:.1f}/100")
        lines.append(f"Stale Documents: {stale_count}")
        lines.append("")
        for report in reports:
            flag = " [STALE]" if report.is_stale else ""
            lines.append(
                f"  [{report.grade}] {report.doc_title}{flag} "
                f"({report.overall_score:.0f}%)"
            )
        return "\n".join(lines)

    elif output_format == "json":
        return json.dumps([r.to_dict() for r in reports], indent=2)

    elif output_format == "detailed":
        parts = []
        for report in reports:
            parts.append(f"=== {report.doc_title} ===")
            parts.append(f"  Grade: {report.grade} ({report.overall_score:.0f}%)")
            parts.append(f"  Status: {report.status.value}")
            parts.append(f"  Stale: {'YES' if report.is_stale else 'NO'}")
            parts.append("  Gates:")
            for a in report.assessments:
                icon = "✓" if a.passed else "✗"
                parts.append(f"    {icon} {a.standard.name}: {a.details}")
            parts.append("")
        return "\n".join(parts)

    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def get_gate_by_name(name: str) -> Optional[DocQualityGate]:
    """Look up a quality gate by name."""
    try:
        return DocQualityGate(name.lower().replace(" ", "_"))
    except ValueError:
        return None


def get_gate_description(gate: DocQualityGate) -> str:
    """Get the description of a quality gate."""
    for std in DOC_STANDARDS:
        if std.gate == gate:
            return std.description
    return ""


def get_standards_summary() -> Dict[str, Any]:
    """Get a summary of all documentation standards."""
    return {
        "total_standards": len(DOC_STANDARDS),
        "standards": [
            {
                "gate": s.gate.value,
                "name": s.name,
                "weight": s.weight,
                "sla_days": s.sla_days,
            }
            for s in DOC_STANDARDS
        ],
    }