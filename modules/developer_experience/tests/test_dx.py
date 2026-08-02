"""
Tests for the Developer Experience OS module.

Covers:
    - journey.py: Journey creation, stage advancement, blocking, progress
    - standards.py: Standard definitions, compliance checking, reporting
    - environment.py: Environment creation, validation, templates
    - golden_paths.py: Path retrieval, execution, prerequisite validation
    - platform.py: Capability listing, request creation, approvals
    - ai_rules.py: Rule definitions, compliance checking, enforcement
    - docs.py: Documentation validation, quality assessment, reporting
    - metrics.py: Metric collection, DORA calculation, dashboard
"""

import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from enterprise.modules.developer_experience.journey import (
    DeveloperJourney,
    JourneyStage,
    JourneyStageStatus,
    StageEntry,
    STAGE_ORDER,
    STAGE_DEPENDENCIES,
    STAGE_OWNERS,
    STAGE_DURATION_TARGETS,
    create_journey,
    get_journey,
    get_all_journeys,
    advance_stage,
    get_journey_summary,
    find_blocked_journeys,
)

from enterprise.modules.developer_experience.standards import (
    RepoStandard,
    StandardCategory,
    StandardSeverity,
    REQUIRED_STANDARDS,
    ComplianceResult,
    ComplianceReport,
    validate_repo_standards,
    get_required_standards,
    check_standard_compliance,
    generate_standard_report,
    get_standards_by_category,
    get_standards_by_severity,
    get_standard_by_id,
)

from enterprise.modules.developer_experience.environment import (
    DevEnvironment,
    EnvironmentProvider,
    EnvironmentStatus,
    DependencySpec,
    SecretSpec,
    MockService,
    ObservabilityTool,
    create_environment,
    validate_environment,
    get_environment_spec,
    list_supported_providers,
    get_environment_template,
    list_templates,
    generate_setup_script,
    check_environment_health,
    is_environment_reproducible,
    TEMPLATES,
)

from enterprise.modules.developer_experience.golden_paths import (
    GoldenPath,
    PathCategory,
    PathStatus,
    PathStep,
    PathPrerequisite,
    GOLDEN_PATHS,
    get_golden_path,
    list_golden_paths,
    execute_golden_path,
    validate_path_prerequisites,
    get_paths_by_category,
    search_paths,
    get_path_summary,
)

from enterprise.modules.developer_experience.platform import (
    IDPCapability,
    CapabilityStatus,
    CapabilityCategory,
    PlatformRequest,
    ServiceEntry,
    PLATFORM_CAPABILITIES,
    get_capability,
    list_capabilities,
    request_capability,
    self_service_action,
    get_service_catalog,
    register_service,
    deregister_service,
    get_request,
    get_user_requests,
    get_pending_approvals,
    approve_request,
    reject_request,
    get_platform_metrics,
)

from enterprise.modules.developer_experience.ai_rules import (
    AIRule,
    AIRuleCategory,
    AIRuleSeverity,
    AIRuleViolation,
    AIRulesReport,
    AI_RULES,
    get_ai_rules,
    validate_ai_compliance,
    generate_ai_rules_report,
    enforce_ai_rules,
    check_secrets,
    check_file_size,
    get_rule_by_id,
    get_rules_by_category,
)

from enterprise.modules.developer_experience.docs import (
    DocStandard,
    DocQualityGate,
    DocStatus,
    DocAssessment,
    DocReport,
    DOC_STANDARDS,
    validate_documentation,
    get_doc_standards,
    assess_doc_quality,
    generate_doc_report,
    assess_doc_content,
    get_gate_by_name,
    get_standards_summary,
)

from enterprise.modules.developer_experience.metrics import (
    DXMetric,
    MetricCategory,
    DORAMetrics,
    collect_metric,
    get_metrics_dashboard,
    calculate_dora_metrics,
    generate_metrics_report,
    start_timer,
    stop_timer,
    timed_metric,
    track_setup_time,
    track_build_duration,
    track_test_duration,
    track_deploy_frequency,
    track_deploy_success,
    track_pr_cycle_time,
    track_incident_recovery,
    track_developer_satisfaction,
    track_rework_rate,
    track_defect_escape_rate,
    track_documentation_success_rate,
    clear_metrics,
    get_metric_count,
)


# =============================================================================
# Journey Tests
# =============================================================================

class TestJourneyStage(unittest.TestCase):
    """Tests for StageEntry."""

    def test_stage_creation(self):
        stage = StageEntry(stage=JourneyStage.DEVELOPMENT)
        self.assertEqual(stage.stage, JourneyStage.DEVELOPMENT)
        self.assertEqual(stage.status, JourneyStageStatus.NOT_STARTED)
        self.assertIsNone(stage.started_at)

    def test_stage_start(self):
        stage = StageEntry(stage=JourneyStage.DEVELOPMENT)
        stage.start()
        self.assertEqual(stage.status, JourneyStageStatus.IN_PROGRESS)
        self.assertIsNotNone(stage.started_at)

    def test_stage_complete(self):
        stage = StageEntry(stage=JourneyStage.ACCESS_REQUEST)
        stage.start()
        stage.complete(notes="Done", artifacts=["access-request-123"])
        self.assertEqual(stage.status, JourneyStageStatus.COMPLETED)
        self.assertIsNotNone(stage.completed_at)
        self.assertEqual(stage.notes, "Done")
        self.assertIn("access-request-123", stage.artifacts)

    def test_stage_block(self):
        stage = StageEntry(stage=JourneyStage.ACCESS_REQUEST)
        stage.block("Waiting for manager approval")
        self.assertEqual(stage.status, JourneyStageStatus.BLOCKED)
        self.assertEqual(stage.blocked_reason, "Waiting for manager approval")

    def test_stage_skip(self):
        stage = StageEntry(stage=JourneyStage.OFFBOARDING)
        stage.skip("Contractor departure")
        self.assertEqual(stage.status, JourneyStageStatus.SKIPPED)

    def test_stage_duration(self):
        stage = StageEntry(stage=JourneyStage.ACCESS_REQUEST)
        stage.start()
        stage.complete()
        self.assertIsNotNone(stage.duration)
        self.assertLess(stage.duration.total_seconds(), 1)

    def test_stage_is_overdue(self):
        stage = StageEntry(stage=JourneyStage.ACCESS_REQUEST)
        stage.start()
        # ACCESS_REQUEST target is 4 hours - this stage should not be overdue
        self.assertFalse(stage.is_overdue)


