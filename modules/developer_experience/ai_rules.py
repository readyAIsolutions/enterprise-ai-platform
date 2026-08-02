"""
AI Coding Agent Rules
=====================
Governance rules for AI coding agents (Copilot, Cursor, Codex, etc.)
operating within the organization's codebases. Ensures AI-assisted
code meets quality, security, and compliance standards.

AI Agent Rules:
    1.  Read project standards before contributing
    2.  Inspect architecture before making changes
    3.  Avoid unnecessary rewrites - prefer surgical changes
    4.  Preserve backward compatibility
    5.  Write tests for all changes
    6.  Run existing checks before declaring done
    7.  Document assumptions and design decisions
    8.  Never commit secrets or sensitive data
    9.  Respect code ownership boundaries
    10. Make changes reviewable (small, focused PRs)
    11. Explain migrations and breaking changes
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple
import json
import logging
import re

logger = logging.getLogger(__name__)


class AIRuleCategory(Enum):
    """Categories of AI coding rules."""
    PREREQUISITE = "prerequisite"     # Must check before starting
    QUALITY = "quality"               # Code quality rules
    SECURITY = "security"             # Security rules
    COLLABORATION = "collaboration"   # Team collaboration rules
    GOVERNANCE = "governance"         # Process and compliance rules


class AIRuleSeverity(Enum):
    """Severity of AI rule violations."""
    BLOCKING = "blocking"     # Blocks PR/merge entirely
    CRITICAL = "critical"     # Must fix before merge
    WARNING = "warning"       # Should fix, but won't block
    ADVISORY = "advisory"     # Best practice recommendation


@dataclass
class AIRule:
    """Definition of a single AI coding agent rule."""
    id: str
    name: str
    description: str
    category: AIRuleCategory
    severity: AIRuleSeverity
    rule_pattern: Optional[str] = None  # Regex to detect violation
    file_glob: Optional[str] = None     # Files this rule applies to
    check_fn_name: Optional[str] = None  # Name of check function
    rationale: str = ""
    examples_bad: List[str] = field(default_factory=list)
    examples_good: List[str] = field(default_factory=list)
    auto_fix_available: bool = False
    documentation_url: str = ""


# --- AI Rule Definitions ---

AI_RULES: List[AIRule] = [
    AIRule(
        id="AI-R01",
        name="Read Project Standards",
        description=(
            "Before writing any code, read and understand the project's "
            "CONTRIBUTING.md, ARCHITECTURE.md, and coding standards. "
            "Do not assume conventions - verify them."
        ),
        category=AIRuleCategory.PREREQUISITE,
        severity=AIRuleSeverity.BLOCKING,
        rationale=(
            "AI agents must understand project-specific conventions and "
            "standards to produce consistent, maintainable code."
        ),
        examples_bad=[
            "Generating code with different naming conventions than the project uses",
            "Using patterns the project explicitly avoids",
        ],
        examples_good=[
            "Checking CONTRIBUTING.md and matching existing code style",
            "Following project-specific directory structure conventions",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/read-standards",
    ),
    AIRule(
        id="AI-R02",
        name="Inspect Architecture",
        description=(
            "Before making changes, inspect the affected module's architecture: "
            "data flow, dependencies, interfaces, and patterns. Understand the "
            "system before changing it."
        ),
        category=AIRuleCategory.PREREQUISITE,
        severity=AIRuleSeverity.CRITICAL,
        rationale=(
            "Changes made without architectural awareness often introduce "
            "inconsistencies and technical debt."
        ),
        examples_bad=[
            "Adding a new dependency without checking existing dependency graph",
            "Introducing a new pattern when the module already has an established one",
        ],
        examples_good=[
            "Reading existing interfaces before adding a new one",
            "Following the established layering (controller → service → repository)",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/inspect-architecture",
    ),
    AIRule(
        id="AI-R03",
        name="Avoid Unnecessary Rewrites",
        description=(
            "Make surgical, minimal changes. Do not rewrite entire files "
            "or modules unless explicitly requested. Prefer targeted edits."
        ),
        category=AIRuleCategory.QUALITY,
        severity=AIRuleSeverity.CRITICAL,
        rationale=(
            "Unnecessary rewrites increase review burden, risk introducing "
            "bugs, and make git history harder to follow."
        ),
        examples_bad=[
            "Rewriting an entire 500-line file to 'improve' one function",
            "Refactoring unrelated code alongside a bug fix",
        ],
        examples_good=[
            "Making a focused 5-line change to fix a specific issue",
            "Refactoring only the code directly related to the change",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/avoid-rewrites",
    ),
    AIRule(
        id="AI-R04",
        name="Preserve Backward Compatibility",
        description=(
            "All changes must maintain backward compatibility unless a "
            "breaking change is explicitly planned and communicated. "
            "Use deprecation warnings before removal."
        ),
        category=AIRuleCategory.QUALITY,
        severity=AIRuleSeverity.BLOCKING,
        rationale=(
            "Breaking changes without coordination cause downstream "
            "failures and erode trust in the platform."
        ),
        check_fn_name="check_backward_compatibility",
        examples_bad=[
            "Removing a public API method without deprecation notice",
            "Changing a function signature without providing an adapter",
        ],
        examples_good=[
            "Adding @deprecated decorator with migration guide before removal",
            "Supporting both old and new parameter names during transition",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/backward-compat",
    ),
    AIRule(
        id="AI-R05",
        name="Write Tests",
        description=(
            "Every change must include appropriate tests: unit tests for "
            "logic changes, integration tests for API changes, and e2e "
            "tests for user-facing changes. Tests must pass before review."
        ),
        category=AIRuleCategory.QUALITY,
        severity=AIRuleSeverity.BLOCKING,
        rationale=(
            "Untested code is a liability. Tests serve as documentation "
            "and safety net for future changes."
        ),
        examples_bad=[
            "Submitting a PR with new functionality but no tests",
            "Writing a test that doesn't actually assert the behavior",
        ],
        examples_good=[
            "Adding unit tests covering happy path, edge cases, and error handling",
            "Adding integration test that verifies the API contract",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/write-tests",
    ),
    AIRule(
        id="AI-R06",
        name="Run Checks Before Done",
        description=(
            "Run all existing linting, formatting, type checking, and tests "
            "before marking work as complete. Fix any issues found."
        ),
        category=AIRuleCategory.QUALITY,
        severity=AIRuleSeverity.CRITICAL,
        rationale=(
            "CI failures waste reviewer time and create unnecessary "
            "back-and-forth in the review process."
        ),
        examples_bad=[
            "Submitting code that fails the linter",
            "Not running `make check` or equivalent before pushing",
        ],
        examples_good=[
            "Running `make lint test typecheck` before creating PR",
            "Fixing all warnings and errors before submitting for review",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/run-checks",
    ),
    AIRule(
        id="AI-R07",
        name="Document Assumptions",
        description=(
            "When making decisions with incomplete information, document "
            "the assumptions made. Add TODO comments with context for "
            "areas that need human review."
        ),
        category=AIRuleCategory.COLLABORATION,
        severity=AIRuleSeverity.WARNING,
        rationale=(
            "Documenting assumptions helps reviewers understand the "
            "reasoning and identify potential issues early."
        ),
        examples_bad=[
            "Implementing a complex algorithm without explaining the approach",
            "Changing a configuration default without noting the impact",
        ],
        examples_good=[
            "Adding a comment: '// Assumption: max batch size is 100 based on current usage'",
            "Adding: '// TODO(ai-review): Verify rate limit assumption with API team'",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/document-assumptions",
    ),
    AIRule(
        id="AI-R08",
        name="No Secrets in Code",
        description=(
            "Never include secrets, API keys, tokens, passwords, or "
            "credentials in generated code. Use environment variables "
            "or secrets management. Scan output before committing."
        ),
        category=AIRuleCategory.SECURITY,
        severity=AIRuleSeverity.BLOCKING,
        rule_pattern=(
            r"(?i)(api[_-]?key|secret|password|token|credential|private[_-]?key)"
            r'\s*[:=]\s*["\']?[a-zA-Z0-9_\-+/=]{20,}'
        ),
        rationale=(
            "Secrets in code are a critical security vulnerability. "
            "Even in AI-generated code, they must never appear."
        ),
        examples_bad=[
            "hardcoding `API_KEY = 'sk-abc123...'` in source code",
            "Including actual AWS credentials in a config example",
        ],
        examples_good=[
            "Using `API_KEY = os.environ.get('API_KEY')`",
            "Writing `AWS_ACCESS_KEY = vault.read('aws/creds')`",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/no-secrets",
    ),
    AIRule(
        id="AI-R09",
        name="Respect Code Ownership",
        description=(
            "Respect CODEOWNERS boundaries. Do not modify files owned by "
            "other teams without explicit permission. Changes to shared "
            "interfaces require coordination."
        ),
        category=AIRuleCategory.COLLABORATION,
        severity=AIRuleSeverity.CRITICAL,
        rationale=(
            "Cross-team changes without coordination cause conflicts "
            "and unexpected breaks."
        ),
        examples_bad=[
            "Modifying a shared library without notifying its owners",
            "Changing an API contract that other teams depend on",
        ],
        examples_good=[
            "Creating a PR that only touches files owned by the requesting team",
            "Opening a separate issue to coordinate cross-team changes",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/code-ownership",
    ),
    AIRule(
        id="AI-R10",
        name="Reviewable Changes",
        description=(
            "Keep changes small, focused, and reviewable. Each change should "
            "address one concern. Split large changes into logical, "
            "sequential PRs."
        ),
        category=AIRuleCategory.COLLABORATION,
        severity=AIRuleSeverity.WARNING,
        rationale=(
            "Large PRs are hard to review thoroughly. Small, focused "
            "changes get faster, better reviews."
        ),
        examples_bad=[
            "A single PR that changes 50 files across 5 different concerns",
            "Mixing refactoring with new features in the same PR",
        ],
        examples_good=[
            "PR #1: Extract interface, PR #2: Add new implementation, PR #3: Wire up",
            "Keeping changes under 400 lines where possible",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/reviewable-changes",
    ),
    AIRule(
        id="AI-R11",
        name="Explain Migrations",
        description=(
            "When changes require migrations (database, config, API), "
            "clearly explain the migration steps, rollback procedure, "
            "and impact. Include migration scripts."
        ),
        category=AIRuleCategory.GOVERNANCE,
        severity=AIRuleSeverity.CRITICAL,
        rationale=(
            "Undocumented migrations cause deployment failures and "
            "production incidents."
        ),
        examples_bad=[
            "Adding a database migration without documenting the rollback",
            "Changing a config format without migration script for existing data",
        ],
        examples_good=[
            "Including up/down migration scripts with clear documentation",
            "Adding a MIGRATION.md file with steps, impact, and rollback plan",
        ],
        documentation_url="https://docs.internal.company.com/ai-rules/explain-migrations",
    ),
]


# --- Compliance Checking ---

@dataclass
class AIRuleViolation:
    """A detected violation of an AI coding rule."""
    rule: AIRule
    file_path: str
    line_number: Optional[int]
    matched_content: Optional[str]
    severity: AIRuleSeverity
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule.id,
            "rule_name": self.rule.name,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "matched_content": self.matched_content,
            "suggestion": self.suggestion,
        }


@dataclass
class AIRulesReport:
    """Report of AI rule compliance for a change."""
    change_id: str
    files_changed: List[str]
    violations: List[AIRuleViolation]
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def has_blocking_violations(self) -> bool:
        return any(v.severity == AIRuleSeverity.BLOCKING for v in self.violations)

    @property
    def has_critical_violations(self) -> bool:
        return any(v.severity == AIRuleSeverity.CRITICAL for v in self.violations)

    @property
    def violation_count(self) -> int:
        return len(self.violations)

    @property
    def is_mergeable(self) -> bool:
        """Change is mergeable if no blocking or critical violations."""
        return not (self.has_blocking_violations or self.has_critical_violations)

    def summary(self) -> str:
        lines = [
            f"AI Rules Compliance Report: {self.change_id}",
            f"  Files Changed: {len(self.files_changed)}",
            f"  Violations: {self.violation_count}",
            f"  Mergeable: {'YES' if self.is_mergeable else 'NO'}",
        ]
        if self.violations:
            lines.append("  Violations:")
            for v in self.violations:
                lines.append(
                    f"    [{v.severity.value.upper()}] {v.rule.name}: "
                    f"{v.file_path}" +
                    (f":{v.line_number}" if v.line_number else "")
                )
        return "\n".join(lines)


def get_ai_rules(
    category: Optional[AIRuleCategory] = None,
    severity: Optional[AIRuleSeverity] = None,
) -> List[AIRule]:
    """Get AI coding rules, optionally filtered."""
    rules = AI_RULES
    if category:
        rules = [r for r in rules if r.category == category]
    if severity:
        rules = [r for r in rules if r.severity == severity]
    return rules


def check_secrets(content: str, file_path: str) -> List[AIRuleViolation]:
    """Scan code content for potential secrets."""
    violations: List[AIRuleViolation] = []
    secrets_rule = next((r for r in AI_RULES if r.id == "AI-R08"), None)
    if not secrets_rule or not secrets_rule.rule_pattern:
        return violations

    pattern = re.compile(secrets_rule.rule_pattern)
    for i, line in enumerate(content.split("\n"), 1):
        match = pattern.search(line)
        if match:
            violations.append(AIRuleViolation(
                rule=secrets_rule,
                file_path=file_path,
                line_number=i,
                matched_content=match.group(),
                severity=secrets_rule.severity,
                suggestion="Replace with environment variable or secrets manager reference.",
            ))

    return violations


def check_file_size(files: Dict[str, str], max_lines: int = 400) -> List[AIRuleViolation]:
    """Check if any changed file is too large for reviewability."""
    violations: List[AIRuleViolation] = []
    review_rule = next((r for r in AI_RULES if r.id == "AI-R10"), None)
    if not review_rule:
        return violations

    for file_path, content in files.items():
        line_count = len(content.split("\n"))
        if line_count > max_lines:
            violations.append(AIRuleViolation(
                rule=review_rule,
                file_path=file_path,
                line_number=None,
                matched_content=f"{line_count} lines (limit: {max_lines})",
                severity=review_rule.severity,
                suggestion=f"Consider splitting this file or breaking changes into smaller PRs.",
            ))

    return violations


def validate_ai_compliance(
    change_id: str,
    files_changed: List[str],
    file_contents: Optional[Dict[str, str]] = None,
) -> AIRulesReport:
    """Validate an AI-generated change against all AI rules.

    Args:
        change_id: Identifier for the change (e.g., PR number).
        files_changed: List of file paths in the change.
        file_contents: Optional dict mapping file path to content.

    Returns:
        AIRulesReport with all violations found.
    """
    violations: List[AIRuleViolation] = []
    file_contents = file_contents or {}

    # Check each file for secrets
    for file_path in files_changed:
        content = file_contents.get(file_path, "")
        if content:
            violations.extend(check_secrets(content, file_path))

    # Check file sizes
    if file_contents:
        violations.extend(check_file_size(file_contents))

    return AIRulesReport(
        change_id=change_id,
        files_changed=files_changed,
        violations=violations,
    )


def generate_ai_rules_report(
    change_id: str,
    files_changed: List[str],
    file_contents: Optional[Dict[str, str]] = None,
    output_format: str = "summary",
) -> str:
    """Generate an AI rules compliance report.

    Args:
        change_id: Change identifier.
        files_changed: List of changed file paths.
        file_contents: Optional file contents.
        output_format: 'summary', 'json', or 'dict'.

    Returns:
        Formatted report string.
    """
    report = validate_ai_compliance(change_id, files_changed, file_contents)

    if output_format == "summary":
        return report.summary()
    elif output_format == "json":
        return json.dumps({
            "change_id": report.change_id,
            "violations": [v.to_dict() for v in report.violations],
            "is_mergeable": report.is_mergeable,
        }, indent=2)
    elif output_format == "dict":
        return json.dumps({
            "change_id": report.change_id,
            "violations": [v.to_dict() for v in report.violations],
            "is_mergeable": report.is_mergeable,
        })
    else:
        raise ValueError(f"Unsupported output format: {output_format}")


def enforce_ai_rules(
    change_id: str,
    files_changed: List[str],
    file_contents: Optional[Dict[str, str]] = None,
    strict: bool = True,
) -> Tuple[bool, AIRulesReport]:
    """Enforce AI rules, optionally blocking on violations.

    Args:
        change_id: Change identifier.
        files_changed: List of changed file paths.
        file_contents: Optional file contents.
        strict: If True, raises an error on blocking/critical violations.

    Returns:
        Tuple of (passed, report).

    Raises:
        ValueError: If strict=True and blocking/critical violations found.
    """
    report = validate_ai_compliance(change_id, files_changed, file_contents)

    if strict and not report.is_mergeable:
        raise ValueError(
            f"AI rules enforcement failed for {change_id}: "
            f"{report.violation_count} violations found. "
            f"Blocking: {report.has_blocking_violations}, "
            f"Critical: {report.has_critical_violations}"
        )

    return report.is_mergeable, report


def get_rule_by_id(rule_id: str) -> Optional[AIRule]:
    """Look up an AI rule by ID."""
    for rule in AI_RULES:
        if rule.id == rule_id:
            return rule
    return None


def get_rules_by_category() -> Dict[AIRuleCategory, List[AIRule]]:
    """Group AI rules by category."""
    grouped: Dict[AIRuleCategory, List[AIRule]] = {}
    for rule in AI_RULES:
        grouped.setdefault(rule.category, []).append(rule)
    return grouped