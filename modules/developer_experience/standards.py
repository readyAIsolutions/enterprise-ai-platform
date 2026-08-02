"""
Repository Standards
====================
Enterprise-grade repository standards enforcement. Defines required
artifacts and configurations every repository must maintain. Provides
validation, compliance checking, and reporting.

Required Standards:
    1.  README
    2.  Architecture Documentation
    3.  Setup Guide
    4.  Environment Configuration
    5.  Dependencies (pinned)
    6.  Testing Commands
    7.  Linting Configuration
    8.  Build Configuration
    9.  Deployment Guide
    10. Security Guidance
    11. Contribution Guide
    12. Ownership (CODEOWNERS)
    13. Changelog
    14. Troubleshooting Guide
    15. License
    16. Support Channel
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import json
import logging
import re

logger = logging.getLogger(__name__)


class StandardCategory(Enum):
    """Categories of repository standards."""
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    SECURITY = "security"
    OPERATIONS = "operations"
    GOVERNANCE = "governance"
    QUALITY = "quality"


class StandardSeverity(Enum):
    """Severity of non-compliance with a standard."""
    CRITICAL = "critical"   # Must fix immediately, blocks deployment
    HIGH = "high"           # Must fix before next release
    MEDIUM = "medium"       # Should fix within sprint
    LOW = "low"             # Nice to have
    INFO = "info"           # Informational only


@dataclass
class RepoStandard:
    """Definition of a single repository standard."""
    id: str
    name: str
    description: str
    category: StandardCategory
    severity: StandardSeverity
    required_file: Optional[str] = None        # File that must exist
    required_file_pattern: Optional[str] = None  # Regex pattern for file
    required_content_pattern: Optional[str] = None  # Content must match
    required_config_key: Optional[str] = None   # Key in config
    min_file_size_bytes: Optional[int] = None   # Minimum file size
    allowed_extensions: Optional[List[str]] = None
    auto_fix_hint: Optional[str] = None  # How to auto-fix
    rationale: str = ""


# --- Standard Definitions ---

REQUIRED_STANDARDS: List[RepoStandard] = [
    RepoStandard(
        id="STD-001",
        name="README",
        description="Top-level README.md with project overview, badges, and quick-start links.",
        category=StandardCategory.DOCUMENTATION,
        severity=StandardSeverity.CRITICAL,
        required_file="README.md",
        min_file_size_bytes=200,
        rationale="README is the entry point for all developers and must be present and substantive.",
        auto_fix_hint="Create README.md from template: /templates/README.md.tmpl",
    ),
    RepoStandard(
        id="STD-002",
        name="Architecture Documentation",
        description="docs/ARCHITECTURE.md containing system design, data flow, and key decisions.",
        category=StandardCategory.DOCUMENTATION,
        severity=StandardSeverity.HIGH,
        required_file_pattern=r"docs?\/ARCHITECTURE\.md",
        min_file_size_bytes=500,
        rationale="Architecture documentation ensures new team members can understand the system.",
        auto_fix_hint="Run: arch-doc-generator --output docs/ARCHITECTURE.md",
    ),
    RepoStandard(
        id="STD-003",
        name="Setup Guide",
        description="docs/SETUP.md with one-command environment setup instructions.",
        category=StandardCategory.DOCUMENTATION,
        severity=StandardSeverity.HIGH,
        required_file_pattern=r"docs?\/SETUP\.md",
        min_file_size_bytes=300,
        rationale="Rapid onboarding requires clear, tested setup instructions.",
        auto_fix_hint="Create docs/SETUP.md from template: /templates/SETUP.md.tmpl",
    ),
    RepoStandard(
        id="STD-004",
        name="Environment Configuration",
        description="Standard environment configuration (.env.example, config templates).",
        category=StandardCategory.CONFIGURATION,
        severity=StandardSeverity.CRITICAL,
        required_file=".env.example",
        rationale="Environment template prevents missing configuration errors.",
        auto_fix_hint="Run: extract-config-template --output .env.example",
    ),
    RepoStandard(
        id="STD-005",
        name="Dependencies (Pinned)",
        description="Dependencies with pinned/locked versions (package-lock.json, Pipfile.lock, etc.).",
        category=StandardCategory.CONFIGURATION,
        severity=StandardSeverity.CRITICAL,
        required_file_pattern=r"(package-lock\.json|yarn\.lock|Pipfile\.lock|poetry\.lock|Cargo\.lock|Gemfile\.lock|go\.sum)",
        rationale="Pinned dependencies ensure reproducible builds across environments.",
        auto_fix_hint="Run your package manager's lock command (npm install, pipenv lock, etc.)",
    ),
    RepoStandard(
        id="STD-006",
        name="Testing Commands",
        description="Documented commands for running tests (unit, integration, e2e).",
        category=StandardCategory.QUALITY,
        severity=StandardSeverity.HIGH,
        required_content_pattern=r"(npm test|pytest|go test|cargo test|rspec|jest|vitest)",
        required_file="README.md",
        rationale="Every developer must know how to run tests immediately.",
        auto_fix_hint="Add a '## Testing' section to README.md",
    ),
    RepoStandard(
        id="STD-007",
        name="Linting Configuration",
        description="Linting/formatting configuration files committed to repo.",
        category=StandardCategory.QUALITY,
        severity=StandardSeverity.HIGH,
        required_file_pattern=r"(\.eslintrc|\.prettierrc|pyproject\.toml|\.rubocop\.yml|\.golangci\.yml|\.clang-format)",
        rationale="Consistent code style enforced by tooling prevents style arguments in review.",
        auto_fix_hint="Run language-appropriate lint init command.",
    ),
    RepoStandard(
        id="STD-008",
        name="Build Configuration",
        description="Build configuration (Dockerfile, Makefile, build.gradle, CMakeLists.txt, etc.).",
        category=StandardCategory.OPERATIONS,
        severity=StandardSeverity.CRITICAL,
        required_file_pattern=r"(Dockerfile|Makefile|build\.gradle|CMakeLists\.txt|Taskfile\.yml|justfile)",
        rationale="Build must be reproducible with a single command.",
        auto_fix_hint="Add a Dockerfile or Makefile with build targets.",
    ),
    RepoStandard(
        id="STD-009",
        name="Deployment Guide",
        description="docs/DEPLOYMENT.md with deployment procedures and rollback instructions.",
        category=StandardCategory.OPERATIONS,
        severity=StandardSeverity.MEDIUM,
        required_file_pattern=r"docs?\/DEPLOY(?:MENT)?\.md",
        min_file_size_bytes=200,
        rationale="Clear deployment documentation reduces deployment errors.",
        auto_fix_hint="Create docs/DEPLOYMENT.md from template.",
    ),
    RepoStandard(
        id="STD-010",
        name="Security Guidance",
        description="SECURITY.md with vulnerability reporting process and security considerations.",
        category=StandardCategory.SECURITY,
        severity=StandardSeverity.HIGH,
        required_file="SECURITY.md",
        min_file_size_bytes=150,
        rationale="Security policy is required for responsible vulnerability disclosure.",
        auto_fix_hint="Create SECURITY.md with contact and disclosure process.",
    ),
    RepoStandard(
        id="STD-011",
        name="Contribution Guide",
        description="CONTRIBUTING.md with PR process, coding standards, and review expectations.",
        category=StandardCategory.GOVERNANCE,
        severity=StandardSeverity.HIGH,
        required_file="CONTRIBUTING.md",
        min_file_size_bytes=300,
        rationale="Clear contribution guidelines reduce onboarding friction for contributors.",
        auto_fix_hint="Create CONTRIBUTING.md from template.",
    ),
    RepoStandard(
        id="STD-012",
        name="Ownership (CODEOWNERS)",
        description="CODEOWNERS file defining ownership for all code paths.",
        category=StandardCategory.GOVERNANCE,
        severity=StandardSeverity.CRITICAL,
        required_file_pattern=r"(CODEOWNERS|\.github\/CODEOWNERS|OWNERS)",
        min_file_size_bytes=10,
        rationale="Clear code ownership ensures accountability and review routing.",
        auto_fix_hint="Create .github/CODEOWNERS with team ownership assignments.",
    ),
    RepoStandard(
        id="STD-013",
        name="Changelog",
        description="CHANGELOG.md tracking all notable changes following semantic versioning.",
        category=StandardCategory.DOCUMENTATION,
        severity=StandardSeverity.MEDIUM,
        required_file="CHANGELOG.md",
        min_file_size_bytes=100,
        rationale="Changelog communicates changes to consumers and maintainers.",
        auto_fix_hint="Create CHANGELOG.md and update on each release.",
    ),
    RepoStandard(
        id="STD-014",
        name="Troubleshooting Guide",
        description="docs/TROUBLESHOOTING.md with common issues and solutions.",
        category=StandardCategory.DOCUMENTATION,
        severity=StandardSeverity.MEDIUM,
        required_file_pattern=r"docs?\/TROUBLESHOOTING\.md",
        min_file_size_bytes=100,
        rationale="Troubleshooting guide reduces support burden and developer frustration.",
        auto_fix_hint="Create docs/TROUBLESHOOTING.md with common issues.",
    ),
    RepoStandard(
        id="STD-015",
        name="License",
        description="LICENSE file with approved open-source or proprietary license.",
        category=StandardCategory.GOVERNANCE,
        severity=StandardSeverity.CRITICAL,
        required_file="LICENSE",
        min_file_size_bytes=50,
        rationale="Every repository must have a clear license.",
        auto_fix_hint="Copy approved license from /licenses/ directory.",
    ),
    RepoStandard(
        id="STD-016",
        name="Support Channel",
        description="Documented support channel (Slack, Teams, email) in README.",
        category=StandardCategory.OPERATIONS,
        severity=StandardSeverity.LOW,
        required_content_pattern=r"(#[a-z0-9_-]+|@[a-zA-Z]+|support@|help@)",
        required_file="README.md",
        rationale="Clear support channel reduces resolution time for questions.",
        auto_fix_hint="Add support channel info to README.",
    ),
]


@dataclass
class ComplianceResult:
    """Result of checking a single standard."""
    standard: RepoStandard
    compliant: bool
    details: str = ""
    missing_files: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "standard_id": self.standard.id,
            "standard_name": self.standard.name,
            "category": self.standard.category.value,
            "severity": self.standard.severity.value,
            "compliant": self.compliant,
            "details": self.details,
            "missing_files": self.missing_files,
            "suggestions": self.suggestions,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class ComplianceReport:
    """Full compliance report for a repository."""
    repo_name: str
    repo_path: str
    results: List[ComplianceResult]
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_standards(self) -> int:
        return len(self.results)

    @property
    def compliant_count(self) -> int:
        return sum(1 for r in self.results if r.compliant)

    @property
    def non_compliant_count(self) -> int:
        return self.total_standards - self.compliant_count

    @property
    def compliance_percentage(self) -> float:
        if self.total_standards == 0:
            return 100.0
        return (self.compliant_count / self.total_standards) * 100

    @property
    def critical_failures(self) -> List[ComplianceResult]:
        return [
            r for r in self.results
            if not r.compliant and r.standard.severity == StandardSeverity.CRITICAL
        ]

    @property
    def is_deployable(self) -> bool:
        """A repo is deployable if it has no critical failures."""
        return len(self.critical_failures) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_name": self.repo_name,
            "repo_path": self.repo_path,
            "generated_at": self.generated_at.isoformat(),
            "total_standards": self.total_standards,
            "compliant_count": self.compliant_count,
            "non_compliant_count": self.non_compliant_count,
            "compliance_percentage": round(self.compliance_percentage, 1),
            "is_deployable": self.is_deployable,
            "critical_failures": len(self.critical_failures),
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def summary(self) -> str:
        """Generate a human-readable summary."""
        lines = [
            f"Compliance Report: {self.repo_name}",
            f"  Path: {self.repo_path}",
            f"  Compliance: {self.compliance_percentage:.1f}% ({self.compliant_count}/{self.total_standards})",
            f"  Deployable: {'YES' if self.is_deployable else 'NO'}",
        ]
        if self.critical_failures:
            lines.append(f"  Critical Failures ({len(self.critical_failures)}):")
            for f in self.critical_failures:
                lines.append(f"    - {f.standard.name}: {f.details}")
        return "\n".join(lines)


def get_required_standards(
    categories: Optional[List[StandardCategory]] = None,
    severities: Optional[List[StandardSeverity]] = None,
) -> List[RepoStandard]:
    """Get required standards, optionally filtered by category and/or severity."""
    standards = REQUIRED_STANDARDS
    if categories:
        standards = [s for s in standards if s.category in categories]
    if severities:
        standards = [s for s in standards if s.severity in severities]
    return standards


def check_standard_compliance(
    repo_path: str,
    repo_files: List[str],
    file_contents: Optional[Dict[str, str]] = None,
) -> List[ComplianceResult]:
    """Check all required standards against a repository's files.

    Args:
        repo_path: Path to the repository root.
        repo_files: List of file paths relative to repo root.
        file_contents: Optional dict mapping file path to content for
                       content-based checks.

    Returns:
        List of ComplianceResult objects, one per standard.
    """
    if file_contents is None:
        file_contents = {}

    results: List[ComplianceResult] = []

    for standard in REQUIRED_STANDARDS:
        compliant = True
        details_parts: List[str] = []
        missing_files: List[str] = []
        suggestions: List[str] = []

        # Check required file existence
        if standard.required_file:
            found = standard.required_file in repo_files
            # Also check subdirectories
            if not found:
                found = any(
                    f == standard.required_file or f.endswith(f"/{standard.required_file}")
                    for f in repo_files
                )
            if not found:
                compliant = False
                missing_files.append(standard.required_file)
                details_parts.append(f"Missing required file: {standard.required_file}")

        # Check file pattern
        if standard.required_file_pattern:
            pattern = re.compile(standard.required_file_pattern)
            matches = [f for f in repo_files if pattern.search(f)]
            if not matches:
                compliant = False
                details_parts.append(
                    f"No file matching pattern: {standard.required_file_pattern}"
                )
                missing_files.append(f"*{standard.required_file_pattern}*")
            elif standard.min_file_size_bytes:
                matching_files = matches

        # Check content pattern
        if standard.required_content_pattern and standard.required_file:
            target_file = standard.required_file
            content = file_contents.get(target_file, "")
            if content:
                pattern = re.compile(
                    standard.required_content_pattern, re.IGNORECASE | re.MULTILINE
                )
                if not pattern.search(content):
                    compliant = False
                    details_parts.append(
                        f"Content pattern not found in {target_file}: "
                        f"{standard.required_content_pattern}"
                    )
            else:
                compliant = False
                details_parts.append(f"Cannot check content: {target_file} not provided")

        # Build suggestions
        if not compliant and standard.auto_fix_hint:
            suggestions.append(standard.auto_fix_hint)

        detail = "; ".join(details_parts) if details_parts else "Compliant"
        results.append(ComplianceResult(
            standard=standard,
            compliant=compliant,
            details=detail,
            missing_files=missing_files,
            suggestions=suggestions,
        ))

    return results


def validate_repo_standards(
    repo_name: str,
    repo_path: str,
    repo_files: List[str],
    file_contents: Optional[Dict[str, str]] = None,
) -> ComplianceReport:
    """Validate a repository against all required standards.

    This is the main entry point for standards validation.
    """
    results = check_standard_compliance(repo_path, repo_files, file_contents)
    return ComplianceReport(
        repo_name=repo_name,
        repo_path=repo_path,
        results=results,
    )


def generate_standard_report(
    repo_name: str,
    repo_path: str,
    repo_files: List[str],
    file_contents: Optional[Dict[str, str]] = None,
    output_format: str = "json",
) -> str:
    """Generate a compliance report in the specified format.

    Args:
        repo_name: Repository name.
        repo_path: Repository path.
        repo_files: List of files in the repo.
        file_contents: Optional file contents for deep checks.
        output_format: 'json', 'dict', or 'summary'.

    Returns:
        Report in the requested format.
    """
    report = validate_repo_standards(repo_name, repo_path, repo_files, file_contents)

    if output_format == "json":
        return report.to_json()
    elif output_format == "dict":
        return json.dumps(report.to_dict())
    elif output_format == "summary":
        return report.summary()
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def get_standards_by_category() -> Dict[StandardCategory, List[RepoStandard]]:
    """Group all standards by their category."""
    grouped: Dict[StandardCategory, List[RepoStandard]] = {}
    for standard in REQUIRED_STANDARDS:
        grouped.setdefault(standard.category, []).append(standard)
    return grouped


def get_standards_by_severity() -> Dict[StandardSeverity, List[RepoStandard]]:
    """Group all standards by their severity level."""
    grouped: Dict[StandardSeverity, List[RepoStandard]] = {}
    for standard in REQUIRED_STANDARDS:
        grouped.setdefault(standard.severity, []).append(standard)
    return grouped


def get_standard_by_id(standard_id: str) -> Optional[RepoStandard]:
    """Look up a standard by its ID."""
    for standard in REQUIRED_STANDARDS:
        if standard.id == standard_id:
            return standard
    return None