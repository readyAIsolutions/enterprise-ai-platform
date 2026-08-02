"""
Module Validator
================

Validates module integrity before activation. Performs a suite of checks
covering required fields, dependency satisfaction, circular dependency
detection, and permission compatibility.

All validation functions are designed to be composable and return structured
results so callers can decide how to handle individual issues.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set

from .registry import (
    ActivationCondition,
    ModuleMeta,
    ModulePermission,
    ModuleRegistry,
    ModuleState,
)


class Severity(Enum):
    """Severity level for validation issues."""
    ERROR = "error"     # Hard failure — module must not activate
    WARNING = "warning"  # Soft advisory — may still proceed
    INFO = "info"       # Purely informational


@dataclass
class ValidationIssue:
    """A single issue found during module validation.

    Attributes:
        module_id: The module that produced this issue.
        severity: Error, warning, or info.
        code: Short machine-readable issue code (e.g. 'missing_field', 'circular_dep').
        message: Human-readable description of the issue.
        detail: Optional structured detail (e.g. the field name, the cycle path).
    """
    module_id: str
    severity: Severity
    code: str
    message: str
    detail: Optional[object] = None


@dataclass
class ValidationReport:
    """Aggregate result of validating one or more modules.

    Attributes:
        module_ids: Which modules were validated.
        passed: True if no issues at ERROR severity.
        issues: List of all issues, grouped by module.
    """
    module_ids: List[str]
    passed: bool
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        """Return only ERROR-severity issues."""
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        """Return only WARNING-severity issues."""
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def infos(self) -> List[ValidationIssue]:
        """Return only INFO-severity issues."""
        return [i for i in self.issues if i.severity == Severity.INFO]

    def issues_for(self, module_id: str) -> List[ValidationIssue]:
        """Return issues scoped to a single module.

        Args:
            module_id: The module to filter by.

        Returns:
            List of ValidationIssue for that module.
        """
        return [i for i in self.issues if i.module_id == module_id]


class ModuleValidator:
    """Validates module metadata and inter-module relationships.

    Performs a comprehensive set of checks before a module (or a group of
    modules) is allowed to activate. The validator is stateless — it operates
    on a :class:`ModuleRegistry` snapshot at call time.

    Example usage::

        validator = ModuleValidator(registry)
        report = validator.validate("auth")
        if report.passed:
            registry.activate("auth")
        else:
            for err in report.errors:
                print(f"  [ERROR] {err.message}")
    """

    # ------------------------------------------------------------------
    # Well-known required fields (name-in-module -> label)
    # ------------------------------------------------------------------
    REQUIRED_FIELDS: Dict[str, str] = {
        "module_id": "Module ID",
        "version": "Version",
    }

    RECOMMENDED_FIELDS: Dict[str, str] = {
        "display_name": "Display name",
        "description": "Description",
        "author": "Author",
    }

    def __init__(self, registry: ModuleRegistry) -> None:
        """Initialise the validator with a registry to validate against.

        Args:
            registry: The module registry that holds the modules to validate.
        """
        self.registry = registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def validate(self, module_id: str) -> ValidationReport:
        """Run all validation checks against a single module.

        Args:
            module_id: The module to validate.

        Returns:
            A :class:`ValidationReport` with all issues found.

        Raises:
            KeyError: If *module_id* is not registered.
        """
        return self.validate_many([module_id])

    def validate_many(self, module_ids: List[str]) -> ValidationReport:
        """Run all validation checks against multiple modules.

        Includes cross-module checks such as circular dependency detection
        and permission compatibility.

        Args:
            module_ids: The modules to validate.

        Returns:
            A :class:`ValidationReport` with all issues found across all modules.
        """
        issues: List[ValidationIssue] = []

        # Per-module checks
        seen: Set[str] = set()
        for mid in module_ids:
            if mid in seen:
                continue
            seen.add(mid)
            meta = self.registry.get(mid)
            if meta is None:
                issues.append(ValidationIssue(
                    module_id=mid,
                    severity=Severity.ERROR,
                    code="not_registered",
                    message=f"Module '{mid}' is not registered in the registry",
                ))
                continue
            issues.extend(self._check_required_fields(meta))
            issues.extend(self._check_recommended_fields(meta))
            issues.extend(self._check_dependency_satisfaction(meta))
            issues.extend(self._check_dependency_version_constraints(meta))
            issues.extend(self._check_permission_integrity(meta))
            issues.extend(self._check_activation_condition(meta))
            issues.extend(self._check_version_format(meta))

        # Cross-module checks
        issues.extend(self._check_circular_dependencies(module_ids))
        issues.extend(self._check_permission_compatibility(module_ids))

        has_errors = any(i.severity == Severity.ERROR for i in issues)
        return ValidationReport(
            module_ids=list(seen),
            passed=not has_errors,
            issues=issues,
        )

    def validate_all(self) -> ValidationReport:
        """Validate every module registered in the registry.

        Returns:
            A :class:`ValidationReport` covering all registered modules.
        """
        all_ids = [m.module_id for m in self.registry.list_all()]
        return self.validate_many(all_ids)

    def quick_check(self, module_id: str) -> bool:
        """Return True if the module passes all ERROR-level checks.

        A convenience wrapper around :meth:`validate` that only cares about
        hard failures.

        Args:
            module_id: The module to check.

        Returns:
            True if there are no ERROR-severity issues.
        """
        report = self.validate(module_id)
        return report.passed

    # ------------------------------------------------------------------
    # Field checks
    # ------------------------------------------------------------------

    def _check_required_fields(self, meta: ModuleMeta) -> List[ValidationIssue]:
        """Verify that all REQUIRED_FIELDS are non-empty.

        Args:
            meta: The module to inspect.

        Returns:
            List of issues (one per missing/empty required field).
        """
        issues: List[ValidationIssue] = []
        for field_name, label in self.REQUIRED_FIELDS.items():
            value = getattr(meta, field_name, None)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.ERROR,
                    code="missing_required_field",
                    message=f"Required field '{label}' ({field_name}) is missing or empty",
                    detail=field_name,
                ))
        return issues

    def _check_recommended_fields(self, meta: ModuleMeta) -> List[ValidationIssue]:
        """Warn about missing RECOMMENDED_FIELDS.

        Args:
            meta: The module to inspect.

        Returns:
            List of WARNING issues.
        """
        issues: List[ValidationIssue] = []
        for field_name, label in self.RECOMMENDED_FIELDS.items():
            value = getattr(meta, field_name, None)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.WARNING,
                    code="missing_recommended_field",
                    message=f"Recommended field '{label}' ({field_name}) is empty",
                    detail=field_name,
                ))
        return issues

    def _check_version_format(self, meta: ModuleMeta) -> List[ValidationIssue]:
        """Validate that the version string is a well-formed semver-like string.

        Args:
            meta: The module to check.

        Returns:
            List of issues.
        """
        issues: List[ValidationIssue] = []
        parts = meta.version.split(".")
        if len(parts) < 1:
            issues.append(ValidationIssue(
                module_id=meta.module_id,
                severity=Severity.ERROR,
                code="invalid_version",
                message=f"Version '{meta.version}' is not a valid dotted version string",
                detail=meta.version,
            ))
            return issues

        for part in parts:
            if not part.isdigit():
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.ERROR,
                    code="invalid_version",
                    message=f"Version '{meta.version}' contains non-numeric component '{part}'",
                    detail=meta.version,
                ))
                return issues
        return issues

    # ------------------------------------------------------------------
    # Dependency checks
    # ------------------------------------------------------------------

    def _check_dependency_satisfaction(self, meta: ModuleMeta) -> List[ValidationIssue]:
        """Verify that all declared dependencies are registered.

        Also checks that required dependency versions are satisfied.

        Args:
            meta: The module being validated.

        Returns:
            List of issues for missing or incompatible dependencies.
        """
        issues: List[ValidationIssue] = []
        for dep_id in meta.dependencies:
            dep = self.registry.get(dep_id)
            if dep is None:
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.ERROR,
                    code="missing_dependency",
                    message=f"Dependency '{dep_id}' is not registered in the registry",
                    detail=dep_id,
                ))
            elif dep.state == ModuleState.DISABLED:
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.WARNING,
                    code="disabled_dependency",
                    message=f"Dependency '{dep_id}' is currently DISABLED",
                    detail=dep_id,
                ))
            elif dep.state == ModuleState.ERROR:
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.ERROR,
                    code="errored_dependency",
                    message=f"Dependency '{dep_id}' is in ERROR state",
                    detail=dep_id,
                ))
        return issues

    def _check_dependency_version_constraints(
        self, meta: ModuleMeta
    ) -> List[ValidationIssue]:
        """Check version constraints from metadata (if any).

        Modules can declare minimum versions for dependencies in metadata
        under the key ``dep_version_min`` as a dict mapping dep_id -> version_str.

        Args:
            meta: The module to check.

        Returns:
            List of issues for unsatisfied version constraints.
        """
        issues: List[ValidationIssue] = []
        constraints: dict = meta.metadata.get("dep_version_min", {})
        if not isinstance(constraints, dict):
            return issues

        for dep_id, min_version in constraints.items():
            if dep_id not in meta.dependencies:
                continue
            dep = self.registry.get(dep_id)
            if dep is None:
                continue
            if not self.registry.check_version_satisfies(dep_id, str(min_version)):
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.ERROR,
                    code="version_constraint_failed",
                    message=(
                        f"Dependency '{dep_id}' version {dep.version} does not "
                        f"satisfy minimum {min_version}"
                    ),
                    detail={"dep": dep_id, "actual": dep.version, "required": min_version},
                ))
        return issues

    def _check_circular_dependencies(
        self, module_ids: List[str]
    ) -> List[ValidationIssue]:
        """Detect circular dependencies in the subgraph formed by *module_ids*.

        Uses the registry's own cycle detection but scoped to the requested
        modules.

        Args:
            module_ids: The IDs to include in the check.

        Returns:
            List of issues if cycles are found.
        """
        issues: List[ValidationIssue] = []
        # Only include registered modules in the dependency check
        registered_ids = [mid for mid in module_ids if self.registry.get(mid) is not None]
        if not registered_ids:
            return issues
        try:
            self.registry.resolve_activation_order(registered_ids)
        except ValueError as exc:
            # Extract cycle details if possible
            cycle = self.registry.find_cycle()
            cycle_modules = cycle if cycle else []
            issues.append(ValidationIssue(
                module_id=",".join(module_ids),
                severity=Severity.ERROR,
                code="circular_dependency",
                message=str(exc),
                detail=cycle_modules,
            ))
        return issues

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    def _check_permission_integrity(self, meta: ModuleMeta) -> List[ValidationIssue]:
        """Check a module's declared permissions for internal consistency.

        Verifies that:
        - Permission levels are in 0-10 range (enforced by dataclass already)
        - required_permissions are a subset of declared permissions
        - Permission names follow a reasonable format

        Args:
            meta: The module to check.

        Returns:
            List of issues.
        """
        issues: List[ValidationIssue] = []
        perm_names = frozenset(p.name for p in meta.permissions)

        # required_permissions subset check (belt-and-suspenders with dataclass)
        for rp in meta.required_permissions:
            if rp not in perm_names:
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.ERROR,
                    code="invalid_required_permission",
                    message=f"required_permission '{rp}' is not in declared permissions",
                    detail=rp,
                ))

        # Permission name format (recommend 'category:action')
        for p in meta.permissions:
            if ":" not in p.name and len(p.name.split()) < 3:
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.INFO,
                    code="permission_name_format",
                    message=f"Permission '{p.name}' does not follow 'category:action' convention",
                    detail=p.name,
                ))

        return issues

    def _check_permission_compatibility(
        self, module_ids: List[str]
    ) -> List[ValidationIssue]:
        """Check that modules don't have conflicting permission levels.

        A module declaring high-level permissions (e.g. level >= 8) when its
        dependencies only use low-level permissions may indicate a risky design.

        Args:
            module_ids: The modules to check.

        Returns:
            List of issues.
        """
        issues: List[ValidationIssue] = []

        for mid in module_ids:
            meta = self.registry.get(mid)
            if meta is None:
                continue

            max_level = max((p.level for p in meta.permissions), default=0)

            # Check that the module doesn't escalate beyond its dependencies
            for dep_id in meta.dependencies:
                dep = self.registry.get(dep_id)
                if dep is None:
                    continue
                dep_max = max((p.level for p in dep.permissions), default=0)
                if max_level > dep_max + 2:  # Arbitrary threshold
                    issues.append(ValidationIssue(
                        module_id=mid,
                        severity=Severity.WARNING,
                        code="permission_escalation",
                        message=(
                            f"Module '{mid}' has max permission level {max_level} "
                            f"but depends on '{dep_id}' with max level {dep_max}"
                        ),
                        detail={"module": mid, "dependency": dep_id, "levels": (max_level, dep_max)},
                    ))

        return issues

    # ------------------------------------------------------------------
    # Activation condition
    # ------------------------------------------------------------------

    def _check_activation_condition(self, meta: ModuleMeta) -> List[ValidationIssue]:
        """Validate the activation condition setup.

        Ensures CONDITIONAL has a callable, and that conditions make sense
        with the module's dependency list.

        Args:
            meta: The module to check.

        Returns:
            List of issues.
        """
        issues: List[ValidationIssue] = []

        if meta.activation_condition == ActivationCondition.CONDITIONAL:
            if meta.activation_callable is None:
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.ERROR,
                    code="missing_activation_callable",
                    message=(
                        f"Activation condition is CONDITIONAL but no "
                        f"activation_callable is set"
                    ),
                    detail=meta.module_id,
                ))
            elif not callable(meta.activation_callable):
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.ERROR,
                    code="non_callable_activation",
                    message="activation_callable is not callable",
                    detail=meta.module_id,
                ))

        if meta.activation_condition == ActivationCondition.DEPENDENCIES_READY:
            if not meta.dependencies:
                issues.append(ValidationIssue(
                    module_id=meta.module_id,
                    severity=Severity.WARNING,
                    code="unnecessary_dep_ready",
                    message=(
                        "Activation condition is DEPENDENCIES_READY but module "
                        "has no dependencies; consider using ALWAYS instead"
                    ),
                    detail=meta.module_id,
                ))

        if meta.activation_condition == ActivationCondition.NEVER:
            issues.append(ValidationIssue(
                module_id=meta.module_id,
                severity=Severity.INFO,
                code="never_activate",
                message="Module will never auto-activate; requires manual activation",
                detail=meta.module_id,
            ))

        return issues