class TestDeveloperJourney(unittest.TestCase):
    """Tests for DeveloperJourney."""

    def setUp(self):
        self.journey = DeveloperJourney(
            developer_id="dev-001",
            developer_name="Alice",
            team="platform",
            role="senior-engineer",
        )

    def test_journey_creation(self):
        self.assertEqual(self.journey.developer_id, "dev-001")
        self.assertEqual(len(self.journey.stages), len(STAGE_ORDER))
        # All stages should have NOT_STARTED status by default
        for stage in STAGE_ORDER:
            self.assertEqual(
                self.journey.stages[stage].status,
                JourneyStageStatus.NOT_STARTED,
            )

    def test_advance_requires_dependencies(self):
        # Cannot advance to DEVELOPMENT without ACCESS_REQUEST being complete
        with self.assertRaises(ValueError) as ctx:
            self.journey.advance(JourneyStage.DEVELOPMENT)
        self.assertIn("dependencies not met", str(ctx.exception))

    def test_advance_with_met_dependencies(self):
        # Complete dependencies first
        self.journey.stages[JourneyStage.ACCESS_REQUEST].complete()
        self.journey.stages[JourneyStage.ACCOUNT_SETUP].complete()
        self.journey.stages[JourneyStage.LOCAL_ENV_SETUP].complete()
        self.journey.stages[JourneyStage.REPO_DISCOVERY].complete()
        self.journey.stages[JourneyStage.PROJECT_UNDERSTANDING].complete()
        self.journey.stages[JourneyStage.DEPS_INSTALLATION].complete()

        # Now advance DEVELOPMENT
        entry = self.journey.advance(JourneyStage.DEVELOPMENT, notes="Starting feature work")
        self.assertEqual(entry.status, JourneyStageStatus.COMPLETED)
        self.assertEqual(entry.notes, "Starting feature work")

    def test_advance_to(self):
        entry = self.journey.advance_to(JourneyStage.ACCOUNT_SETUP)
        self.assertEqual(entry.status, JourneyStageStatus.IN_PROGRESS)
        # ACCESS_REQUEST should have been auto-completed
        self.assertEqual(
            self.journey.stages[JourneyStage.ACCESS_REQUEST].status,
            JourneyStageStatus.COMPLETED,
        )

    def test_progress_percentage(self):
        self.assertEqual(self.journey.progress_percentage, 0.0)
        # Complete one stage
        self.journey.stages[JourneyStage.ACCESS_REQUEST].complete()
        expected = (1 / len(STAGE_ORDER)) * 100
        self.assertAlmostEqual(self.journey.progress_percentage, expected)

    def test_current_stage(self):
        self.assertIsNone(self.journey.current_stage)
        self.journey.stages[JourneyStage.ACCESS_REQUEST].start()
        self.assertEqual(self.journey.current_stage, JourneyStage.ACCESS_REQUEST)

    def test_block_and_unblock(self):
        self.journey.block_stage(JourneyStage.ACCESS_REQUEST, "IT system down")
        entry = self.journey.stages[JourneyStage.ACCESS_REQUEST]
        self.assertEqual(entry.status, JourneyStageStatus.BLOCKED)

        self.journey.unblock_stage(JourneyStage.ACCESS_REQUEST)
        self.assertEqual(entry.status, JourneyStageStatus.IN_PROGRESS)

    def test_blocked_stages_property(self):
        self.journey.block_stage(JourneyStage.ACCESS_REQUEST, "reason1")
        self.journey.block_stage(JourneyStage.ACCOUNT_SETUP, "reason2")
        self.assertEqual(len(self.journey.blocked_stages), 2)

    def test_to_dict(self):
        d = self.journey.to_dict()
        self.assertEqual(d["developer_id"], "dev-001")
        self.assertEqual(d["team"], "platform")
        self.assertEqual(len(d["stages"]), len(STAGE_ORDER))

    def test_to_json(self):
        j = self.journey.to_json()
        data = json.loads(j)
        self.assertEqual(data["developer_name"], "Alice")

    def test_complete_journey(self):
        self.journey.complete_journey()
        self.assertEqual(self.journey.progress_percentage, 100.0)
        self.assertIsNotNone(self.journey.completed_at)
        for stage in STAGE_ORDER:
            self.assertEqual(
                self.journey.stages[stage].status,
                JourneyStageStatus.COMPLETED,
            )


class TestJourneyModuleFunctions(unittest.TestCase):
    """Tests for journey module-level functions."""

    def setUp(self):
        # Clear store between tests (access private for testing)
        import enterprise.modules.developer_experience.journey as journey_mod
        journey_mod._journey_store.clear()

    def test_create_and_get_journey(self):
        journey = create_journey("dev-002", "Bob", "backend", "engineer")
        self.assertIsNotNone(get_journey("dev-002"))
        # First stage should be auto-started
        self.assertEqual(
            journey.stages[JourneyStage.ACCESS_REQUEST].status,
            JourneyStageStatus.IN_PROGRESS,
        )

    def test_duplicate_journey_raises(self):
        create_journey("dev-003", "Charlie", "frontend", "engineer")
        with self.assertRaises(ValueError):
            create_journey("dev-003", "Charlie", "frontend", "engineer")

    def test_get_all_journeys(self):
        create_journey("dev-a", "A", "team-a", "role-a")
        create_journey("dev-b", "B", "team-b", "role-b")
        self.assertEqual(len(get_all_journeys()), 2)

    def test_get_journey_summary(self):
        create_journey("dev-004", "Diana", "ml", "ml-engineer")
        summary = get_journey_summary("dev-004")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["developer_name"], "Diana")

    def test_find_blocked_journeys(self):
        create_journey("dev-005", "Eve", "sre", "sre-engineer")
        # Block a stage
        journey = get_journey("dev-005")
        journey.block_stage(JourneyStage.ACCESS_REQUEST, "Waiting on IT")
        blocked = find_blocked_journeys()
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]["developer_name"], "Eve")

    def test_advance_stage_function(self):
        create_journey("dev-006", "Frank", "api", "api-engineer")
        # Complete first stage to enable advance
        journey = get_journey("dev-006")
        journey.stages[JourneyStage.ACCESS_REQUEST].complete()
        entry = advance_stage("dev-006", JourneyStage.ACCOUNT_SETUP, notes="Account created")
        self.assertEqual(entry.status, JourneyStageStatus.COMPLETED)


# =============================================================================
# Standards Tests
# =============================================================================

class TestRepoStandards(unittest.TestCase):
    """Tests for repository standards."""

    def test_all_standards_defined(self):
        self.assertEqual(len(REQUIRED_STANDARDS), 16)
        ids = [s.id for s in REQUIRED_STANDARDS]
        expected_ids = [f"STD-{i:03d}" for i in range(1, 17)]
        self.assertEqual(ids, expected_ids)

    def test_standard_categories(self):
        categories = set(s.category for s in REQUIRED_STANDARDS)
        self.assertIn(StandardCategory.DOCUMENTATION, categories)
        self.assertIn(StandardCategory.SECURITY, categories)

    def test_standard_severities(self):
        severities = set(s.severity for s in REQUIRED_STANDARDS)
        self.assertIn(StandardSeverity.CRITICAL, severities)
        self.assertIn(StandardSeverity.HIGH, severities)

    def test_get_required_standards(self):
        all_standards = get_required_standards()
        self.assertEqual(len(all_standards), 16)

    def test_get_required_standards_filtered(self):
        docs = get_required_standards(categories=[StandardCategory.DOCUMENTATION])
        self.assertGreater(len(docs), 0)
        for s in docs:
            self.assertEqual(s.category, StandardCategory.DOCUMENTATION)

    def test_get_standards_by_category(self):
        grouped = get_standards_by_category()
        self.assertIn(StandardCategory.DOCUMENTATION, grouped)
        self.assertGreater(len(grouped[StandardCategory.DOCUMENTATION]), 0)

    def test_get_standards_by_severity(self):
        grouped = get_standards_by_severity()
        self.assertIn(StandardSeverity.CRITICAL, grouped)
        self.assertGreater(len(grouped[StandardSeverity.CRITICAL]), 0)

    def test_get_standard_by_id(self):
        std = get_standard_by_id("STD-001")
        self.assertIsNotNone(std)
        self.assertEqual(std.name, "README")

        self.assertIsNone(get_standard_by_id("STD-999"))


