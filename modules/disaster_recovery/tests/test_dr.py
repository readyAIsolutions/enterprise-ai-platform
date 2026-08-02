"""
Comprehensive tests for the Disaster Recovery OS module.

Covers BIA, RTO/RPO, scenarios, backup, recovery, cyber recovery,
AI continuity, crisis management, and exercises.
"""

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# ------------------------------------------------------------------
# BIA tests
# ------------------------------------------------------------------


class TestBIAEngine(unittest.TestCase):
    """Test Business Impact Analysis engine."""

    def setUp(self):
        from enterprise.modules.disaster_recovery.bia import BIAEngine, CriticalityLevel, ImpactCategory
        self.BIAEngine = BIAEngine
        self.CriticalityLevel = CriticalityLevel
        self.ImpactCategory = ImpactCategory

    def test_assess_service_critical(self):
        engine = self.BIAEngine()
        asset = engine.assess_service(
            name="payments",
            service_type="api",
            max_downtime_hours=0.5,
            financial_impact_per_hour=500_000,
            legal_risk=True,
            customer_impact=True,
            safety_impact=False,
        )
        self.assertEqual(asset.name, "payments")
        self.assertEqual(asset.criticality, self.CriticalityLevel.CRITICAL)
        self.assertGreater(asset.annual_financial_risk, 0)

    def test_assess_service_low(self):
        engine = self.BIAEngine()
        asset = engine.assess_service(
            name="docs",
            service_type="web",
            max_downtime_hours=48,
            financial_impact_per_hour=10,
            legal_risk=False,
            customer_impact=False,
            safety_impact=False,
        )
        self.assertEqual(asset.criticality, self.CriticalityLevel.LOW)

    def test_calculate_financial_impact(self):
        engine = self.BIAEngine()
        engine.assess_service(
            name="api",
            service_type="api",
            max_downtime_hours=1,
            financial_impact_per_hour=1000,
        )
        impact = engine.calculate_financial_impact("api", downtime_hours=4)
        self.assertEqual(impact, 4000)

    def test_calculate_financial_impact_unknown(self):
        engine = self.BIAEngine()
        impact = engine.calculate_financial_impact("nonexistent", downtime_hours=10)
        self.assertEqual(impact, 0.0)

    def test_map_dependency_chain(self):
        engine = self.BIAEngine()
        engine.assess_service(name="a", service_type="api", max_downtime_hours=1)
        engine.assess_service(name="b", service_type="db", max_downtime_hours=1, dependencies=["a"])
        engine.assess_service(name="c", service_type="web", max_downtime_hours=1, dependencies=["b"])
        chain = engine.map_dependency_chain("c")
        self.assertIn("a", chain)
        self.assertIn("b", chain)
        self.assertIn("c", chain)

    def test_find_dependents(self):
        engine = self.BIAEngine()
        engine.assess_service(name="db", service_type="db", max_downtime_hours=1)
        engine.assess_service(name="api", service_type="api", max_downtime_hours=1, dependencies=["db"])
        engine.assess_service(name="web", service_type="web", max_downtime_hours=1, dependencies=["api"])
        deps = engine.find_dependents("db")
        self.assertIn("api", deps)
        self.assertIn("web", deps)

    def test_prioritize_recovery(self):
        engine = self.BIAEngine()
        engine.assess_service(name="low", service_type="web", max_downtime_hours=48, financial_impact_per_hour=10)
        engine.assess_service(name="high", service_type="api", max_downtime_hours=1, financial_impact_per_hour=10000)
        engine.assess_service(name="crit", service_type="db", max_downtime_hours=0.1, financial_impact_per_hour=500000,
                              legal_risk=True, customer_impact=True)
        prioritized = engine.prioritize_recovery()
        self.assertEqual(prioritized[0].name, "crit")
        self.assertEqual(prioritized[-1].name, "low")

    def test_generate_bia_report(self):
        engine = self.BIAEngine()
        engine.assess_service(name="svc", service_type="api", max_downtime_hours=2, financial_impact_per_hour=1000)
        report = engine.generate_bia_report()
        self.assertIn("BUSINESS IMPACT ANALYSIS REPORT", report)
        self.assertIn("svc", report)


# ------------------------------------------------------------------
# RTO/RPO tests
# ------------------------------------------------------------------


