"""
Tests for ModuleValidator
=========================
"""

import unittest

from enterprise.foundation.module_registry.registry import (
    ActivationCondition,
    ModuleMeta,
    ModulePermission,
    ModuleRegistry,
    ModuleState,
)
from enterprise.foundation.module_registry.validator import (
    ModuleValidator,
    Severity,
    ValidationIssue,
    ValidationReport,
)


class TestValidationIssue(unittest.TestCase):
    """Tests for the ValidationIssue dataclass."""

    def test_create_error_issue(self) -> None:
        issue = ValidationIssue(
            module_id="mod_a",
            severity=Severity.ERROR,
            code="missing_field",
            message="Missing required field",
            detail="module_id",
        )
        self.assertEqual(issue.module_id, "mod_a")
        self.assertEqual(issue.severity, Severity.ERROR)
        self.assertEqual(issue.code, "missing_field")
        self.assertEqual(issue.detail, "module_id")

    def test_create_warning_issue(self) -> None:
        issue = ValidationIssue(
            module_id="mod_b",
            severity=Severity.WARNING,
            code="permission_escalation",
            message="Permission level too high",
        )
        self.assertEqual(issue.severity, Severity.WARNING)


class TestValidationReport(unittest.TestCase):
    """Tests for the ValidationReport dataclass."""

    def _make_issues(self) -> list[ValidationIssue]:
        return [
            ValidationIssue("m1", Severity.ERROR, "e1", "err"),
            ValidationIssue("m1", Severity.WARNING, "w1", "warn"),
            ValidationIssue("m2", Severity.ERROR, "e2", "err2"),
            ValidationIssue("m2", Severity.INFO, "i1", "info"),
        ]

    def test_passed_when_no_errors(self) -> None:
        report = ValidationReport(
            module_ids=["m"], passed=True,
            issues=[ValidationIssue("m", Severity.WARNING, "w", "warn")]
        )
        self.assertTrue(report.passed)

    def test_not_passed_with_errors(self) -> None:
        report = ValidationReport(
            module_ids=["m"], passed=False,
            issues=[ValidationIssue("m", Severity.ERROR, "e", "err")]
        )
        self.assertFalse(report.passed)

    def test_filter_errors(self) -> None:
        issues = self._make_issues()
        report = ValidationReport(module_ids=["m1", "m2"], passed=False, issues=issues)
        self.assertEqual(len(report.errors), 2)
        self.assertTrue(all(i.severity == Severity.ERROR for i in report.errors))

    def test_filter_warnings(self) -> None:
        issues = self._make_issues()
        report = ValidationReport(module_ids=["m1", "m2"], passed=False, issues=issues)
        self.assertEqual(len(report.warnings), 1)

    def test_filter_infos(self) -> None:
        issues = self._make_issues()
        report = ValidationReport(module_ids=["m1", "m2"], passed=False, issues=issues)
        self.assertEqual(len(report.infos), 1)

    def test_issues_for(self) -> None:
        issues = self._make_issues()
        report = ValidationReport(module_ids=["m1", "m2"], passed=False, issues=issues)
        self.assertEqual(len(report.issues_for("m1")), 2)
        self.assertEqual(len(report.issues_for("m2")), 2)
        self.assertEqual(len(report.issues_for("m3")), 0)