class TestCompliance(unittest.TestCase):
    """Tests for compliance checking."""

    def test_empty_repo_fails_all(self):
        results = check_standard_compliance("/test", [])
        self.assertEqual(len(results), 16)
        for r in results:
            self.assertFalse(r.compliant)

    def test_minimal_repo(self):
        repo_files = [
            "README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md",
            "CHANGELOG.md", "Dockerfile", "package-lock.json",
            ".github/CODEOWNERS", ".env.example",
            "docs/ARCHITECTURE.md", "docs/SETUP.md",
            "docs/DEPLOYMENT.md", "docs/TROUBLESHOOTING.md",
            ".eslintrc.json",
        ]
        file_contents = {
            "README.md": "# My Project\n\n## Testing\n\nRun `npm test` to execute tests.\nSupport: #my-team-slack",
        }
        results = check_standard_compliance("/test", repo_files, file_contents)
        compliant_count = sum(1 for r in results if r.compliant)
        # Should have high compliance with all required files present
        self.assertGreater(compliant_count, 10)

    def test_validate_repo_standards(self):
        repo_files = ["README.md", "LICENSE", "Dockerfile", ".env.example"]
        report = validate_repo_standards("test-repo", "/test", repo_files)
        self.assertIsInstance(report, ComplianceReport)
        self.assertEqual(report.repo_name, "test-repo")
        self.assertEqual(report.total_standards, 16)

    def test_compliance_report_properties(self):
        repo_files = ["README.md"]
        report = validate_repo_standards("test", "/test", repo_files)
        self.assertEqual(report.total_standards, 16)
        self.assertLess(report.compliant_count, 16)
        self.assertGreater(report.non_compliant_count, 0)
        self.assertFalse(report.is_deployable)  # Missing critical files

    def test_compliance_report_json(self):
        repo_files = ["README.md"]
        report = validate_repo_standards("test", "/test", repo_files)
        data = report.to_dict()
        self.assertIn("compliance_percentage", data)
        self.assertIn("results", data)

    def test_generate_standard_report_summary(self):
        repo_files = ["README.md"]
        result = generate_standard_report("test", "/test", repo_files, output_format="summary")
        self.assertIn("Compliance Report", result)

    def test_generate_standard_report_json(self):
        repo_files = ["README.md"]
        result = generate_standard_report("test", "/test", repo_files, output_format="json")
        data = json.loads(result)
        self.assertIn("compliance_percentage", data)


# =============================================================================
# Environment Tests
# =============================================================================

class TestDevEnvironment(unittest.TestCase):
    """Tests for DevEnvironment."""

    def test_environment_creation(self):
        env = DevEnvironment(
            project_name="test-project",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
        )
        is_valid, issues = env.validate()
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)

    def test_environment_validation_fails(self):
        env = DevEnvironment(project_name="")
        is_valid, issues = env.validate()
        self.assertFalse(is_valid)
        self.assertIn("project_name is required", issues)

    def test_environment_validation_no_language(self):
        env = DevEnvironment(project_name="test")
        is_valid, issues = env.validate()
        self.assertFalse(is_valid)
        self.assertIn("language is required", issues)

    def test_environment_validation_no_setup_commands(self):
        env = DevEnvironment(
            project_name="test",
            language="python",
            language_version="3.12",
            package_manager="poetry",
        )
        is_valid, issues = env.validate()
        self.assertFalse(is_valid)
        self.assertTrue(any("setup_command" in i.lower() for i in issues))

    def test_unsafe_secret_defaults(self):
            env = DevEnvironment(
                project_name="test",
                language="python",
                language_version="3.12",
                package_manager="poetry",
                setup_commands=["poetry install"],
                secrets=[
                    SecretSpec(key="API_KEY", description="Key",
                              default_value="sk-live-abcdefghijklmnopqrstuvwxyz"),
                ],
            )
            is_valid, issues = env.validate()
            self.assertFalse(is_valid)
            self.assertTrue(any("real credential" in i for i in issues))

    def test_safe_secret_defaults(self):
        env = DevEnvironment(
            project_name="test",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
            secrets=[
                SecretSpec(key="API_KEY", description="Key",
                          default_value="dev-key-placeholder"),
            ],
        )
        is_valid, issues = env.validate()
        self.assertTrue(is_valid)

    def test_environment_to_dict(self):
        env = DevEnvironment(
            project_name="test",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
        )
        d = env.to_dict()
        self.assertEqual(d["project_name"], "test")
        self.assertEqual(d["language"], "python")

    def test_generate_setup_script(self):
        env = DevEnvironment(
            project_name="test",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install", "poetry run migrate"],
            health_check_command="poetry run pytest",
        )
        script = env.get_setup_script()
        self.assertIn("#!/usr/bin/env bash", script)
        self.assertIn("poetry install", script)
        self.assertIn("poetry run migrate", script)
        self.assertIn("poetry run pytest", script)


class TestEnvironmentTemplates(unittest.TestCase):
    """Tests for environment templates."""

    def test_templates_exist(self):
        self.assertIn("node-typescript", TEMPLATES)
        self.assertIn("python", TEMPLATES)
        self.assertIn("go", TEMPLATES)

    def test_list_templates(self):
        templates = list_templates()
        self.assertEqual(len(templates), 3)
        self.assertIn("python", templates)

    def test_get_template(self):
        template = get_environment_template("python")
        self.assertIsNotNone(template)
        self.assertEqual(template.language, "python")
        self.assertEqual(template.language_version, "3.12")

    def test_templates_are_valid(self):
        for name in ("node-typescript", "python", "go"):
            template = get_environment_template(name)
            is_valid, issues = template.validate()
            self.assertTrue(is_valid, f"Template {name} has issues: {issues}")

    def test_list_supported_providers(self):
        providers = list_supported_providers()
        self.assertGreater(len(providers), 0)
        provider_names = [p["provider"] for p in providers]
        self.assertIn("dev_container", provider_names)
        self.assertIn("local", provider_names)