class TestRTOPlanner(unittest.TestCase):
    """Test RTO/RPO planning engine."""

    def setUp(self):
        from enterprise.modules.disaster_recovery.rto_rpo import RTOPlanner, RecoveryTier, RTOPlan
        self.RTOPlanner = RTOPlanner
        self.RecoveryTier = RecoveryTier
        self.RTOPlan = RTOPlan

    def test_define_recovery_objective(self):
        planner = self.RTOPlanner()
        plan = planner.define_recovery_objective(
            service_name="api",
            rto_minutes=5,
            rpo_minutes=2,
            max_tolerable_downtime=10,
            recovery_priority=1,
            required_infrastructure=["kubernetes_cluster"],
            required_personnel=["alice"],
            required_data_sources=["postgres_replica"],
        )
        self.assertEqual(plan.service_name, "api")
        self.assertEqual(plan.rto_minutes, 5)
        self.assertEqual(plan.recovery_tier, self.RecoveryTier.TIER_1_MINUTES)

    def test_recovery_tier_zero(self):
        planner = self.RTOPlanner()
        plan = planner.define_recovery_objective("api", rto_minutes=0.5, rpo_minutes=0,
                                                   max_tolerable_downtime=1, recovery_priority=1)
        self.assertEqual(plan.recovery_tier, self.RecoveryTier.TIER_0_ZERO)

    def test_recovery_tier_days(self):
        planner = self.RTOPlanner()
        plan = planner.define_recovery_objective("batch", rto_minutes=500, rpo_minutes=120,
                                                   max_tolerable_downtime=1000, recovery_priority=10)
        self.assertEqual(plan.recovery_tier, self.RecoveryTier.TIER_3_DAYS)

    def test_calculate_rto(self):
        planner = self.RTOPlanner()
        rto = planner.calculate_rto(
            infrastructure_type="container",
            data_restore_time_minutes=10,
            service_startup_time_minutes=3,
            validation_time_minutes=2,
        )
        # provision=2 + restore=10 + startup=3 + validation=2
        self.assertEqual(rto, 17.0)

    def test_calculate_rpo(self):
        planner = self.RTOPlanner()
        rpo = planner.calculate_rpo(backup_frequency_minutes=5, replication_lag_minutes=1)
        self.assertEqual(rpo, 6.0)

    def test_validate_feasibility_passes(self):
        planner = self.RTOPlanner()
        planner.define_recovery_objective(
            "api", rto_minutes=5, rpo_minutes=2, max_tolerable_downtime=10, recovery_priority=1,
            required_infrastructure=["kubernetes_cluster"], required_personnel=["alice"],
            required_data_sources=["postgres_replica"],
        )
        feasible, gaps = planner.validate_feasibility(
            "api",
            available_infrastructure=["kubernetes_cluster"],
            available_personnel=["alice", "bob"],
            available_data_sources=["postgres_replica"],
        )
        self.assertTrue(feasible)
        self.assertEqual(gaps, [])

    def test_validate_feasibility_fails(self):
        planner = self.RTOPlanner()
        planner.define_recovery_objective(
            "api", rto_minutes=15, rpo_minutes=2, max_tolerable_downtime=10, recovery_priority=1,
            required_infrastructure=["kubernetes_cluster", "load_balancer"],
            required_personnel=["alice"],
            required_data_sources=["postgres_replica"],
        )
        feasible, gaps = planner.validate_feasibility(
            "api",
            available_infrastructure=["kubernetes_cluster"],
            available_personnel=[],
            available_data_sources=[],
        )
        self.assertFalse(feasible)
        self.assertGreater(len(gaps), 0)

    def test_validate_feasibility_no_plan(self):
        planner = self.RTOPlanner()
        feasible, gaps = planner.validate_feasibility("unknown", [], [], [])
        self.assertFalse(feasible)

    def test_generate_recovery_schedule(self):
        planner = self.RTOPlanner()
        planner.define_recovery_objective("db", rto_minutes=10, rpo_minutes=2,
                                            max_tolerable_downtime=15, recovery_priority=1)
        planner.define_recovery_objective("api", rto_minutes=5, rpo_minutes=1,
                                            max_tolerable_downtime=10, recovery_priority=2)
        planner.define_recovery_objective("web", rto_minutes=3, rpo_minutes=1,
                                            max_tolerable_downtime=30, recovery_priority=3)
        schedule = planner.generate_recovery_schedule()
        self.assertEqual(len(schedule), 3)
        self.assertEqual(schedule[0][0], "db")  # priority 1

    def test_allocate_resources(self):
        planner = self.RTOPlanner()
        planner.define_recovery_objective("db", rto_minutes=10, rpo_minutes=2,
                                            max_tolerable_downtime=15, recovery_priority=1)
        planner.define_recovery_objective("api", rto_minutes=5, rpo_minutes=1,
                                            max_tolerable_downtime=10, recovery_priority=3)
        allocation = planner.allocate_resources("engineers", 10)
        self.assertIn("db", allocation)
        self.assertIn("api", allocation)
        self.assertEqual(sum(allocation.values()), 10)