class TestModuleValidatorRequiredFields(unittest.TestCase):
    """Tests for required/recommended field validation."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.validator = ModuleValidator(self.registry)

    def test_missing_module_id_fails(self) -> None:
        # Registration requires module_id, so test via direct check
        self.registry.register(ModuleMeta(module_id="bare", version=""))
        report = self.validator.validate("bare")
        self.assertFalse(report.passed)
        self.assertTrue(any("version" in i.code or "Version" in i.message for i in report.errors))

    def test_valid_module_passes(self) -> None:
        self.registry.register(ModuleMeta(
            module_id="good",
            version="1.0.0",
            display_name="Good Module",
            description="Does good things",
            author="Tester",
        ))
        report = self.validator.validate("good")
        self.assertTrue(report.passed)

    def test_missing_recommended_fields_warns(self) -> None:
        self.registry.register(ModuleMeta(module_id="minimal", version="1.0.0"))
        report = self.validator.validate("minimal")
        # Should still pass (no errors) but have warnings
        self.assertTrue(report.passed)
        self.assertGreater(len(report.warnings), 0)

    def test_invalid_version_format(self) -> None:
        self.registry.register(ModuleMeta(module_id="badver", version="one.two"))
        report = self.validator.validate("badver")
        self.assertFalse(report.passed)
        self.assertTrue(any("invalid_version" == i.code for i in report.errors))


class TestModuleValidatorDependencies(unittest.TestCase):
    """Tests for dependency satisfaction validation."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.validator = ModuleValidator(self.registry)

    def test_missing_dependency_error(self) -> None:
        self.registry.register(ModuleMeta(
            module_id="orphan",
            version="1.0.0",
            dependencies=frozenset({"nonexistent"}),
        ))
        report = self.validator.validate("orphan")
        self.assertFalse(report.passed)
        self.assertTrue(any("missing_dependency" == i.code for i in report.errors))

    def test_disabled_dependency_warns(self) -> None:
        self.registry.register(ModuleMeta(module_id="base", version="1.0.0"))
        # base starts REGISTERED and we don't enable it, but it's not DISABLED either
        # Let's disable it explicitly
        base = self.registry.get("base")
        base.state = ModuleState.DISABLED
        self.registry._modules["base"] = base

        self.registry.register(ModuleMeta(
            module_id="consumer",
            version="1.0.0",
            dependencies=frozenset({"base"}),
        ))
        report = self.validator.validate("consumer")
        # Should have warning about disabled dep, still passes
        self.assertTrue(report.passed)
        self.assertTrue(any("disabled_dependency" == i.code for i in report.warnings))

    def test_errored_dependency_error(self) -> None:
        self.registry.register(ModuleMeta(module_id="broken", version="1.0.0"))
        broken = self.registry.get("broken")
        broken.state = ModuleState.ERROR
        self.registry._modules["broken"] = broken

        self.registry.register(ModuleMeta(
            module_id="user",
            version="1.0.0",
            dependencies=frozenset({"broken"}),
        ))
        report = self.validator.validate("user")
        self.assertFalse(report.passed)
        self.assertTrue(any("errored_dependency" == i.code for i in report.errors))

    def test_satisfied_dependency_passes(self) -> None:
        self.registry.register(ModuleMeta(module_id="ok_dep", version="1.0.0"))
        self.registry.enable("ok_dep")
        self.registry.register(ModuleMeta(
            module_id="consumer_ok",
            version="1.0.0",
            dependencies=frozenset({"ok_dep"}),
        ))
        report = self.validator.validate("consumer_ok")
        self.assertTrue(report.passed)

    def test_version_constraint_failure(self) -> None:
        self.registry.register(ModuleMeta(module_id="old_lib", version="0.5.0"))
        self.registry.register(ModuleMeta(
            module_id="needs_new",
            version="1.0.0",
            dependencies=frozenset({"old_lib"}),
            metadata={"dep_version_min": {"old_lib": "1.0.0"}},
        ))
        report = self.validator.validate("needs_new")
        self.assertFalse(report.passed)
        self.assertTrue(any("version_constraint_failed" == i.code for i in report.errors))


class TestModuleValidatorCircularDeps(unittest.TestCase):
    """Tests for circular dependency detection."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.validator = ModuleValidator(self.registry)

    def test_no_circular_deps_passes(self) -> None:
        self.registry.register(ModuleMeta(module_id="a", version="1.0.0"))
        self.registry.register(ModuleMeta(module_id="b", version="1.0.0",
                                          dependencies=frozenset({"a"})))
        self.registry.register(ModuleMeta(module_id="c", version="1.0.0",
                                          dependencies=frozenset({"b"})))
        report = self.validator.validate_many(["a", "b", "c"])
        self.assertTrue(report.passed)

    def test_simple_cycle_detected(self) -> None:
        self.registry.register(ModuleMeta(module_id="x", version="1.0.0",
                                          dependencies=frozenset({"y"})))
        self.registry.register(ModuleMeta(module_id="y", version="1.0.0",
                                          dependencies=frozenset({"x"})))
        report = self.validator.validate_many(["x", "y"])
        self.assertFalse(report.passed)
        self.assertTrue(any("circular_dependency" == i.code for i in report.errors))

    def test_self_loop_detected(self) -> None:
        self.registry.register(ModuleMeta(module_id="loop", version="1.0.0",
                                          dependencies=frozenset({"loop"})))
        report = self.validator.validate("loop")
        self.assertFalse(report.passed)
        self.assertTrue(any("circular_dependency" == i.code for i in report.errors))

    def test_validate_many_unregistered(self) -> None:
        report = self.validator.validate_many(["ghost"])
        self.assertFalse(report.passed)
        self.assertTrue(any("not_registered" == i.code for i in report.errors))


class TestModuleValidatorPermissions(unittest.TestCase):
    """Tests for permission validation."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.validator = ModuleValidator(self.registry)

    def test_valid_permissions_pass(self) -> None:
        perm = ModulePermission(name="read:data", level=3)
        self.registry.register(ModuleMeta(
            module_id="safe",
            version="1.0.0",
            permissions=frozenset({perm}),
            required_permissions=frozenset({"read:data"}),
        ))
        report = self.validator.validate("safe")
        self.assertTrue(report.passed)

    def test_invalid_required_permission_error(self) -> None:
        # The dataclass __post_init__ catches this, so we must bypass it
        # to test the validator's own check. Use a valid Meta then mutate.
        perm = ModulePermission(name="read:data", level=3)
        meta = ModuleMeta(
            module_id="bad_req",
            version="1.0.0",
            permissions=frozenset({perm}),
            required_permissions=frozenset({"read:data"}),
        )
        # Bypass dataclass validation by directly injecting the bad state
        meta.required_permissions = frozenset({"write:data"})
        self.registry._modules["bad_req"] = meta
        report = self.validator.validate("bad_req")
        self.assertFalse(report.passed)
        self.assertTrue(any("invalid_required_permission" == i.code for i in report.errors))

    def test_permission_name_format_info(self) -> None:
        perm = ModulePermission(name="raw_permission_without_colon", level=1)
        self.registry.register(ModuleMeta(
            module_id="fmt_test",
            version="1.0.0",
            permissions=frozenset({perm}),
        ))
        report = self.validator.validate("fmt_test")
        # INFO severity, should still pass
        self.assertTrue(report.passed)
        self.assertGreater(len(report.infos), 0)

    def test_permission_escalation_warning(self) -> None:
        low_perm = ModulePermission(name="low", level=1)
        high_perm = ModulePermission(name="high", level=9)
        self.registry.register(ModuleMeta(
            module_id="base_mod", version="1.0.0",
            permissions=frozenset({low_perm}),
        ))
        self.registry.register(ModuleMeta(
            module_id="escalated", version="1.0.0",
            permissions=frozenset({high_perm}),
            dependencies=frozenset({"base_mod"}),
        ))
        report = self.validator.validate_many(["base_mod", "escalated"])
        # Should still pass but have permission escalation warning
        self.assertTrue(report.passed)
        self.assertTrue(any("permission_escalation" == i.code for i in report.warnings))