class TestEnvironmentModuleFunctions(unittest.TestCase):
    """Tests for environment module-level functions."""

    def setUp(self):
        import enterprise.modules.developer_experience.environment as env_mod
        env_mod._environment_store.clear()

    def test_create_environment(self):
        env = DevEnvironment(
            project_name="my-service",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
        )
        result = create_environment(env)
        self.assertEqual(result.status, EnvironmentStatus.CREATING)
        self.assertIsNotNone(result.created_at)

    def test_get_environment_spec(self):
        env = DevEnvironment(
            project_name="my-service",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
        )
        create_environment(env)
        spec = get_environment_spec("my-service")
        self.assertIsNotNone(spec)
        self.assertEqual(spec.project_name, "my-service")

    def test_validate_environment(self):
        env = DevEnvironment(
            project_name="my-service",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
        )
        create_environment(env)
        is_valid, issues = validate_environment("my-service")
        self.assertTrue(is_valid)
        self.assertEqual(len(issues), 0)

    def test_check_environment_health(self):
        env = DevEnvironment(
            project_name="healthy-service",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
            debugger="debugpy",
            mock_services=[MockService(name="pg", image="postgres:16", port=5432)],
        )
        create_environment(env)
        health = check_environment_health("healthy-service")
        self.assertEqual(health["status"], "creating")
        self.assertTrue(health["debugging_configured"])
        self.assertTrue(health["mock_services_defined"])

    def test_is_environment_reproducible(self):
        env = DevEnvironment(
            project_name="reproducible-service",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            provider=EnvironmentProvider.DEV_CONTAINER,
            setup_commands=["poetry install"],
            runtime_dependencies=[
                DependencySpec(name="poetry.lock", version="locked", category="dev"),
            ],
        )
        create_environment(env)
        self.assertTrue(is_environment_reproducible("reproducible-service"))

    def test_generate_setup_script_function(self):
        env = DevEnvironment(
            project_name="scripted-service",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
            seed_data_path="fixtures/seed.sql",
        )
        create_environment(env)
        script = generate_setup_script("scripted-service")
        self.assertIsNotNone(script)
        self.assertIn("poetry install", script)
        self.assertIn("fixtures/seed.sql", script)


# =============================================================================
# Golden Paths Tests
# =============================================================================

class TestGoldenPaths(unittest.TestCase):
    """Tests for golden paths."""

    def test_all_paths_defined(self):
        self.assertEqual(len(GOLDEN_PATHS), 12)

    def test_get_golden_path(self):
        path = get_golden_path("GP-001")
        self.assertIsNotNone(path)
        self.assertEqual(path.name, "Create Service")

    def test_get_nonexistent_path(self):
        self.assertIsNone(get_golden_path("GP-999"))

    def test_list_all_paths(self):
        paths = list_golden_paths()
        self.assertEqual(len(paths), 12)

    def test_list_paths_by_category(self):
        create_paths = list_golden_paths(category=PathCategory.CREATE)
        self.assertGreater(len(create_paths), 0)
        for p in create_paths:
            self.assertEqual(p.category, PathCategory.CREATE)

    def test_list_paths_by_tags(self):
        ai_paths = list_golden_paths(tags=["ai", "ml"])
        self.assertGreater(len(ai_paths), 0)

    def test_execute_golden_path(self):
        result = execute_golden_path("GP-001", variables={"service_name": "test-svc"},
                                     skip_prerequisites=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["path_name"], "Create Service")

    def test_execute_golden_path_dry_run(self):
        result = execute_golden_path("GP-001", dry_run=True, skip_prerequisites=True)
        self.assertTrue(result["dry_run"])

    def test_execute_nonexistent_path(self):
        with self.assertRaises(ValueError):
            execute_golden_path("GP-999")

    def test_validate_path_prerequisites(self):
        is_valid, unmet = validate_path_prerequisites("GP-001")
        # GP-001 has prerequisites that cannot be auto-validated
        # So it will report them as unmet in this test environment
        self.assertFalse(is_valid)
        self.assertGreater(len(unmet), 0)

    def test_get_paths_by_category(self):
        grouped = get_paths_by_category()
        self.assertIn(PathCategory.CREATE, grouped)
        self.assertIn(PathCategory.INTEGRATE, grouped)
        self.assertIn(PathCategory.OPERATE, grouped)
        self.assertIn(PathCategory.RESPOND, grouped)

    def test_search_paths(self):
        results = search_paths("deploy")
        self.assertGreater(len(results), 0)
        self.assertTrue(any("Deploy" in p.name for p in results))

    def test_search_paths_no_match(self):
        results = search_paths("nonexistent_xyz")
        self.assertEqual(len(results), 0)

    def test_get_path_summary(self):
        summary = get_path_summary("GP-001")
        self.assertIsNotNone(summary)
        self.assertEqual(summary["name"], "Create Service")
        self.assertIn("steps_count", summary)


# =============================================================================
# Platform Tests
# =============================================================================

class TestPlatformCapabilities(unittest.TestCase):
    """Tests for platform capabilities."""

    def test_all_capabilities_defined(self):
        self.assertEqual(len(PLATFORM_CAPABILITIES), 12)

    def test_get_capability(self):
        cap = get_capability("CAP-PROJECT-CREATE")
        self.assertIsNotNone(cap)
        self.assertEqual(cap.name, "Project Creation")
        self.assertTrue(cap.self_service)

    def test_get_nonexistent_capability(self):
        self.assertIsNone(get_capability("CAP-999"))

    def test_list_all_capabilities(self):
        caps = list_capabilities()
        self.assertEqual(len(caps), 12)

    def test_list_self_service(self):
        caps = list_capabilities(self_service=True)
        self.assertGreater(len(caps), 0)
        for c in caps:
            self.assertTrue(c.self_service)

    def test_list_non_self_service(self):
        caps = list_capabilities(self_service=False)
        self.assertGreater(len(caps), 0)
        for c in caps:
            self.assertFalse(c.self_service)

    def test_list_by_category(self):
        caps = list_capabilities(category=CapabilityCategory.SECURITY)
        self.assertGreater(len(caps), 0)

    def test_list_by_tags(self):
        caps = list_capabilities(tags=["deploy"])
        self.assertGreater(len(caps), 0)