# ------------------------------------------------------------------
# Scenario tests
# ------------------------------------------------------------------


class TestScenarioLibrary(unittest.TestCase):
    """Test disaster scenario library."""

    def setUp(self):
        from enterprise.modules.disaster_recovery.scenarios import ScenarioLibrary, Scenario, ScenarioType
        self.ScenarioLibrary = ScenarioLibrary
        self.Scenario = Scenario
        self.ScenarioType = ScenarioType

    def test_add_and_get(self):
        lib = self.ScenarioLibrary()
        scenario = self.Scenario(
            type=self.ScenarioType.RANSOMWARE,
            title="Ransomware",
            description="Test",
            likelihood=0.5,
            impact_severity=0.9,
            affected_services=["db"],
        )
        lib.add_scenario(scenario)
        retrieved = lib.get_by_type(self.ScenarioType.RANSOMWARE)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.title, "Ransomware")
        self.assertAlmostEqual(retrieved.risk_score, 0.45)

    def test_rank_by_risk(self):
        lib = self.ScenarioLibrary()
        lib.add_scenario(self.Scenario(
            type=self.ScenarioType.NETWORK_OUTAGE, title="Low", description="",
            likelihood=0.1, impact_severity=0.1,
        ))
        lib.add_scenario(self.Scenario(
            type=self.ScenarioType.RANSOMWARE, title="High", description="",
            likelihood=0.9, impact_severity=0.9,
        ))
        ranked = lib.rank_by_risk()
        self.assertEqual(ranked[0].title, "High")
        self.assertEqual(ranked[-1].title, "Low")

    def test_filter_by_service(self):
        lib = self.ScenarioLibrary()
        lib.add_scenario(self.Scenario(
            type=self.ScenarioType.DB_CORRUPTION, title="DB", description="",
            likelihood=0.1, impact_severity=0.8, affected_services=["postgres"],
        ))
        lib.add_scenario(self.Scenario(
            type=self.ScenarioType.NETWORK_OUTAGE, title="Net", description="",
            likelihood=0.2, impact_severity=0.5, affected_services=["api"],
        ))
        results = lib.filter_by_service("postgres")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "DB")

    def test_generate_runbook(self):
        lib = self.ScenarioLibrary()
        lib.seed_defaults()
        runbook = lib.generate_runbook()
        self.assertIn("DISASTER SCENARIO RUNBOOK", runbook)
        self.assertIn("Ransomware", runbook)
        self.assertIn("Cloud Region Failure", runbook)

    def test_evaluate_readiness(self):
        lib = self.ScenarioLibrary()
        lib.add_scenario(self.Scenario(
            type=self.ScenarioType.RANSOMWARE, title="R", description="",
            likelihood=0.5, impact_severity=0.9, affected_services=["db", "storage"],
        ))
        statuses = lib.evaluate_readiness(
            available_services=["db", "storage"],
            backup_coverage={"db": True, "storage": True},
        )
        self.assertEqual(statuses["ransomware"], "ready")

    def test_seed_defaults(self):
        lib = self.ScenarioLibrary()
        lib.seed_defaults()
        self.assertGreaterEqual(len(lib.list_all()), 4)


# ------------------------------------------------------------------
# Backup tests
# ------------------------------------------------------------------