class TestModuleValidatorActivationConditions(unittest.TestCase):
    """Tests for activation condition validation."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.validator = ModuleValidator(self.registry)

    def test_conditional_with_callable_passes(self) -> None:
        self.registry.register(ModuleMeta(
            module_id="cond_ok", version="1.0.0",
            activation_condition=ActivationCondition.CONDITIONAL,
            activation_callable=lambda: True,
        ))
        report = self.validator.validate("cond_ok")
        self.assertTrue(report.passed)

    def test_conditional_without_callable_errors(self) -> None:
        # This should already fail at dataclass level, but test the code path
        # We'll register a module that somehow slipped through
        m = ModuleMeta(
            module_id="cond_bad", version="1.0.0",
            activation_condition=ActivationCondition.ALWAYS,
        )
        # Manually change the condition (bypassing dataclass validation)
        m.activation_condition = ActivationCondition.CONDITIONAL
        m.activation_callable = None
        self.registry._modules["cond_bad"] = m

        report = self.validator.validate("cond_bad")
        self.assertFalse(report.passed)
        self.assertTrue(any("missing_activation_callable" == i.code for i in report.errors))

    def test_dependencies_ready_without_deps_warns(self) -> None:
        self.registry.register(ModuleMeta(
            module_id="no_deps", version="1.0.0",
            activation_condition=ActivationCondition.DEPENDENCIES_READY,
        ))
        report = self.validator.validate("no_deps")
        self.assertTrue(report.passed)
        self.assertTrue(any("unnecessary_dep_ready" == i.code for i in report.warnings))

    def test_never_activate_info(self) -> None:
        self.registry.register(ModuleMeta(
            module_id="never_mod", version="1.0.0",
            activation_condition=ActivationCondition.NEVER,
        ))
        report = self.validator.validate("never_mod")
        self.assertTrue(report.passed)
        self.assertTrue(any("never_activate" == i.code for i in report.infos))


class TestModuleValidatorValidateAll(unittest.TestCase):
    """Tests for validate_all()."""

    def setUp(self) -> None:
        self.registry = ModuleRegistry()
        self.validator = ModuleValidator(self.registry)

    def test_validate_all_empty(self) -> None:
        report = self.validator.validate_all()
        self.assertTrue(report.passed)
        self.assertEqual(len(report.module_ids), 0)

    def test_validate_all_with_modules(self) -> None:
        self.registry.register(ModuleMeta(
            module_id="m1", version="1.0.0",
            display_name="One", description="First", author="A",
        ))
        self.registry.register(ModuleMeta(
            module_id="m2", version="2.0.0",
            display_name="Two", description="Second", author="B",
        ))
        report = self.validator.validate_all()
        self.assertTrue(report.passed)
        self.assertEqual(len(report.module_ids), 2)

    def test_validate_all_with_errors(self) -> None:
        self.registry.register(ModuleMeta(module_id="bad", version="abc"))
        report = self.validator.validate_all()
        self.assertFalse(report.passed)

    def test_quick_check(self) -> None:
        self.registry.register(ModuleMeta(module_id="ok", version="1.0.0"))
        self.assertTrue(self.validator.quick_check("ok"))

        self.registry.register(ModuleMeta(module_id="bad", version="invalid"))
        self.assertFalse(self.validator.quick_check("bad"))


if __name__ == "__main__":
    unittest.main()