class TestPlatformRequests(unittest.TestCase):
    """Tests for platform requests."""

    def setUp(self):
        import enterprise.modules.developer_experience.platform as plat_mod
        plat_mod._request_store.clear()
        plat_mod._service_catalog.clear()

    def test_request_self_service_capability(self):
        req = request_capability(
            "CAP-PROJECT-CREATE",
            requested_by="alice",
            team="platform",
            parameters={"name": "my-project", "template": "python-service", "team": "platform"},
        )
        self.assertIsNotNone(req)
        self.assertEqual(req.status, CapabilityStatus.APPROVED)
        self.assertEqual(req.requested_by, "alice")

    def test_request_non_self_service_capability(self):
        req = request_capability(
            "CAP-SECRETS-REQUEST",
            requested_by="alice",
            team="platform",
            parameters={
                "secret_name": "api-key",
                "secret_type": "api_key",
                "project": "my-project",
                "justification": "Need to access external API",
            },
        )
        self.assertEqual(req.status, CapabilityStatus.PENDING)

    def test_request_missing_parameters(self):
        with self.assertRaises(ValueError):
            request_capability(
                "CAP-PROJECT-CREATE",
                requested_by="alice",
                team="platform",
                parameters={"name": "my-project"},  # Missing required 'template'
            )

    def test_request_nonexistent_capability(self):
        with self.assertRaises(ValueError):
            request_capability(
                "CAP-999",
                requested_by="alice",
                team="platform",
                parameters={},
            )

    def test_self_service_action(self):
        result = self_service_action(
            "CAP-PROJECT-CREATE",
            requested_by="bob",
            team="backend",
            parameters={"name": "svc", "template": "go-service", "team": "backend"},
        )
        self.assertEqual(result["status"], "completed")
        self.assertIn("request_id", result)

    def test_self_service_action_non_self_service(self):
        with self.assertRaises(ValueError):
            self_service_action(
                "CAP-SECRETS-REQUEST",
                requested_by="bob",
                team="backend",
                parameters={
                    "secret_name": "key",
                    "secret_type": "api_key",
                    "project": "x",
                    "justification": "testing",
                },
            )

    def test_approve_request(self):
        req = request_capability(
            "CAP-SECRETS-REQUEST",
            requested_by="alice",
            team="platform",
            parameters={
                "secret_name": "key", "secret_type": "api_key",
                "project": "x", "justification": "test",
            },
        )
        approved = approve_request(req.id, "security-lead")
        self.assertEqual(approved.status, CapabilityStatus.APPROVED)

    def test_reject_request(self):
        req = request_capability(
            "CAP-SECRETS-REQUEST",
            requested_by="alice",
            team="platform",
            parameters={
                "secret_name": "key", "secret_type": "api_key",
                "project": "x", "justification": "test",
            },
        )
        rejected = reject_request(req.id, "security-lead", "Insufficient justification")
        self.assertEqual(rejected.status, CapabilityStatus.REJECTED)
        self.assertEqual(rejected.error_message, "Insufficient justification")

    def test_get_user_requests(self):
        request_capability(
            "CAP-PROJECT-CREATE", "alice", "platform",
            {"name": "a", "template": "t", "team": "p"},
        )
        request_capability(
            "CAP-PROJECT-CREATE", "bob", "backend",
            {"name": "b", "template": "t", "team": "b"},
        )
        alice_reqs = get_user_requests("alice")
        self.assertEqual(len(alice_reqs), 1)

    def test_get_pending_approvals(self):
        request_capability(
            "CAP-SECRETS-REQUEST", "alice", "platform",
            {"secret_name": "k", "secret_type": "api_key", "project": "x", "justification": "t"},
        )
        pending = get_pending_approvals("security")
        self.assertGreater(len(pending), 0)


class TestServiceCatalog(unittest.TestCase):
    """Tests for service catalog."""

    def setUp(self):
        import enterprise.modules.developer_experience.platform as plat_mod
        plat_mod._service_catalog.clear()

    def test_register_service(self):
        svc = ServiceEntry(
            service_id="svc-001",
            name="User Service",
            description="User management",
            team="platform",
            repo_url="https://github.com/company/user-service",
            language="go",
        )
        registered = register_service(svc)
        self.assertEqual(registered.name, "User Service")

    def test_get_service_catalog(self):
        register_service(ServiceEntry(
            service_id="svc-001", name="User Service", description="desc",
            team="platform", repo_url="url", language="go",
        ))
        catalog = get_service_catalog()
        self.assertEqual(len(catalog), 1)

    def test_get_service_catalog_filters(self):
        register_service(ServiceEntry(
            service_id="svc-001", name="User Service", description="desc",
            team="platform", repo_url="url", language="go",
        ))
        register_service(ServiceEntry(
            service_id="svc-002", name="API Gateway", description="desc",
            team="backend", repo_url="url", language="python",
        ))

        platform_services = get_service_catalog(team="platform")
        self.assertEqual(len(platform_services), 1)

        go_services = get_service_catalog(language="go")
        self.assertEqual(len(go_services), 1)

        search_results = get_service_catalog(query="gateway")
        self.assertEqual(len(search_results), 1)

    def test_deregister_service(self):
        register_service(ServiceEntry(
            service_id="svc-001", name="User Service", description="desc",
            team="platform", repo_url="url", language="go",
        ))
        self.assertTrue(deregister_service("svc-001"))
        self.assertEqual(len(get_service_catalog()), 0)

    def test_get_platform_metrics(self):
        metrics = get_platform_metrics()
        self.assertIn("total_requests", metrics)
        self.assertIn("services_in_catalog", metrics)


# =============================================================================
# AI Rules Tests
# =============================================================================

class TestAIRules(unittest.TestCase):
    """Tests for AI coding rules."""

    def test_all_rules_defined(self):
        self.assertEqual(len(AI_RULES), 11)

    def test_get_ai_rules(self):
        rules = get_ai_rules()
        self.assertEqual(len(rules), 11)

    def test_get_rules_by_category(self):
        sec_rules = get_ai_rules(category=AIRuleCategory.SECURITY)
        self.assertGreater(len(sec_rules), 0)
        for r in sec_rules:
            self.assertEqual(r.category, AIRuleCategory.SECURITY)

    def test_get_rules_by_severity(self):
        blocking = get_ai_rules(severity=AIRuleSeverity.BLOCKING)
        self.assertGreater(len(blocking), 0)

    def test_get_rule_by_id(self):
        rule = get_rule_by_id("AI-R08")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.name, "No Secrets in Code")

    def test_get_rules_by_category_grouped(self):
        grouped = get_rules_by_category()
        self.assertIn(AIRuleCategory.PREREQUISITE, grouped)
        self.assertIn(AIRuleCategory.SECURITY, grouped)
        self.assertIn(AIRuleCategory.QUALITY, grouped)


class TestAISecretsChecking(unittest.TestCase):
    """Tests for AI secrets detection."""

    def test_no_secrets_in_clean_code(self):
        violations = check_secrets(
            'const API_URL = "https://api.example.com";\n'
            'const apiKey = process.env.API_KEY;\n',
            "config.ts",
        )
        self.assertEqual(len(violations), 0)

    def test_detects_hardcoded_api_key(self):
        violations = check_secrets(
            'const API_KEY = "sk-abc123def456ghi789jkl";\n',
            "secrets.ts",
        )
        self.assertGreater(len(violations), 0)
        self.assertEqual(violations[0].severity, AIRuleSeverity.BLOCKING)
        self.assertEqual(violations[0].file_path, "secrets.ts")

    def test_detects_password(self):
        violations = check_secrets(
            'PASSWORD = "superSecretPassword123!"',
            "config.py",
        )
        self.assertGreater(len(violations), 0)