class TestBackupManager(unittest.TestCase):
    """Test backup management system."""

    def setUp(self):
        from enterprise.modules.disaster_recovery.backup import BackupManager, BackupType, BackupPolicy
        self.BackupManager = BackupManager
        self.BackupType = BackupType
        self.BackupPolicy = BackupPolicy

    def test_configure_policy(self):
        mgr = self.BackupManager()
        policy = mgr.configure_policy(
            name="daily_full",
            backup_type=self.BackupType.FULL,
            frequency_hours=24,
            immutable=True,
        )
        self.assertEqual(policy.name, "daily_full")
        self.assertEqual(policy.backup_type, self.BackupType.FULL)
        self.assertTrue(policy.immutable)

    def test_execute_backup(self):
        mgr = self.BackupManager()
        mgr.configure_policy("daily_full", self.BackupType.FULL, frequency_hours=24)
        record = mgr.execute_backup("daily_full", source_path="/data")
        self.assertIsNotNone(record.backup_id)
        self.assertEqual(record.policy_name, "daily_full")
        self.assertGreater(len(record.checksum), 0)

    def test_execute_backup_unknown_policy(self):
        mgr = self.BackupManager()
        with self.assertRaises(ValueError):
            mgr.execute_backup("nonexistent")

    def test_verify_integrity(self):
        mgr = self.BackupManager()
        mgr.configure_policy("daily", self.BackupType.FULL, frequency_hours=24)
        record = mgr.execute_backup("daily")
        self.assertTrue(mgr.verify_integrity(record.backup_id))

    def test_verify_integrity_unknown(self):
        mgr = self.BackupManager()
        self.assertFalse(mgr.verify_integrity("fake-id"))

    def test_test_restoration(self):
        mgr = self.BackupManager()
        mgr.configure_policy("daily", self.BackupType.FULL, frequency_hours=24)
        record = mgr.execute_backup("daily")
        self.assertTrue(mgr.test_restoration(record.backup_id))

    def test_list_retained_versions(self):
        mgr = self.BackupManager()
        mgr.configure_policy("daily", self.BackupType.FULL, frequency_hours=24)
        mgr.execute_backup("daily")
        mgr.execute_backup("daily")
        versions = mgr.list_retained_versions("daily")
        self.assertEqual(len(versions), 2)

    def test_rotate_keys(self):
        mgr = self.BackupManager()
        key = mgr.rotate_keys("master_key")
        self.assertEqual(len(key), 32)

    def test_monitor_backup_health(self):
        mgr = self.BackupManager()
        mgr.configure_policy("daily", self.BackupType.FULL, frequency_hours=24)
        mgr.execute_backup("daily")
        health = mgr.monitor_backup_health()
        self.assertTrue(health["healthy"])
        self.assertEqual(health["policies"], 1)
        self.assertEqual(health["total_backups"], 1)

    def test_monitor_backup_health_overdue(self):
        mgr = self.BackupManager()
        mgr.configure_policy("hourly", self.BackupType.FULL, frequency_hours=0.1)
        health = mgr.monitor_backup_health()
        self.assertFalse(health["healthy"])
        self.assertIn("hourly", health["policies_without_recent_backup"])


# ------------------------------------------------------------------
# Recovery tests
# ------------------------------------------------------------------


class TestRecoveryEngine(unittest.TestCase):
    """Test active recovery engine."""

    def setUp(self):
        from enterprise.modules.disaster_recovery.recovery import RecoveryEngine, RecoveryMode, RecoveryPlan
        self.RecoveryEngine = RecoveryEngine
        self.RecoveryMode = RecoveryMode
        self.RecoveryPlan = RecoveryPlan

    def test_create_plan(self):
        engine = self.RecoveryEngine()
        plan = engine.create_plan(
            name="primary_api",
            mode=self.RecoveryMode.AUTOMATED,
            multi_zone=True,
            multi_region=True,
            failover_enabled=True,
            alt_communication_channels=["slack", "pagerduty"],
        )
        self.assertEqual(plan.name, "primary_api")
        self.assertTrue(plan.multi_zone)
        self.assertTrue(plan.failover_enabled)
        self.assertEqual(len(plan.alt_communication_channels), 2)

    def test_execute_failover(self):
        engine = self.RecoveryEngine()
        engine.create_plan("api", failover_enabled=True)
        self.assertTrue(engine.execute_failover("api"))
        self.assertIsNotNone(engine.get_plan("api").last_failover_at)

    def test_execute_failover_disabled(self):
        engine = self.RecoveryEngine()
        engine.create_plan("api", failover_enabled=False)
        self.assertFalse(engine.execute_failover("api"))

    def test_execute_failover_unknown(self):
        engine = self.RecoveryEngine()
        self.assertFalse(engine.execute_failover("unknown"))

    def test_reconcile_data(self):
        engine = self.RecoveryEngine()
        engine.create_plan("api", data_reconciliation_enabled=True)
        self.assertTrue(engine.reconcile_data("api"))

    def test_rebuild_infrastructure(self):
        engine = self.RecoveryEngine()
        engine.create_plan("api", iac_enabled=True, auto_rebuild=True, multi_zone=True, multi_region=True)
        state = engine.rebuild_infrastructure("api")
        self.assertEqual(state["status"], "completed")
        self.assertTrue(state["multi_zone"])
        self.assertTrue(state["multi_region"])

    def test_recover_secrets(self):
        engine = self.RecoveryEngine()
        engine.create_plan("api", secret_recovery_enabled=True)
        secrets = engine.recover_secrets("api")
        self.assertIsInstance(secrets, dict)

    def test_establish_alt_comms(self):
        engine = self.RecoveryEngine()
        engine.create_plan("api", alt_communication_channels=["slack", "matrix"])
        self.assertTrue(engine.establish_alt_comms("api"))

    def test_validate_recovery(self):
        engine = self.RecoveryEngine()
        engine.create_plan("api", failover_enabled=True, alt_communication_channels=["slack"])
        engine.execute_failover("api")
        engine.rebuild_infrastructure("api")
        engine.establish_alt_comms("api")
        result = engine.validate_recovery("api")
        self.assertTrue(result["valid"])

    def test_rollback(self):
        engine = self.RecoveryEngine()
        engine.create_plan("api")
        engine.execute_failover("api")
        engine.rebuild_infrastructure("api")
        self.assertTrue(engine.rollback("api"))
        self.assertIsNone(engine.get_plan("api").last_failover_at)

    def test_recovery_log(self):
        engine = self.RecoveryEngine()
        engine.create_plan("api")
        engine.execute_failover("api")
        log = engine.get_recovery_log()
        self.assertEqual(len(log), 1)


# ------------------------------------------------------------------
# Cyber recovery tests
# ------------------------------------------------------------------


class TestCyberRecoveryManager(unittest.TestCase):
    """Test cyber incident recovery manager."""

    def setUp(self):
        from enterprise.modules.disaster_recovery.cyber_recovery import CyberRecoveryManager, CyberRecoveryPhase, CyberRecoveryPlan
        self.CyberRecoveryManager = CyberRecoveryManager
        self.CyberRecoveryPhase = CyberRecoveryPhase
        self.CyberRecoveryPlan = CyberRecoveryPlan

    def test_initiate_recovery(self):
        mgr = self.CyberRecoveryManager()
        plan = mgr.initiate_recovery(metadata={"source": "soc"})
        self.assertIsNotNone(plan.incident_id)
        self.assertIn(self.CyberRecoveryPhase.DETECT, plan.phases_completed)

    def test_full_phase_sequence(self):
        mgr = self.CyberRecoveryManager()
        plan = mgr.initiate_recovery()

        # DETECT already done by initiate_recovery
        self.assertIn(self.CyberRecoveryPhase.DETECT, plan.phases_completed)

        # Advance through containment
        mgr.advance_phase(plan.incident_id, self.CyberRecoveryPhase.CONTAIN)
        mgr.advance_phase(plan.incident_id, self.CyberRecoveryPhase.ISOLATE)

        # Collect evidence
        evidence = mgr.collect_forensic_evidence(plan.incident_id, ["logs", "disk_image"])
        self.assertEqual(len(evidence), 2)
        self.assertIn(self.CyberRecoveryPhase.PRESERVE_EVIDENCE, plan.phases_completed)

        # Rotate credentials
        rotated = mgr.rotate_all_credentials(plan.incident_id, ["aws", "database", "github"])
        self.assertEqual(len(rotated), 3)

        # Identify clean point
        clean = mgr.identify_clean_recovery_point(plan.incident_id, ["snap1", "snap2", "snap3"])
        self.assertEqual(clean, "snap3")

        # Rebuild trusted
        self.assertTrue(mgr.rebuild_trusted_environment(plan.incident_id))

        # Validate
        self.assertTrue(mgr.validate_system_integrity(plan.incident_id))

        # Controlled restore
        self.assertTrue(mgr.perform_controlled_restore(plan.incident_id))

        # Monitor reinfection
        self.assertTrue(mgr.monitor_for_reinfection(plan.incident_id, duration_hours=48))

        # Generate report (also marks DOCUMENT phase)
        report = mgr.generate_incident_report(plan.incident_id)
        self.assertIn("CYBER INCIDENT RECOVERY REPORT", report)

        # Plan should be complete
        self.assertTrue(plan.is_complete)

    def test_rebuild_without_clean_point(self):
        mgr = self.CyberRecoveryManager()
        plan = mgr.initiate_recovery()
        self.assertFalse(mgr.rebuild_trusted_environment(plan.incident_id))

    def test_restore_without_validation(self):
        mgr = self.CyberRecoveryManager()
        plan = mgr.initiate_recovery()
        mgr.identify_clean_recovery_point(plan.incident_id, ["snap1"])
        mgr.rebuild_trusted_environment(plan.incident_id)
        # Skip validation
        self.assertFalse(mgr.perform_controlled_restore(plan.incident_id))

    def test_generate_report_unknown(self):
        mgr = self.CyberRecoveryManager()
        report = mgr.generate_incident_report("unknown")
        self.assertIn("No incident found", report)

    def test_current_phase(self):
        mgr = self.CyberRecoveryManager()
        plan = mgr.initiate_recovery()
        self.assertEqual(plan.current_phase, self.CyberRecoveryPhase.CONTAIN)