class TestAIFileSizeChecking(unittest.TestCase):
    """Tests for AI file size checking."""

    def test_small_file_no_violation(self):
        files = {"small.py": "x = 1\n" * 10}
        violations = check_file_size(files)
        self.assertEqual(len(violations), 0)

    def test_large_file_violation(self):
        lines = ["print('line')\n"] * 500
        files = {"large.py": "".join(lines)}
        violations = check_file_size(files, max_lines=400)
        self.assertGreater(len(violations), 0)


class TestAIComplianceValidation(unittest.TestCase):
    """Tests for AI compliance validation."""

    def test_validate_clean_change(self):
        report = validate_ai_compliance(
            "PR-123",
            files_changed=["src/utils.py", "src/models.py"],
            file_contents={
                "src/utils.py": "def add(a, b): return a + b\n",
                "src/models.py": "class User:\n    pass\n",
            },
        )
        self.assertTrue(report.is_mergeable)

    def test_validate_with_secrets(self):
        report = validate_ai_compliance(
            "PR-456",
            files_changed=["src/config.py"],
            file_contents={
                "src/config.py": 'API_KEY = "sk-live-abc123def456"\n',
            },
        )
        self.assertFalse(report.is_mergeable)
        self.assertGreater(report.violation_count, 0)

    def test_enforce_ai_rules_strict(self):
        with self.assertRaises(ValueError):
            enforce_ai_rules(
                "PR-789",
                files_changed=["config.py"],
                file_contents={
                    "config.py": 'PASSWORD="supersecretpassword1234567890abc"\n',
                },
                strict=True,
            )

    def test_enforce_ai_rules_lenient(self):
        passed, report = enforce_ai_rules(
            "PR-789",
            files_changed=["config.py"],
            file_contents={
                "config.py": 'PASSWORD="supersecretpassword1234567890abc"\n',
            },
            strict=False,
        )
        self.assertFalse(passed)
        self.assertIsInstance(report, AIRulesReport)

    def test_generate_ai_rules_report(self):
        report = generate_ai_rules_report(
            "PR-000",
            files_changed=["clean.py"],
            file_contents={"clean.py": "# nothing to see here\n"},
            output_format="json",
        )
        data = json.loads(report)
        self.assertEqual(data["change_id"], "PR-000")
        self.assertTrue(data["is_mergeable"])


# =============================================================================
# Documentation Tests
# =============================================================================

class TestDocStandards(unittest.TestCase):
    """Tests for documentation standards."""

    def test_all_standards_defined(self):
        self.assertEqual(len(DOC_STANDARDS), 9)

    def test_get_doc_standards(self):
        standards = get_doc_standards()
        self.assertEqual(len(standards), 9)

    def test_get_gate_by_name(self):
        gate = get_gate_by_name("current")
        self.assertEqual(gate, DocQualityGate.CURRENT)

        gate = get_gate_by_name("task oriented")
        self.assertEqual(gate, DocQualityGate.TASK_ORIENTED)

    def test_get_gate_by_name_invalid(self):
        self.assertIsNone(get_gate_by_name("nonexistent"))

    def test_get_standards_summary(self):
        summary = get_standards_summary()
        self.assertEqual(summary["total_standards"], 9)
        self.assertIn("standards", summary)


class TestDocContentAssessment(unittest.TestCase):
    """Tests for document content assessment."""

    def test_assess_well_structured_doc(self):
        content = (
            "# Getting Started Guide\n\n"
            "## How to Install\n\n"
            "This guide shows you how to set up the project.\n\n"
            "### Example\n\n"
            "```bash\nnpm install\n```\n\n"
            "See [source code](https://github.com/company/repo/blob/main/src).\n"
        )
        assessments = assess_doc_content(content)
        self.assertEqual(len(assessments), len(DOC_STANDARDS))

    def test_assess_empty_doc(self):
        assessments = assess_doc_content("")
        self.assertEqual(len(assessments), len(DOC_STANDARDS))
        # Most checks should fail on empty content
        passed = sum(1 for a in assessments if a.passed)
        self.assertLess(passed, len(DOC_STANDARDS))

    def test_assess_doc_with_examples(self):
        content = (
            "# API Reference\n\n"
            "## Usage\n\n"
            "Here is an example:\n\n"
            "```python\nfrom mylib import Client\nclient = Client()\n```\n"
        )
        assessments = assess_doc_content(content)
        example_assessment = next(
            a for a in assessments
            if a.standard.gate == DocQualityGate.EXAMPLE_DRIVEN
        )
        self.assertTrue(example_assessment.passed)


class TestDocValidation(unittest.TestCase):
    """Tests for documentation validation."""

    def test_validate_documentation(self):
        report = validate_documentation(
            doc_path="docs/setup.md",
            content="# Setup Guide\n\n## Installation\n\n```bash\npip install\n```",
            doc_title="Setup Guide",
            owner="platform-team",
            last_updated=datetime.utcnow(),
        )
        self.assertIsInstance(report, DocReport)
        self.assertEqual(report.doc_path, "docs/setup.md")
        self.assertEqual(report.owner, "platform-team")
        self.assertEqual(report.status, DocStatus.PUBLISHED)

    def test_validate_stale_documentation(self):
        report = validate_documentation(
            doc_path="docs/old.md",
            content="# Old Document",
            last_updated=datetime.utcnow() - timedelta(days=100),
        )
        self.assertEqual(report.status, DocStatus.STALE)
        self.assertTrue(report.is_stale)

    def test_report_grade(self):
        report = validate_documentation(
            doc_path="docs/good.md",
            content=(
                "# Great Documentation\n\n"
                "## How to Use\n\n"
                "### Example\n\n```python\nexample()\n```\n\n"
                "See source at https://github.com/company/repo\n\n"
                "Step 1: Install\nStep 2: Configure\nStep 3: Run\n"
            ),
            last_updated=datetime.utcnow(),
        )
        self.assertIn(report.grade, ["A", "B", "C", "D", "F"])
        # Well-structured doc should get A or B
        self.assertIn(report.grade, ["A", "B"])

    def test_report_to_dict(self):
        report = validate_documentation(
            doc_path="docs/test.md",
            content="# Test",
        )
        d = report.to_dict()
        self.assertIn("doc_path", d)
        self.assertIn("overall_score", d)
        self.assertIn("grade", d)


class TestAssessDocQuality(unittest.TestCase):
    """Tests for batch documentation quality assessment."""

    def test_assess_multiple_docs(self):
        docs = {
            "docs/api.md": {
                "title": "API Reference",
                "content": "# API\n\n```python\napi.call()\n```",
                "owner": "api-team",
                "last_updated": datetime.utcnow(),
            },
            "docs/guide.md": {
                "title": "User Guide",
                "content": "# Guide\n\n## How to start\n\nStep 1: Install",
                "owner": "docs-team",
                "last_updated": datetime.utcnow() - timedelta(days=100),
            },
        }
        reports = assess_doc_quality(docs)
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[1].status, DocStatus.STALE)

    def test_generate_doc_report_summary(self):
        docs = {
            "docs/test.md": {
                "title": "Test",
                "content": "# Test Doc\n## Example\n```code```",
                "owner": "team",
                "last_updated": datetime.utcnow(),
            },
        }
        report = generate_doc_report(docs, output_format="summary")
        self.assertIn("Documentation Quality Report", report)

    def test_generate_doc_report_json(self):
        docs = {
            "docs/test.md": {
                "title": "Test",
                "content": "# Test",
                "owner": "team",
                "last_updated": datetime.utcnow(),
            },
        }
        report = generate_doc_report(docs, output_format="json")
        data = json.loads(report)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)