# ------------------------------------------------------------------
# AI Continuity tests
# ------------------------------------------------------------------


class TestAIContinuityManager(unittest.TestCase):
    """Test AI service continuity manager."""

    def setUp(self):
        from enterprise.modules.disaster_recovery.ai_continuity import AIContinuityManager, AIDisruptionType, AIContinuityPlan
        self.AIContinuityManager = AIContinuityManager
        self.AIDisruptionType = AIDisruptionType
        self.AIContinuityPlan = AIContinuityPlan

    def test_configure_plan(self):
        mgr = self.AIContinuityManager()
        plan = mgr.configure_plan(
            disruption_type=self.AIDisruptionType.MODEL_PROVIDER_OUTAGE,
            primary_provider="openai",
            fallback_providers=["anthropic", "together"],
            model_fallback_chain=["gpt-4o", "claude-sonnet", "llama-3"],
        )
        self.assertEqual(plan.primary_provider, "openai")
        self.assertEqual(len(plan.fallback_providers), 2)
        self.assertEqual(len(plan.model_fallback_chain), 3)

    def test_detect_disruption(self):
        mgr = self.AIContinuityManager()
        mgr.configure_plan(
            self.AIDisruptionType.MODEL_PROVIDER_OUTAGE, "openai",
            fallback_providers=["anthropic"],
        )
        self.assertTrue(mgr.detect_disruption(
            self.AIDisruptionType.MODEL_PROVIDER_OUTAGE,
            symptoms=["timeout", "503 errors"],
        ))
        self.assertTrue(mgr.is_disrupted(self.AIDisruptionType.MODEL_PROVIDER_OUTAGE))

    def test_detect_disruption_no_plan(self):
        mgr = self.AIContinuityManager()
        self.assertFalse(mgr.detect_disruption(self.AIDisruptionType.COST_SPIKE))

    def test_activate_fallback(self):
        mgr = self.AIContinuityManager()
        mgr.configure_plan(
            self.AIDisruptionType.MODEL_PROVIDER_OUTAGE, "openai",
            fallback_providers=["anthropic"],
        )
        mgr.detect_disruption(self.AIDisruptionType.MODEL_PROVIDER_OUTAGE)
        plan = mgr.activate_fallback(self.AIDisruptionType.MODEL_PROVIDER_OUTAGE)
        self.assertIsNotNone(plan)
        self.assertTrue(plan.is_active)

    def test_switch_model_provider(self):
        mgr = self.AIContinuityManager()
        mgr.configure_plan(
            self.AIDisruptionType.MODEL_PROVIDER_OUTAGE, "openai",
            fallback_providers=["anthropic"],
        )
        mgr.detect_disruption(self.AIDisruptionType.MODEL_PROVIDER_OUTAGE)
        self.assertTrue(mgr.switch_model_provider("anthropic", "claude-sonnet"))

    def test_restore_context_store(self):
        mgr = self.AIContinuityManager()
        self.assertTrue(mgr.restore_context_store("s3://backups/context"))

    def test_rebuild_vector_index(self):
        mgr = self.AIContinuityManager()
        self.assertTrue(mgr.rebuild_vector_index("pgvector_replica"))

    def test_verify_agent_health(self):
        mgr = self.AIContinuityManager()
        health = mgr.verify_agent_health("agent-001")
        self.assertTrue(health["healthy"])
        self.assertEqual(health["agent_id"], "agent-001")

    def test_reload_prompt_registry(self):
        mgr = self.AIContinuityManager()
        self.assertTrue(mgr.reload_prompt_registry("/backups/prompts.json"))

    def test_scale_inference_capacity(self):
        mgr = self.AIContinuityManager()
        self.assertTrue(mgr.scale_inference_capacity(factor=2.0))

    def test_check_cost_spike(self):
        mgr = self.AIContinuityManager()
        mgr.configure_plan(
            self.AIDisruptionType.COST_SPIKE, "openai", cost_threshold=500,
        )
        result = mgr.check_cost_spike(current_daily_cost=2000)
        self.assertTrue(result["spike_detected"])

    def test_apply_safety_override(self):
        mgr = self.AIContinuityManager()
        self.assertTrue(mgr.apply_safety_override({"strict_mode": True}))