# =============================================================================
# Metrics Tests
# =============================================================================

class TestMetricCollection(unittest.TestCase):
    """Tests for metric collection."""

    def setUp(self):
        clear_metrics()

    def test_collect_metric(self):
        metric = collect_metric(
            name="test_metric",
            value=42.0,
            unit="count",
            category=MetricCategory.SPEED,
            team="test-team",
        )
        self.assertEqual(metric.name, "test_metric")
        self.assertEqual(metric.value, 42.0)
        self.assertEqual(metric.team, "test-team")
        self.assertEqual(get_metric_count(), 1)

    def test_collect_multiple_metrics(self):
        for i in range(5):
            collect_metric(f"metric_{i}", float(i), "count", MetricCategory.SPEED)
        self.assertEqual(get_metric_count(), 5)


class TestConvenienceMetrics(unittest.TestCase):
    """Tests for convenience metric functions."""

    def setUp(self):
        clear_metrics()

    def test_track_setup_time(self):
        metric = track_setup_time(120.5, "dev-001", "platform")
        self.assertEqual(metric.name, "setup_time")
        self.assertEqual(metric.value, 120.5)
        self.assertEqual(metric.category, MetricCategory.SPEED)

    def test_track_build_duration(self):
        metric = track_build_duration(45.0, "my-service", commit_sha="abc123")
        self.assertEqual(metric.name, "build_duration")
        self.assertEqual(metric.tags["commit_sha"], "abc123")

    def test_track_test_duration(self):
        metric = track_test_duration(30.0, "my-service", test_type="integration")
        self.assertEqual(metric.name, "integration_test_duration")
        self.assertEqual(metric.tags["test_type"], "integration")

    def test_track_deploy_frequency(self):
        metric = track_deploy_frequency(10, 48, "platform", "api-svc")
        self.assertEqual(metric.name, "deploy_frequency")
        self.assertEqual(metric.unit, "deploys_per_day")
        # 10 deploys in 48 hours = 5 per day
        self.assertAlmostEqual(metric.value, 5.0)

    def test_track_deploy_success(self):
        metric = track_deploy_success(True, "platform", "api-svc", "abc")
        self.assertEqual(metric.value, 1.0)

        metric2 = track_deploy_success(False, "platform", "api-svc", "def")
        self.assertEqual(metric2.value, 0.0)

    def test_track_pr_cycle_time(self):
        metric = track_pr_cycle_time(4.5, "team-a", "project-x", "PR-123", "dev-001")
        self.assertEqual(metric.name, "pr_cycle_time")
        self.assertEqual(metric.value, 4.5)
        self.assertEqual(metric.unit, "hours")

    def test_track_incident_recovery(self):
        metric = track_incident_recovery(15.0, "sre", "api-svc", "INC-001")
        self.assertEqual(metric.name, "mttr")
        self.assertEqual(metric.value, 15.0)
        self.assertEqual(metric.unit, "minutes")

    def test_track_developer_satisfaction(self):
        metric = track_developer_satisfaction(9.0, "dev-001", "platform")
        self.assertEqual(metric.name, "developer_satisfaction")
        self.assertEqual(metric.value, 9.0)

    def test_track_rework_rate(self):
        metric = track_rework_rate(5, 20, "team-a", "project-x")
        self.assertEqual(metric.name, "rework_rate")
        self.assertEqual(metric.value, 25.0)  # 5/20 = 25%

    def test_track_defect_escape_rate(self):
        metric = track_defect_escape_rate(3, 10, "team-a")
        self.assertEqual(metric.value, 30.0)  # 3/10 = 30%

    def test_track_documentation_success_rate(self):
        metric = track_documentation_success_rate(8, 10, "docs-team")
        self.assertEqual(metric.value, 80.0)


class TestTimerMetrics(unittest.TestCase):
    """Tests for timer-based metrics."""

    def setUp(self):
        clear_metrics()

    def test_start_stop_timer(self):
        timer_id = start_timer("test_timer")
        metric = stop_timer(timer_id, "timer_duration", MetricCategory.SPEED)
        self.assertIsNotNone(metric)
        self.assertEqual(metric.name, "timer_duration")
        self.assertGreaterEqual(metric.value, 0)

    def test_stop_nonexistent_timer(self):
        metric = stop_timer("nonexistent", "test", MetricCategory.SPEED)
        self.assertIsNone(metric)

    def test_timed_metric_context(self):
        with timed_metric("context_metric", MetricCategory.SPEED):
            pass
        self.assertEqual(get_metric_count(), 1)


class TestDORAMetrics(unittest.TestCase):
    """Tests for DORA metrics calculation."""

    def setUp(self):
        clear_metrics()

    def test_calculate_empty_dora(self):
        dora = calculate_dora_metrics(team="empty-team")
        self.assertEqual(dora.team, "empty-team")
        self.assertEqual(dora.total_deployments, 0)
        # With all zero defaults, empty DORA scores "High" (0% failure rate,
        # 0 min MTTR, and 0 hour lead time are all "elite" individually)
        self.assertEqual(dora.performance_level(), "High")

    def test_calculate_elite_dora(self):
        # Elite: daily deploys, fast lead time, low failure rate, fast MTTR
        for _ in range(20):
            track_deploy_success(True, "elite-team", "elite-svc")
        track_deploy_success(False, "elite-team", "elite-svc")  # 1 failure
        for _ in range(3):
            track_incident_recovery(5.0, "elite-team")  # 5 min recovery

        dora = calculate_dora_metrics(team="elite-team", service="elite-svc")
        self.assertEqual(dora.total_deployments, 21)
        self.assertEqual(dora.failed_deployments, 1)
        self.assertAlmostEqual(dora.change_failure_rate_percent, 100 / 21, places=0)

    def test_dora_performance_level_elite(self):
        dora = DORAMetrics(
            team="test",
            deployment_frequency_daily=5.0,
            lead_time_for_changes_hours=0.5,
            change_failure_rate_percent=2.0,
            mttr_minutes=30.0,
        )
        self.assertEqual(dora.performance_level(), "Elite")

    def test_dora_performance_level_high(self):
        dora = DORAMetrics(
            team="test",
            deployment_frequency_weekly=3.0,
            lead_time_for_changes_hours=12.0,
            change_failure_rate_percent=8.0,
            mttr_minutes=120.0,
        )
        self.assertEqual(dora.performance_level(), "High")

    def test_dora_performance_level_medium(self):
        dora = DORAMetrics(
            team="test",
            deployment_frequency_weekly=1.0,
            lead_time_for_changes_hours=72.0,
            change_failure_rate_percent=12.0,
            mttr_minutes=2000.0,
        )
        self.assertEqual(dora.performance_level(), "Medium")

    def test_dora_performance_level_low(self):
        dora = DORAMetrics(
            team="test",
            deployment_frequency_weekly=0.1,
            lead_time_for_changes_hours=200.0,
            change_failure_rate_percent=20.0,
            mttr_minutes=5000.0,
        )
        self.assertEqual(dora.performance_level(), "Low")

    def test_dora_to_dict(self):
        dora = DORAMetrics(
            team="test",
            deployment_frequency_daily=1.0,
            lead_time_for_changes_hours=4.0,
            change_failure_rate_percent=5.0,
            mttr_minutes=60.0,
            total_deployments=10,
        )
        d = dora.to_dict()
        self.assertEqual(d["team"], "test")
        self.assertIn("performance_level", d)
        self.assertEqual(d["total_deployments"], 10)

    def test_dora_to_json(self):
        dora = DORAMetrics(team="test")
        j = dora.to_json()
        data = json.loads(j)
        self.assertEqual(data["team"], "test")