# ------------------------------------------------------------------
# Crisis management tests
# ------------------------------------------------------------------


class TestCrisisManager(unittest.TestCase):
    """Test crisis management system."""

    def setUp(self):
        from enterprise.modules.disaster_recovery.crisis import CrisisManager, CrisisRole, CrisisSeverity, CrisisPlan, CrisisTeam
        self.CrisisManager = CrisisManager
        self.CrisisRole = CrisisRole
        self.CrisisSeverity = CrisisSeverity
        self.CrisisPlan = CrisisPlan
        self.CrisisTeam = CrisisTeam

    def test_declare_crisis(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(
            severity=self.CrisisSeverity.SEV_1_CRITICAL,
            commander="alice",
            customer_comms_process="status_page",
        )
        self.assertEqual(plan.severity, self.CrisisSeverity.SEV_1_CRITICAL)
        self.assertEqual(plan.commander, "alice")
        self.assertFalse(plan.is_resolved)

    def test_assign_roles(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_1_CRITICAL, "alice")
        self.assertTrue(mgr.assign_roles(plan.incident_id, {
            self.CrisisRole.TECHNICAL_LEAD: "bob",
            self.CrisisRole.SECURITY_LEAD: "carol",
            self.CrisisRole.COMMS_LEAD: "dave",
        }))
        self.assertTrue(plan.team.is_fully_staffed())

    def test_assign_roles_unknown_incident(self):
        mgr = self.CrisisManager()
        self.assertFalse(mgr.assign_roles("unknown", {self.CrisisRole.TECHNICAL_LEAD: "bob"}))

    def test_notify_customers(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_2_MAJOR, "alice")
        self.assertTrue(mgr.notify_customers(
            plan.incident_id,
            "We are investigating an outage.",
            channels=["email", "status_page"],
        ))
        self.assertIn("customers", plan.notifications_sent)

    def test_update_internal_stakeholders(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_2_MAJOR, "alice")
        self.assertTrue(mgr.update_internal_stakeholders(
            plan.incident_id, "Root cause identified; working on fix."
        ))

    def test_notify_regulators(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(
            self.CrisisSeverity.SEV_1_CRITICAL, "alice",
            regulator_notification_required=True,
        )
        self.assertTrue(mgr.notify_regulators(plan.incident_id))

    def test_notify_regulators_not_required(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_3_MINOR, "alice")
        self.assertTrue(mgr.notify_regulators(plan.incident_id))  # no-op success

    def test_escalate_to_vendor(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_1_CRITICAL, "alice")
        self.assertTrue(mgr.escalate_to_vendor(plan.incident_id, "aws", "Region outage"))
        self.assertEqual(len(plan.escalated_items), 1)

    def test_escalate_to_executive(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_1_CRITICAL, "alice")
        self.assertTrue(mgr.escalate_to_executive(plan.incident_id, "cto", "Revenue impact"))
        self.assertEqual(len(plan.escalated_items), 1)

    def test_close_crisis(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_2_MAJOR, "alice")
        self.assertTrue(mgr.close_crisis(plan.incident_id, "Fix deployed, monitoring confirms resolution."))
        self.assertTrue(plan.is_resolved)
        self.assertGreater(plan.duration_minutes, 0)

    def test_close_crisis_unknown(self):
        mgr = self.CrisisManager()
        self.assertFalse(mgr.close_crisis("unknown"))

    def test_get_crisis(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_1_CRITICAL, "alice")
        retrieved = mgr.get_crisis(plan.incident_id)
        self.assertEqual(retrieved.incident_id, plan.incident_id)

    def test_list_active_resolved(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_2_MAJOR, "alice")
        self.assertEqual(len(mgr.list_active()), 1)
        mgr.close_crisis(plan.incident_id)
        self.assertEqual(len(mgr.list_active()), 0)
        self.assertEqual(len(mgr.list_resolved()), 1)

    def test_track_resolution(self):
        mgr = self.CrisisManager()
        plan = mgr.declare_crisis(self.CrisisSeverity.SEV_2_MAJOR, "alice")
        self.assertTrue(mgr.track_resolution(plan.incident_id, "Applying hotfix."))
        self.assertGreater(len(plan.status_updates), 0)


# ------------------------------------------------------------------
# Exercise manager tests
# ------------------------------------------------------------------


class TestExerciseManager(unittest.TestCase):
    """Test DR exercise manager."""

    def setUp(self):
        from enterprise.modules.disaster_recovery.exercises import ExerciseManager, ExerciseType, Exercise
        self.ExerciseManager = ExerciseManager
        self.ExerciseType = ExerciseType
        self.Exercise = Exercise

    def test_schedule_exercise(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(
            exercise_type=self.ExerciseType.FAILOVER,
            scheduled_date=datetime.utcnow() + timedelta(days=7),
            participants=["alice", "bob"],
            objectives=["Test failover within RTO"],
        )
        self.assertEqual(ex.type, self.ExerciseType.FAILOVER)
        self.assertEqual(len(ex.participants), 2)
        self.assertFalse(ex.completed)

    def test_run_tabletop(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(self.ExerciseType.TABLETOP, datetime.utcnow())
        findings = mgr.run_tabletop(ex, moderator_notes=["Good discussion on escalation."])
        self.assertIn("Good discussion on escalation.", findings)
        self.assertTrue(ex.completed)
        self.assertTrue(ex.passed)

    def test_test_backup_restoration(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(self.ExerciseType.BACKUP_RESTORATION, datetime.utcnow())
        findings = mgr.test_backup_restoration(ex, backup_ids=["backup-1", "backup-2"])
        self.assertIn("Restored 2 backup(s)", findings[0])
        self.assertTrue(ex.completed)

    def test_test_failover(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(self.ExerciseType.FAILOVER, datetime.utcnow())
        findings = mgr.test_failover(ex, target_service="api")
        self.assertTrue(len(findings) > 0)
        self.assertTrue(ex.completed)

    def test_simulate_region_loss(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(self.ExerciseType.REGION_LOSS, datetime.utcnow())
        findings = mgr.simulate_region_loss(ex, region="us-east-1")
        self.assertTrue(len(findings) >= 2)
        self.assertTrue(ex.completed)

    def test_run_security_drill(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(self.ExerciseType.SECURITY_DRILL, datetime.utcnow())
        findings = mgr.run_security_drill(ex, drill_type="ransomware")
        self.assertTrue(len(findings) >= 2)
        self.assertTrue(ex.completed)

    def test_simulate_vendor_outage(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(self.ExerciseType.VENDOR_OUTAGE, datetime.utcnow())
        findings = mgr.simulate_vendor_outage(ex, vendor="openai")
        self.assertTrue(len(findings) >= 2)
        self.assertTrue(ex.completed)

    def test_simulate_key_person_loss(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(self.ExerciseType.KEY_PERSON_LOSS, datetime.utcnow())
        findings = mgr.simulate_key_person_loss(ex, role="CTO")
        self.assertTrue(len(findings) >= 2)
        self.assertTrue(ex.completed)

    def test_simulate_ai_outage(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(self.ExerciseType.AI_PROVIDER_OUTAGE, datetime.utcnow())
        findings = mgr.simulate_ai_outage(ex, provider="openai")
        self.assertTrue(len(findings) >= 2)
        self.assertTrue(ex.completed)

    def test_exercise_passed_failed(self):
        mgr = self.ExerciseManager()
        ex_pass = mgr.schedule_exercise(self.ExerciseType.FAILOVER, datetime.utcnow())
        mgr.test_failover(ex_pass)
        self.assertTrue(ex_pass.passed)

        ex_fail = mgr.schedule_exercise(self.ExerciseType.FAILOVER, datetime.utcnow())
        mgr._complete_exercise(ex_fail, ["FAIL: RTO exceeded", "Some services down"])
        self.assertFalse(ex_fail.passed)

    def test_generate_after_action_report(self):
        mgr = self.ExerciseManager()
        ex = mgr.schedule_exercise(self.ExerciseType.FAILOVER, datetime.utcnow())
        mgr.test_failover(ex)
        report = mgr.generate_after_action_report()
        self.assertIn("DISASTER RECOVERY AFTER-ACTION REPORT", report)
        self.assertIn("FAILOVER", report)
        self.assertIn("PASS", report)

    def test_list_exercises(self):
        mgr = self.ExerciseManager()
        mgr.schedule_exercise(self.ExerciseType.FAILOVER, datetime.utcnow())
        ex = mgr.schedule_exercise(self.ExerciseType.TABLETOP, datetime.utcnow() + timedelta(days=1))
        mgr.run_tabletop(ex)
        self.assertEqual(len(mgr.list_exercises()), 2)
        self.assertEqual(len(mgr.list_exercises(completed_only=True)), 1)


if __name__ == "__main__":
    unittest.main()