class TestMetricsDashboard(unittest.TestCase):
    """Tests for metrics dashboard and reporting."""

    def setUp(self):
        clear_metrics()
        # Seed some metrics
        for i in range(5):
            track_setup_time(100.0 + i, f"dev-{i}", "platform")
            track_build_duration(30.0, f"svc-{i % 2}")
        track_developer_satisfaction(9.0, "dev-1", "platform")
        track_developer_satisfaction(7.0, "dev-2", "platform")
        track_developer_satisfaction(8.0, "dev-3", "platform")

    def test_get_metrics_dashboard(self):
        dashboard = get_metrics_dashboard()
        self.assertIn("total_metrics_collected", dashboard)
        self.assertIn("aggregates", dashboard)
        self.assertIn("developer_enps", dashboard)
        # eNPS: promoters (9+) = 1, detractors (<=6) = 0, total = 3
        # eNPS = (1 - 0) / 3 * 100 = 33.3
        self.assertIsNotNone(dashboard["developer_enps"])

    def test_get_metrics_dashboard_filtered(self):
        dashboard = get_metrics_dashboard(team="platform")
        self.assertIsNotNone(dashboard)

    def test_generate_metrics_report_json(self):
        report = generate_metrics_report(output_format="json")
        data = json.loads(report)
        self.assertIn("aggregates", data)
        self.assertIn("dora", data)

    def test_generate_metrics_report_dora(self):
        report = generate_metrics_report(output_format="dora")
        data = json.loads(report)
        self.assertIn("performance_level", data)

    def test_generate_metrics_report_summary(self):
        report = generate_metrics_report(output_format="summary")
        self.assertIn("Developer Productivity Metrics", report)

    def test_clear_metrics(self):
        count = clear_metrics()
        self.assertGreater(count, 0)
        self.assertEqual(get_metric_count(), 0)


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration(unittest.TestCase):
    """Cross-module integration tests."""

    def test_journey_to_standards_integration(self):
        """Journey's repo discovery stage links to standards validation."""
        journey = DeveloperJourney("dev-int", "Integration", "team", "role")
        # After repo discovery, we should be able to validate standards
        standards = get_required_standards()
        self.assertGreater(len(standards), 10)
        # Complete stages up to repo discovery
        journey.stages[JourneyStage.ACCESS_REQUEST].complete()
        journey.stages[JourneyStage.ACCOUNT_SETUP].complete()
        journey.stages[JourneyStage.LOCAL_ENV_SETUP].complete()
        journey.advance(JourneyStage.REPO_DISCOVERY, notes="Repos found")
        self.assertEqual(
            journey.stages[JourneyStage.REPO_DISCOVERY].status,
            JourneyStageStatus.COMPLETED,
        )

    def test_environment_to_platform_integration(self):
        """Environment setup leads to platform provisioning."""
        env = DevEnvironment(
            project_name="int-svc",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
            mock_services=[MockService(name="pg", image="postgres:16", port=5432)],
        )
        create_environment(env)

        # Use platform to request database
        req = request_capability(
            "CAP-DB-PROVISION",
            "dev",
            "platform",
            {"db_type": "postgresql", "environment": "dev", "project": "int-svc"},
        )
        self.assertEqual(req.status, CapabilityStatus.APPROVED)
        self.assertEqual(req.parameters["db_type"], "postgresql")

    def test_golden_path_to_ai_rules_integration(self):
        """Golden path 'Create Service' should comply with AI rules."""
        path = get_golden_path("GP-001")
        self.assertIsNotNone(path)

        # After golden path execution, validate AI compliance
        report = validate_ai_compliance(
            "create-service",
            files_changed=["src/main.py", "src/config.py"],
            file_contents={
                "src/main.py": "def main():\n    pass\n",
                "src/config.py": "DATABASE_URL = os.environ.get('DATABASE_URL')\n",
            },
        )
        self.assertTrue(report.is_mergeable)

    def test_full_developer_flow(self):
        """Simulate a complete developer flow through all modules."""
        # 1. Create developer journey
        journey = create_journey("flow-dev", "Flow Dev", "platform", "engineer")
        self.assertIsNotNone(journey)

        # 2. Set up environment
        env = DevEnvironment(
            project_name="flow-service",
            language="python",
            language_version="3.12",
            package_manager="poetry",
            setup_commands=["poetry install"],
        )
        create_environment(env)

        # 3. Access platform
        req = request_capability(
            "CAP-PROJECT-CREATE",
            "flow-dev",
            "platform",
            {"name": "flow-service", "template": "python-service", "team": "platform"},
        )
        self.assertEqual(req.status, CapabilityStatus.APPROVED)

        # 4. Follow golden path
        result = execute_golden_path("GP-001", {"service_name": "flow-service"},
                                     skip_prerequisites=True)
        self.assertTrue(result["success"])

        # 5. Validate standards
        repo_files = ["README.md", "LICENSE", "Dockerfile", ".env.example", "CONTRIBUTING.md"]
        report = validate_repo_standards("flow-service", "/flow-service", repo_files)
        self.assertIsInstance(report, ComplianceReport)

        # 6. Check AI rules compliance
        ai_report = validate_ai_compliance(
            "flow-pr",
            files_changed=["src/main.py"],
            file_contents={"src/main.py": "def main(): pass\n"},
        )
        self.assertTrue(ai_report.is_mergeable)

        # 7. Track metrics
        track_setup_time(45.0, "flow-dev", "platform", "flow-service")
        track_deploy_success(True, "platform", "flow-service")
        dashboard = get_metrics_dashboard(team="platform")
        self.assertIsNotNone(dashboard)

        # 8. Validate docs
        doc_report = validate_documentation(
            doc_path="flow-service/README.md",
            content="# Flow Service\n\n## How to Run\n\n```bash\npoetry run start\n```",
            doc_title="Flow Service",
            owner="platform",
            last_updated=datetime.utcnow(),
        )
        self.assertIn(doc_report.grade, ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main(verbosity=2)