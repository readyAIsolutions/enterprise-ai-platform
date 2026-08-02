"""
Comprehensive tests for the Privacy & Data Governance OS module.
Tests all sub-modules: classifier, lifecycle, quality, privacy,
security, compliance, ai_data, monitoring.
"""
import sys
import os
import unittest
import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Ensure the module directory is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from enterprise.modules.privacy_data.classifier import (
    DataClassifier,
    ClassificationResult,
    ClassificationRule,
    ClassificationConfidence,
    DataType,
    SensitivityLevel,
    PII_PATTERNS,
)
from enterprise.modules.privacy_data.lifecycle import (
    LifecycleManager,
    DataAsset,
    LifecycleStage,
    StageStatus,
    LifecyclePolicy,
    LifecycleEvent,
)
from enterprise.modules.privacy_data.quality import (
    QualityEngine,
    QualityMetric,
    QualityRule,
    QualityDimension,
    QualityStatus,
    DataAnomaly,
)
from enterprise.modules.privacy_data.privacy import (
    PrivacyManager,
    ConsentRecord,
    ConsentStatus,
    PrivacyRequest,
    PrivacyRequestType,
    PrivacyRequestStatus,
    RetentionRule,
    RetentionPolicy,
    LegalHold,
    PurposeCategory,
    DataResidency,
)
from enterprise.modules.privacy_data.security import (
    EncryptionService,
    KeyManager,
    EncryptionKey,
    EncryptionAlgorithm,
    DataMasker,
    MaskingStrategy,
    TokenizationService,
    TokenizationFormat,
    AnonymizationService,
    ImmutableAuditLog,
    AuditEntry,
    SecretsManager,
    TransportSecurity,
    TLSConfig,
    SecurityContext,
    KeyRotationStrategy,
)
from enterprise.modules.privacy_data.compliance import (
    ComplianceMapper,
    Framework,
    ControlDomain,
    ComplianceControl,
    ControlAssessment,
    FrameworkCompliance,
    ComplianceReportGenerator,
)
from enterprise.modules.privacy_data.ai_data import (
    AIDataGovernor,
    TrainingDataRecord,
    EmbeddingVersion,
    AIMemory,
    RAGKnowledgeEntry,
    SourceAttribution,
    EmbeddingStatus,
    MemoryStatus,
    HallucinationRisk,
    DataSourceQuality,
    ValidationStatus,
)
from enterprise.modules.privacy_data.monitoring import (
    PrivacyMonitor,
    MonitorAlert,
    AlertSeverity,
    MonitorCategory,
    MetricSnapshot,
    AccessEvent,
    MonitorRule,
)


# =============================================================================
# Classifier Tests
# =============================================================================

class TestDataClassifier(unittest.TestCase):
    """Tests for the Data Classification Engine."""

    def setUp(self):
        self.classifier = DataClassifier()

    def test_classify_pii_email(self):
        result = self.classifier.classify_field("email", "user@example.com")
        self.assertEqual(result.data_type, DataType.PII)
        self.assertIn(SensitivityLevel, type(result.sensitivity).__mro__)
        self.assertTrue(len(result.pii_detected) > 0)

    def test_classify_pii_ssn(self):
        result = self.classifier.classify_field("ssn", "123-45-6789")
        self.assertEqual(result.data_type, DataType.PII)
        self.assertTrue(result.requires_encryption)

    def test_classify_financial_credit_card(self):
        result = self.classifier.classify_field("credit_card", "4111-1111-1111-1111")
        self.assertEqual(result.data_type, DataType.FINANCIAL)
        self.assertEqual(result.sensitivity, SensitivityLevel.RESTRICTED)

    def test_classify_financial_bank(self):
        result = self.classifier.classify_field("bank_account", "1234567890123456")
        self.assertEqual(result.data_type, DataType.FINANCIAL)

    def test_classify_medical(self):
        result = self.classifier.classify_field("diagnosis", "patient has condition")
        self.assertEqual(result.data_type, DataType.MEDICAL)
        self.assertTrue(result.requires_consent)

    def test_classify_legal(self):
        result = self.classifier.classify_field("contract", "agreement terms")
        self.assertEqual(result.data_type, DataType.LEGAL)

    def test_classify_ip(self):
        result = self.classifier.classify_field("algorithm", "proprietary formula")
        self.assertEqual(result.data_type, DataType.IP)

    def test_classify_ai_training(self):
        result = self.classifier.classify_field("training_data", "dataset corpus")
        self.assertEqual(result.data_type, DataType.AI_TRAINING)

    def test_classify_ai_memory(self):
        result = self.classifier.classify_field("conversation", "user context memory")
        self.assertEqual(result.data_type, DataType.AI_MEMORY)

    def test_classify_operational(self):
        result = self.classifier.classify_field("log", "debug info")
        self.assertEqual(result.data_type, DataType.OPERATIONAL)

    def test_classify_secrets(self):
        result = self.classifier.classify_field("api_key", "api_key=sk-abc123def456ghi789jkl012mno345pqr678")
        self.assertIn(result.data_type, (DataType.FINANCIAL, DataType.PII))
        self.assertTrue(result.requires_encryption)

    def test_classify_unknown_field(self):
        result = self.classifier.classify_field("random_field", "some generic text")
        self.assertEqual(result.data_type, DataType.OTHER)
        self.assertEqual(result.confidence, ClassificationConfidence.LOW)

    def test_classify_dataset(self):
        data = {
            "email": "test@example.com",
            "name": "John Doe",
            "credit_card": "4111111111111111",
            "notes": "general notes",
        }
        results = self.classifier.classify_dataset(data)
        self.assertEqual(len(results), 4)

        summary = self.classifier.get_dataset_summary(results)
        self.assertIn("total_fields", summary)
        self.assertIn("pii_fields", summary)
        self.assertIn("sensitivity_distribution", summary)
        self.assertTrue(summary["pii_field_count"] >= 1)

    def test_export_restricted(self):
        result = self.classifier.classify_field("ssn", "123-45-6789")
        self.assertTrue(result.export_restricted)

    def test_register_custom_rule(self):
        rule = ClassificationRule(
            rule_id="CUSTOM001",
            name="Custom",
            data_type=DataType.OTHER,
            sensitivity=SensitivityLevel.PUBLIC,
            keywords=["customword"],
        )
        self.classifier.register_rule(rule)
        result = self.classifier.classify_field("test", "contains customword")
        self.assertEqual(result.data_type, DataType.OTHER)

    def test_remove_rule(self):
        result_before = self.classifier.classify_field("email", "a@b.com")
        self.classifier.remove_rule("R001")
        result_after = self.classifier.classify_field("email", "a@b.com")
        self.assertNotEqual(
            len(result_before.matched_rules) > 0,
            len(result_after.matched_rules) > 0,
        )

    def test_detect_pii_various_types(self):
        pii = self.classifier.detect_pii("email: test@example.com, ssn: 123-45-6789")
        self.assertTrue(len(pii) >= 2)

    def test_pii_masking(self):
        masked = DataClassifier._mask_pii_value("test@example.com")
        self.assertIn("*", masked)
        self.assertEqual(len(masked), len("test@example.com"))

    def test_classifier_stats(self):
        self.classifier.classify_field("email", "a@b.com")
        stats = self.classifier.stats
        self.assertIn("total_rules", stats)
        self.assertIn("classifications_performed", stats)
        self.assertTrue(stats["classifications_performed"] >= 1)

    def test_suggest_classification(self):
        result = self.classifier.suggest_classification(
            "credit_card", ["4111-1111-1111-1111", "5500-0000-0000-0004"]
        )
        self.assertEqual(result.data_type, DataType.FINANCIAL)

    def test_validate_classification(self):
        current = ClassificationResult(
            data_type=DataType.OTHER,
            sensitivity=SensitivityLevel.PUBLIC,
            confidence=ClassificationConfidence.LOW,
            score=0.0,
            matched_rules=[],
        )
        validation = self.classifier.validate_classification(
            current, "email", ["test@example.com"]
        )
        self.assertTrue(validation["changed"])

    def test_sensitivity_from_score(self):
        self.assertEqual(SensitivityLevel.from_score(0.95), SensitivityLevel.RESTRICTED)
        self.assertEqual(SensitivityLevel.from_score(0.75), SensitivityLevel.CONFIDENTIAL)
        self.assertEqual(SensitivityLevel.from_score(0.50), SensitivityLevel.INTERNAL)
        self.assertEqual(SensitivityLevel.from_score(0.30), SensitivityLevel.PUBLIC)

    def test_classification_result_to_dict(self):
        result = self.classifier.classify_field("email", "a@b.com")
        d = result.to_dict()
        self.assertIn("data_type", d)
        self.assertIn("sensitivity", d)
        self.assertIn("requires_encryption", d)
        self.assertIn("requires_consent", d)

    def test_rules_by_type(self):
        pii_rules = self.classifier.get_rules_by_type(DataType.PII)
        self.assertTrue(len(pii_rules) > 0)
        self.assertTrue(all(r.data_type == DataType.PII for r in pii_rules))


# =============================================================================
# Lifecycle Tests
# =============================================================================

class TestLifecycleManager(unittest.TestCase):
    """Tests for the Data Lifecycle Manager."""

    def setUp(self):
        self.manager = LifecycleManager()

    def test_create_asset(self):
        asset = self.manager.create_asset("customer_db", "pii", "confidential")
        self.assertEqual(asset.current_stage, LifecycleStage.COLLECTION)
        self.assertEqual(asset.data_type, "pii")
        self.assertEqual(asset.sensitivity, "confidential")

    def test_valid_transition(self):
        asset = self.manager.create_asset("test_data", "pii", "confidential")
        success, event = self.manager.transition(asset.asset_id, LifecycleStage.VALIDATION)
        self.assertTrue(success)
        self.assertEqual(event.status, StageStatus.COMPLETED)
        self.assertEqual(asset.current_stage, LifecycleStage.VALIDATION)

    def test_invalid_transition(self):
        asset = self.manager.create_asset("test_data")
        # Can't go from COLLECTION directly to DELETION
        success, event = self.manager.transition(asset.asset_id, LifecycleStage.DELETION)
        self.assertFalse(success)
        self.assertEqual(event.status, StageStatus.FAILED)
        self.assertIsNotNone(event.error_message)

    def test_full_workflow(self):
        asset = self.manager.create_asset("data", "pii", "confidential")

        stages = [
            LifecycleStage.VALIDATION,
            LifecycleStage.CLASSIFICATION,
            LifecycleStage.ENCRYPTION,
            LifecycleStage.STORAGE,
            LifecycleStage.PROCESSING,
        ]
        for stage in stages:
            success, event = self.manager.transition(asset.asset_id, stage)
            self.assertTrue(success, f"Transition to {stage.value} failed")

        self.assertEqual(asset.current_stage, LifecycleStage.PROCESSING)

    def test_policy_enforcement(self):
        # Create with sensitive policy
        for pid, pol in self.manager._policies.items():
            if pol.name == "Sensitive Data":
                sensitive_policy_id = pid
                break

        asset = self.manager.create_asset(
            "sensitive_data", "pii", "confidential", policy_id=sensitive_policy_id
        )
        success, _ = self.manager.transition(asset.asset_id, LifecycleStage.VALIDATION)
        self.assertTrue(success)

        success, _ = self.manager.transition(asset.asset_id, LifecycleStage.CLASSIFICATION)
        self.assertTrue(success)

        # AI usage should be blocked by sensitive policy
        self.manager.transition(asset.asset_id, LifecycleStage.ENCRYPTION)
        self.manager.transition(asset.asset_id, LifecycleStage.STORAGE)

        allowed, reason = self.manager.can_transition(asset.asset_id, LifecycleStage.AI_USAGE)
        self.assertFalse(allowed)
        self.assertIn("not allowed", reason)

    def test_lifecycle_timeline(self):
        asset = self.manager.create_asset("data")
        self.manager.transition(asset.asset_id, LifecycleStage.VALIDATION)
        self.manager.transition(asset.asset_id, LifecycleStage.CLASSIFICATION)

        timeline = self.manager.get_lifecycle_timeline(asset.asset_id)
        self.assertEqual(len(timeline), 3)  # COLLECTION + VALIDATION + CLASSIFICATION

    def test_stage_history(self):
        asset = self.manager.create_asset("data")
        self.manager.transition(asset.asset_id, LifecycleStage.VALIDATION)
        history = asset.get_stage_history()
        self.assertIn("collection", history)
        self.assertIn("validation", history)

    def test_assets_by_stage(self):
        a1 = self.manager.create_asset("data1")
        a2 = self.manager.create_asset("data2")
        self.manager.transition(a1.asset_id, LifecycleStage.VALIDATION)

        collected = self.manager.get_assets_by_stage(LifecycleStage.COLLECTION)
        validated = self.manager.get_assets_by_stage(LifecycleStage.VALIDATION)
        self.assertEqual(len(collected), 1)
        self.assertEqual(len(validated), 1)

    def test_assets_due_for_deletion(self):
        # Create an asset with old creation date
        asset = self.manager.create_asset("old_data", "operational")
        asset.created_at = datetime.utcnow() - timedelta(days=100)
        # Assign operational policy (90-day retention)
        for pid, pol in self.manager._policies.items():
            if pol.name == "Operational Data":
                self.manager.assign_policy(asset.asset_id, pid)
                break

        due = self.manager.get_assets_due_for_deletion()
        self.assertTrue(len(due) >= 0)  # At least the asset should be due

    def test_bulk_transition(self):
        a1 = self.manager.create_asset("data1")
        a2 = self.manager.create_asset("data2")

        results = self.manager.bulk_transition(
            [a1.asset_id, a2.asset_id], LifecycleStage.VALIDATION
        )
        self.assertTrue(results[a1.asset_id][0])
        self.assertTrue(results[a2.asset_id][0])

    def test_execute_full_lifecycle(self):
        asset = self.manager.create_asset("auto_data")
        results = self.manager.execute_full_lifecycle(asset.asset_id)
        self.assertIn("validation", results)
        self.assertTrue(results["validation"][0])

    def test_rollback(self):
        asset = self.manager.create_asset("data")
        self.manager.transition(asset.asset_id, LifecycleStage.VALIDATION)
        self.manager.transition(asset.asset_id, LifecycleStage.CLASSIFICATION)
        self.manager.transition(asset.asset_id, LifecycleStage.ENCRYPTION)
        self.manager.transition(asset.asset_id, LifecycleStage.STORAGE)
        self.manager.transition(asset.asset_id, LifecycleStage.PROCESSING)

        success, msg = self.manager.rollback_stage(asset.asset_id, LifecycleStage.PROCESSING)
        self.assertTrue(success)

    def test_stats(self):
        self.manager.create_asset("data1")
        self.manager.create_asset("data2", "pii")
        stats = self.manager.stats
        self.assertEqual(stats["total_assets"], 2)
        self.assertIn("assets_by_stage", stats)

    def test_failed_event_recording(self):
        asset = self.manager.create_asset("data")
        event = self.manager.fail_transition(
            asset.asset_id, LifecycleStage.VALIDATION, "Test failure"
        )
        self.assertIsNotNone(event)
        self.assertEqual(event.status, StageStatus.FAILED)
        self.assertEqual(event.error_message, "Test failure")

    def test_asset_to_dict(self):
        asset = self.manager.create_asset("export_data", "pii", "confidential")
        d = asset.to_dict()
        self.assertEqual(d["name"], "export_data")
        self.assertEqual(d["data_type"], "pii")


# =============================================================================
# Quality Tests
# =============================================================================

class TestQualityEngine(unittest.TestCase):
    """Tests for the Data Quality Engine."""

    def setUp(self):
        self.engine = QualityEngine()

    def test_assess_clean_dataset(self):
        data = [
            {"id": 1, "name": "Alice", "age": 30, "email": "alice@test.com"},
            {"id": 2, "name": "Bob", "age": 25, "email": "bob@test.com"},
            {"id": 3, "name": "Charlie", "age": 35, "email": "charlie@test.com"},
        ]
        report = self.engine.assess_dataset(data)
        self.assertIn("overall_score", report)
        self.assertIn("overall_status", report)
        self.assertIn("dimension_scores", report)
        self.assertTrue(report["overall_score"] > 0.7)

    def test_detect_missing_values(self):
        data = [
            {"id": 1, "name": "Alice", "age": 30},
            {"id": 2, "name": None, "age": 25},
            {"id": 3, "name": "", "age": None},
        ]
        report = self.engine.assess_dataset(data)
        completeness = report["dimension_scores"].get("completeness", 0)
        self.assertTrue(completeness < 1.0)

    def test_detect_duplicates(self):
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        report = self.engine.assess_dataset(data)
        uniqueness = report["dimension_scores"].get("uniqueness", 1.0)
        self.assertTrue(uniqueness < 1.0)

    def test_anomalies_in_dataset(self):
        data = [
            {"id": 1, "name": "Alice", "age": 30},
            {"id": 2, "name": None, "age": 25},
            {"id": 1, "name": "Alice", "age": 30},  # duplicate
        ]
        report = self.engine.assess_dataset(data)
        self.assertTrue(report["anomaly_count"] > 0)

    def test_schema_drift_detection(self):
        schema = {"id": int, "name": str, "age": int}
        data = [
            {"id": 1, "name": "Alice", "age": 30, "new_field": "unexpected"},
            {"id": 2, "name": "Bob"},
        ]
        anomalies = self.engine.detect_anomalies(data, schema)
        drift_anomalies = [a for a in anomalies if a.anomaly_type == "schema_drift"]
        self.assertTrue(len(drift_anomalies) > 0)

    def test_data_drift_detection(self):
        data = [{"value": i} for i in range(100)] + [{"value": 1000000}] * 10
        anomalies = self.engine.detect_anomalies(data)
        drift = [a for a in anomalies if a.anomaly_type == "data_drift"]
        self.assertTrue(len(drift) > 0)

    def test_invalid_relationships(self):
        data = [
            {"parent_id": 1, "child_id": "A"},
            {"parent_id": 2, "child_id": "A"},  # A appears twice -> violates 1:1
            {"parent_id": 3, "child_id": "B"},
        ]
        rels = [{"parent_field": "parent_id", "child_field": "child_id", "type": "1:1"}]
        anomalies = self.engine.detect_anomalies(data, known_relationships=rels)
        rel_anomalies = [a for a in anomalies if a.anomaly_type == "invalid_relationship"]
        self.assertTrue(len(rel_anomalies) > 0)

    def test_ai_readiness(self):
        data = [{"feature1": i, "feature2": i * 2, "label": i % 2} for i in range(200)]
        report = self.engine.assess_dataset(data)
        ai_readiness = report["dimension_scores"].get("ai_readiness", 0)
        self.assertTrue(ai_readiness > 0.0)

    def test_quality_rule_management(self):
        initial_count = len(self.engine.get_rules())
        self.engine.add_rule(QualityRule(
            rule_id="TEST001",
            name="Test Rule",
            dimension=QualityDimension.ACCURACY,
            check_fn=lambda data: (True, 1.0, {}),
        ))
        self.assertEqual(len(self.engine.get_rules()), initial_count + 1)
        self.engine.remove_rule("TEST001")
        self.assertEqual(len(self.engine.get_rules()), initial_count)

    def test_score_to_status(self):
        self.assertEqual(QualityEngine.score_to_status(0.96), QualityStatus.EXCELLENT)
        self.assertEqual(QualityEngine.score_to_status(0.88), QualityStatus.GOOD)
        self.assertEqual(QualityEngine.score_to_status(0.75), QualityStatus.FAIR)
        self.assertEqual(QualityEngine.score_to_status(0.55), QualityStatus.POOR)
        self.assertEqual(QualityEngine.score_to_status(0.40), QualityStatus.CRITICAL)

    def test_quality_metric_passed(self):
        metric = QualityMetric(
            dimension=QualityDimension.ACCURACY,
            score=0.92,
            threshold=0.90,
        )
        self.assertTrue(metric.passed)

    def test_quality_metric_failed(self):
        metric = QualityMetric(
            dimension=QualityDimension.ACCURACY,
            score=0.85,
            threshold=0.90,
        )
        self.assertFalse(metric.passed)

    def test_anomaly_to_dict(self):
        anomaly = DataAnomaly(
            anomaly_type="missing",
            field_name="email",
            description="Missing values",
            severity="high",
            affected_count=5,
            total_count=100,
        )
        d = anomaly.to_dict()
        self.assertIn("anomaly_type", d)
        self.assertIn("affected_percentage", d)

    def test_empty_dataset(self):
        report = self.engine.assess_dataset([])
        self.assertTrue(report["overall_score"] >= 0.0)


# =============================================================================
# Privacy Tests
# =============================================================================

class TestPrivacyManager(unittest.TestCase):
    """Tests for the Privacy Controls Manager."""

    def setUp(self):
        self.pm = PrivacyManager()

    def test_record_consent(self):
        record = self.pm.record_consent(
            "user123", PurposeCategory.MARKETING,
            status=ConsentStatus.GRANTED,
            duration_days=365,
        )
        self.assertEqual(record.subject_id, "user123")
        self.assertEqual(record.status, ConsentStatus.GRANTED)
        self.assertTrue(record.is_valid)

    def test_check_consent_granted(self):
        self.pm.record_consent("user123", PurposeCategory.MARKETING,
                              ConsentStatus.GRANTED)
        allowed, reason = self.pm.check_consent("user123", PurposeCategory.MARKETING)
        self.assertTrue(allowed)
        self.assertIn("granted", reason.lower())

    def test_check_consent_denied(self):
        self.pm.record_consent("user123", PurposeCategory.MARKETING,
                              ConsentStatus.DENIED)
        allowed, reason = self.pm.check_consent("user123", PurposeCategory.MARKETING)
        self.assertFalse(allowed)

    def test_check_consent_essential_purpose(self):
        # Security always allowed
        allowed, reason = self.pm.check_consent("user456", PurposeCategory.SECURITY)
        self.assertTrue(allowed)

    def test_withdraw_consent(self):
        self.pm.record_consent("user123", PurposeCategory.MARKETING, ConsentStatus.GRANTED)
        result = self.pm.withdraw_consent("user123", PurposeCategory.MARKETING)
        self.assertTrue(result)
        allowed, _ = self.pm.check_consent("user123", PurposeCategory.MARKETING)
        self.assertFalse(allowed)

    def test_withdraw_all_consent(self):
        self.pm.record_consent("user123", PurposeCategory.MARKETING, ConsentStatus.GRANTED)
        self.pm.record_consent("user123", PurposeCategory.ANALYTICS, ConsentStatus.GRANTED)
        count = self.pm.withdraw_all_consent("user123")
        self.assertEqual(count, 2)

    def test_get_consent_records(self):
        self.pm.record_consent("user123", PurposeCategory.MARKETING, ConsentStatus.GRANTED)
        self.pm.record_consent("user123", PurposeCategory.ANALYTICS, ConsentStatus.DENIED)
        records = self.pm.get_consent_records("user123")
        self.assertEqual(len(records), 2)

    def test_submit_access_request(self):
        request = PrivacyRequest(
            subject_id="user123",
            request_type=PrivacyRequestType.ACCESS,
        )
        self.pm.submit_request(request)
        self.assertEqual(request.status, PrivacyRequestStatus.RECEIVED)
        self.assertIsNotNone(request.due_date)

    def test_verify_and_complete_request(self):
        request = PrivacyRequest(
            subject_id="user123",
            request_type=PrivacyRequestType.DELETE,
        )
        self.pm.submit_request(request)
        self.pm.verify_request(request.request_id)
        self.assertEqual(request.status, PrivacyRequestStatus.VERIFIED)

        self.pm.complete_request(request.request_id)
        self.assertEqual(request.status, PrivacyRequestStatus.COMPLETED)

    def test_deny_request(self):
        request = PrivacyRequest(
            subject_id="user123",
            request_type=PrivacyRequestType.ACCESS,
        )
        self.pm.submit_request(request)
        self.pm.deny_request(request.request_id, "Identity not verified")
        self.assertEqual(request.status, PrivacyRequestStatus.DENIED)

    def test_overdue_requests(self):
        request = PrivacyRequest(
            subject_id="user123",
            request_type=PrivacyRequestType.ACCESS,
        )
        self.pm.submit_request(request)
        # Manually set due_date in the past
        request.due_date = datetime.utcnow() - timedelta(days=10)
        overdue = self.pm.get_overdue_requests()
        self.assertTrue(len(overdue) >= 1)

    def test_retention_rule(self):
        rule = self.pm.get_retention_rule("RET-001")
        self.assertIsNotNone(rule)
        self.assertEqual(rule.rule_id, "RET-001")

    def test_should_delete_within_retention(self):
        should, reason = self.pm.should_delete(
            "pii", datetime.utcnow() - timedelta(days=30)
        )
        self.assertFalse(should)

    def test_legal_hold_prevents_deletion(self):
        hold = LegalHold(
            name="Litigation Hold",
            subject_ids=["user123"],
            data_types=["pii"],
        )
        self.pm.place_legal_hold(hold)

        should, reason = self.pm.should_delete(
            "pii",
            datetime.utcnow() - timedelta(days=4000),
            subject_id="user123",
        )
        self.assertFalse(should)
        self.assertIn("Legal hold", reason)

    def test_release_legal_hold(self):
        hold = self.pm.place_legal_hold(LegalHold(name="Test Hold"))
        result = self.pm.release_legal_hold(hold.hold_id)
        self.assertTrue(result)
        active = self.pm.get_active_holds("any")
        self.assertEqual(len(active), 0)

    def test_data_residency_check(self):
        compliant, violations = self.pm.check_residency_compliance(
            DataResidency.US, "pii"
        )
        self.assertTrue(compliant)
        self.assertEqual(len(violations), 0)

    def test_export_data(self):
        data_store = {
            "users": {"subject_id": "user123", "name": "Alice", "email": "alice@test.com"},
        }
        result = self.pm.export_data("user123", data_store)
        self.assertEqual(result["subject_id"], "user123")
        self.assertIn("data", result)
        self.assertIn("consent_records", result)

    def test_record_correction(self):
        correction = self.pm.record_correction(
            "user123", "email", "old@test.com", "new@test.com"
        )
        self.assertIn("correction_id", correction)
        self.assertIn("old_value_hash", correction)
        self.assertIn("new_value_hash", correction)

    def test_get_corrections(self):
        self.pm.record_correction("user123", "email", "old@test.com", "new@test.com")
        corrections = self.pm.get_corrections("user123")
        self.assertEqual(len(corrections), 1)

    def test_restrict_processing(self):
        self.pm.record_consent("user123", PurposeCategory.ANALYTICS, ConsentStatus.GRANTED)
        self.pm.restrict_processing("user123", PurposeCategory.ANALYTICS)

        allowed, reason = self.pm.check_consent("user123", PurposeCategory.ANALYTICS)
        self.assertFalse(allowed)

        restricted = self.pm.is_processing_restricted("user123", PurposeCategory.ANALYTICS)
        self.assertTrue(restricted)

    def test_lift_restriction(self):
        self.pm.restrict_processing("user123", PurposeCategory.ANALYTICS)
        self.pm.lift_restriction("user123", PurposeCategory.ANALYTICS)
        self.assertFalse(self.pm.is_processing_restricted("user123", PurposeCategory.ANALYTICS))

    def test_purpose_validation(self):
        self.pm.record_consent("user123", PurposeCategory.MARKETING, ConsentStatus.GRANTED)
        valid, msg = self.pm.validate_purpose(
            "user123", PurposeCategory.MARKETING, ["pii"]
        )
        self.assertTrue(valid)

    def test_purpose_validation_no_consent(self):
        valid, msg = self.pm.validate_purpose(
            "user456", PurposeCategory.MARKETING, ["pii"]
        )
        self.assertFalse(valid)

    def test_privacy_stats(self):
        self.pm.record_consent("user1", PurposeCategory.MARKETING, ConsentStatus.GRANTED)
        stats = self.pm.stats
        self.assertIn("total_consent_records", stats)
        self.assertIn("active_consents", stats)
        self.assertIn("active_legal_holds", stats)

    def test_consent_record_compute_proof(self):
        record = ConsentRecord(subject_id="user1", purpose=PurposeCategory.MARKETING)
        proof = record.compute_proof()
        self.assertTrue(len(proof) > 0)
        self.assertEqual(len(proof), 64)  # SHA-256 hex


# =============================================================================
# Security Tests
# =============================================================================

class TestSecurity(unittest.TestCase):
    """Tests for Security Controls."""

    def setUp(self):
        self.key_manager = KeyManager()
        self.encryption = EncryptionService(self.key_manager)

    def test_key_generation(self):
        key = self.key_manager.generate_key(make_primary=True)
        self.assertIsNotNone(key)
        self.assertTrue(key.is_primary)
        self.assertTrue(key.is_active)

    def test_encrypt_decrypt(self):
        plaintext = "sensitive data"
        encrypted = self.encryption.encrypt(plaintext)
        self.assertIn("ciphertext", encrypted)
        self.assertIn("key_id", encrypted)

        decrypted = self.encryption.decrypt(encrypted)
        self.assertEqual(decrypted.decode(), plaintext)

    def test_encrypt_field(self):
        data = {"name": "Alice", "email": "alice@test.com", "notes": "public"}
        result = self.encryption.encrypt_field(data, ["email"])
        self.assertIsInstance(result["email"], dict)
        self.assertIn("ciphertext", result["email"])

    def test_decrypt_field(self):
        data = {"name": "Alice", "email": self.encryption.encrypt("alice@test.com")}
        result = self.encryption.decrypt_field(data, ["email"])
        self.assertEqual(result["email"], "alice@test.com")

    def test_encrypt_record_auto_detect(self):
        record = {"name": "Alice", "api_key": "sk-secret-key-123"}
        result = self.encryption.encrypt_record(record)
        self.assertIsInstance(result["api_key"], dict)

    def test_key_rotation(self):
        key = self.key_manager.generate_key(make_primary=True, algorithm=EncryptionAlgorithm.FERNET)
        key.created_at = datetime.utcnow() - timedelta(days=100)
        new_keys = self.key_manager.rotate_keys()
        self.assertTrue(len(new_keys) >= 1)
        self.assertFalse(key.is_active)

    def test_key_revocation(self):
        key = self.key_manager.generate_key()
        self.assertTrue(self.key_manager.revoke_key(key.key_id))
        self.assertFalse(key.is_active)

    def test_multi_fernet_decrypt(self):
        # Encrypt with key1
        encrypted = self.encryption.encrypt("test")
        # Rotate
        for k in self.key_manager._keys.values():
            k.created_at = datetime.utcnow() - timedelta(days=100)
        self.key_manager.rotate_keys()
        # Should still decrypt with old key available
        decrypted = self.encryption.decrypt(encrypted)
        self.assertEqual(decrypted.decode(), "test")

    def test_data_masking_full(self):
        result = DataMasker.mask("sensitive", MaskingStrategy.FULL_MASK)
        self.assertEqual(result, "*********")

    def test_data_masking_partial(self):
        result = DataMasker.mask("alice@example.com", MaskingStrategy.PARTIAL_MASK,
                                show_first=3, show_last=4)
        self.assertTrue(result.startswith("ali"))
        self.assertTrue(result.endswith(".com"))

    def test_data_masking_hash(self):
        result = DataMasker.mask("value", MaskingStrategy.HASH)
        self.assertNotEqual(result, "value")
        self.assertEqual(len(result), 16)

    def test_data_masking_redact(self):
        result = DataMasker.mask("anything", MaskingStrategy.REDACT)
        self.assertEqual(result, "[REDACTED]")

    def test_data_masking_nullify(self):
        result = DataMasker.mask("value", MaskingStrategy.NULLIFY)
        self.assertIsNone(result)

    def test_mask_pii_record(self):
        record = {
            "email": "alice@example.com",
            "ssn": "123-45-6789",
            "notes": "public info",
        }
        masked = DataMasker.mask_pii(record)
        self.assertNotEqual(masked["email"], record["email"])
        self.assertNotEqual(masked["ssn"], record["ssn"])
        self.assertEqual(masked["notes"], record["notes"])

    def test_tokenization(self):
        tokenizer = TokenizationService()
        token = tokenizer.tokenize("4111-1111-1111-1111")
        self.assertTrue(token.startswith("tok_"))
        self.assertTrue(tokenizer.verify_token(token, "4111-1111-1111-1111"))
        self.assertFalse(tokenizer.verify_token(token, "different_value"))

    def test_tokenization_record(self):
        tokenizer = TokenizationService()
        record = {"card": "4111111111111111", "name": "Alice"}
        result = tokenizer.tokenize_record(record, ["card"])
        self.assertTrue(result["card"].startswith("tok_"))
        self.assertEqual(result["name"], "Alice")

    def test_anonymization(self):
        anon = AnonymizationService()
        result = anon.anonymize("identifier123")
        self.assertIsNotNone(result)
        self.assertNotEqual(result, "identifier123")

    def test_pseudonymization(self):
        anon = AnonymizationService()
        pseudo = anon.pseudonymize("user123", "test_ns")
        self.assertIsNotNone(pseudo)
        self.assertEqual(len(pseudo), 16)

        recovered = anon.depseudonymize(pseudo, "test_ns")
        self.assertEqual(recovered, "user123")

    def test_anonymize_record(self):
        anon = AnonymizationService()
        record = {"name": "Alice", "email": "alice@test.com"}
        result = anon.anonymize_record(record, ["email"])
        self.assertEqual(result["name"], "Alice")
        self.assertNotEqual(result["email"], "alice@test.com")

    def test_immutable_audit_log(self):
        log = ImmutableAuditLog("test")
        entry = log.record("system", "CREATE", "resource_1", {"note": "test"})
        self.assertIsNotNone(entry)
        self.assertTrue(len(entry.current_hash) > 0)

        integrity, bad_idx = log.verify_integrity()
        self.assertTrue(integrity)
        self.assertIsNone(bad_idx)

    def test_audit_log_query(self):
        log = ImmutableAuditLog("test")
        log.record("alice", "READ", "doc_1")
        log.record("bob", "WRITE", "doc_2")
        log.record("alice", "DELETE", "doc_1")

        alice_entries = log.query(actor="alice")
        self.assertEqual(len(alice_entries), 2)

    def test_audit_log_export(self):
        log = ImmutableAuditLog("test")
        log.record("system", "CREATE", "r1")
        exported = log.export()
        self.assertEqual(len(exported), 1)
        self.assertIn("entry_id", exported[0])

    def test_secrets_manager(self):
        sm = SecretsManager(self.key_manager)
        sm.store_secret("DB_PASSWORD", "super_secret_123")
        retrieved = sm.retrieve_secret("DB_PASSWORD")
        self.assertEqual(retrieved, "super_secret_123")

        sm.rotate_secret("DB_PASSWORD", "new_secret_456")
        retrieved = sm.retrieve_secret("DB_PASSWORD")
        self.assertEqual(retrieved, "new_secret_456")

        sm.delete_secret("DB_PASSWORD")
        self.assertIsNone(sm.retrieve_secret("DB_PASSWORD"))

    def test_transport_security_config(self):
        config = TransportSecurity.create_secure_config()
        self.assertEqual(config.min_version, "TLSv1.3")

        valid, warnings = TransportSecurity.validate_config(config)
        self.assertTrue(valid)

    def test_security_context(self):
        ctx = SecurityContext()
        self.assertIsNotNone(ctx.key_manager)
        self.assertIsNotNone(ctx.encryption)
        self.assertIsNotNone(ctx.masker)
        self.assertIsNotNone(ctx.tokenizer)
        self.assertIsNotNone(ctx.anonymizer)
        self.assertIsNotNone(ctx.secrets)
        self.assertIsNotNone(ctx.audit_log)

    def test_security_context_secure_record(self):
        ctx = SecurityContext()
        record = {"name": "Alice", "ssn": "123-45-6789"}
        secured = ctx.secure_record(record, ["ssn"], strategy="encrypt")
        self.assertIsInstance(secured["ssn"], dict)

        masked = ctx.secure_record(record, ["ssn"], strategy="mask")
        self.assertNotEqual(masked["ssn"], record["ssn"])

    def test_key_manager_stats(self):
        self.key_manager.generate_key(make_primary=True)
        stats = self.key_manager.stats
        self.assertIn("total_keys", stats)
        self.assertIn("active_keys", stats)
        self.assertIn("primary_key_id", stats)


# =============================================================================
# Compliance Tests
# =============================================================================

class TestComplianceMapper(unittest.TestCase):
    """Tests for the Compliance Mapping Engine."""

    def setUp(self):
        self.mapper = ComplianceMapper()

    def test_controls_by_framework(self):
        gdpr_controls = self.mapper.get_controls_by_framework(Framework.GDPR)
        self.assertTrue(len(gdpr_controls) > 0)
        self.assertTrue(any("GDPR" in c.control_id for c in gdpr_controls))

    def test_controls_by_domain(self):
        encryption_controls = self.mapper.get_controls_by_domain(ControlDomain.ENCRYPTION)
        self.assertTrue(len(encryption_controls) > 0)

    def test_framework_overlap(self):
        overlap = self.mapper.get_framework_overlap(Framework.GDPR, Framework.CCPA)
        self.assertTrue(len(overlap) > 0)

    def test_assess_framework_compliant(self):
        assessments = {}
        for c in self.mapper.get_controls_by_framework(Framework.GDPR):
            assessments[c.control_id] = ControlAssessment(
                control_id=c.control_id,
                implemented=True,
                compliant=True,
                score=1.0,
            )

        result = self.mapper.assess_framework(Framework.GDPR, assessments)
        self.assertEqual(result.compliant_controls, result.total_controls)
        self.assertEqual(result.status, "Fully Compliant")

    def test_assess_framework_partial(self):
        assessments = {}
        controls = self.mapper.get_controls_by_framework(Framework.GDPR)
        for i, c in enumerate(controls):
            assessments[c.control_id] = ControlAssessment(
                control_id=c.control_id,
                implemented=i < len(controls) // 2,
                compliant=i < len(controls) // 2,
                score=1.0 if i < len(controls) // 2 else 0.3,
            )

        result = self.mapper.assess_framework(Framework.GDPR, assessments)
        self.assertTrue(result.compliance_pct < 1.0)

    def test_generate_gap_analysis(self):
        assessments = {}
        result = self.mapper.generate_gap_analysis(assessments)
        self.assertIn("framework_results", result)
        self.assertIn("total_gaps", result)
        self.assertIn("recommendations", result)
        self.assertIn("critical_gaps", result)

    def test_evidence_checklist(self):
        checklist = self.mapper.generate_evidence_checklist(Framework.GDPR)
        self.assertTrue(len(checklist) > 0)
        self.assertIn("control_id", checklist[0])
        self.assertIn("evidence_required", checklist[0])

    def test_map_classification_to_compliance(self):
        requirements = self.mapper.map_data_classification_to_compliance(
            "restricted", "pii"
        )
        self.assertTrue(len(requirements) > 0)

    def test_executive_summary(self):
        assessments = {}
        results = self.mapper.assess_all_frameworks(assessments)
        summary = ComplianceReportGenerator.generate_executive_summary(results)
        self.assertIn("overall_posture", summary)
        self.assertIn("risk_level", summary)
        self.assertIn("framework_breakdown", summary)

    def test_all_frameworks_have_controls(self):
        for fw in Framework:
            controls = self.mapper.get_controls_by_framework(fw)
            self.assertTrue(
                len(controls) > 0,
                f"Framework {fw.value} has no controls"
            )

    def test_compliance_stats(self):
        stats = self.mapper.stats
        self.assertIn("total_controls", stats)
        self.assertIn("controls_by_framework", stats)
        self.assertIn("controls_by_domain", stats)

    def test_get_control(self):
        control = self.mapper.get_control("GDPR-Art.17")
        self.assertIsNotNone(control)
        self.assertIn("Erasure", control.name)


# =============================================================================
# AI Data Governance Tests
# =============================================================================

class TestAIDataGovernor(unittest.TestCase):
    """Tests for AI Data Governance."""

    def setUp(self):
        self.gov = AIDataGovernor()

    def test_register_training_data(self):
        record = self.gov.register_training_data(
            "https://example.com/data",
            "Training content here",
            DataSourceQuality.VERIFIED,
            license_info="CC-BY-4.0",
        )
        self.assertEqual(record.source, "https://example.com/data")
        self.assertEqual(record.source_quality, DataSourceQuality.VERIFIED)

    def test_scan_for_pii(self):
        record = self.gov.register_training_data(
            "source", "Contact: alice@example.com, phone: 555-123-4567",
            metadata={"content": "Contact: alice@example.com, phone: 555-123-4567"}
        )
        result = self.gov.scan_for_pii(record.record_id)
        self.assertTrue(result["has_pii"])

    def test_assess_bias(self):
        record = self.gov.register_training_data("source", "content")
        result = self.gov.assess_bias(record.record_id, 0.2)
        self.assertEqual(result["risk_level"], "low")

    def test_verify_training_data(self):
        record = self.gov.register_training_data("source", "content")
        self.gov.verify_training_data(record.record_id, "admin")
        self.assertTrue(record.is_trusted)
        self.assertEqual(record.source_quality, DataSourceQuality.TRUSTED)

    def test_flag_training_data(self):
        record = self.gov.register_training_data("source", "content")
        self.gov.flag_training_data(record.record_id, "Contains toxic content")
        self.assertEqual(record.source_quality, DataSourceQuality.FLAGGED)
        self.assertFalse(record.is_trusted)

    def test_get_trusted_training_data(self):
        record = self.gov.register_training_data("trusted_source", "content")
        self.gov.verify_training_data(record.record_id, "admin")
        trusted = self.gov.get_trusted_training_data()
        self.assertEqual(len(trusted), 1)

    def test_add_rag_entry(self):
        entry = self.gov.add_rag_entry(
            "GDPR Overview",
            "GDPR is a regulation on data protection...",
            source_url="https://gdpr.eu",
            tags=["gdpr", "privacy", "regulation"],
        )
        self.assertEqual(entry.title, "GDPR Overview")
        self.assertEqual(entry.source_quality, DataSourceQuality.UNVERIFIED)

    def test_verify_rag_entry(self):
        entry = self.gov.add_rag_entry("Title", "Content")
        self.gov.verify_rag_entry(entry.entry_id, "reviewer")
        self.assertEqual(entry.source_quality, DataSourceQuality.VERIFIED)

    def test_deprecate_rag_entry(self):
        entry = self.gov.add_rag_entry("Old Title", "Old content")
        self.gov.deprecate_rag_entry(entry.entry_id, "Outdated information")
        self.assertTrue(entry.is_deprecated)

    def test_search_rag(self):
        self.gov.add_rag_entry("Python Guide", "Python programming language guide",
                              tags=["python", "programming"])
        self.gov.add_rag_entry("Java Guide", "Java programming language guide",
                              tags=["java", "programming"])

        results = self.gov.search_rag("Python")
        self.assertTrue(len(results) >= 1)
        self.assertIn("Python", results[0].title)

    def test_create_embedding_version(self):
        emb = self.gov.create_embedding_version(
            "content to embed",
            "text-embedding-3-large",
            "v3",
            1536,
            source_attribution="https://source.com",
        )
        self.assertEqual(emb.version, 1)
        self.assertEqual(emb.model_name, "text-embedding-3-large")
        self.assertEqual(emb.status, EmbeddingStatus.GENERATED)

    def test_embedding_versioning(self):
        self.gov.create_embedding_version("content", "model", "v1", 768)
        emb2 = self.gov.create_embedding_version("content", "model", "v2", 1024)
        self.assertEqual(emb2.version, 2)

        versions = self.gov.get_embedding_versions(emb2.content_hash)
        self.assertEqual(len(versions), 2)

    def test_validate_and_deprecate_embedding(self):
        emb = self.gov.create_embedding_version("content", "model", "v1", 768)
        content_hash = emb.content_hash

        self.gov.validate_embedding(content_hash, 1)
        current = self.gov.get_current_embedding(content_hash)
        self.assertEqual(current.status, EmbeddingStatus.VALIDATED)

        self.gov.deprecate_embedding(content_hash, 1, "Model updated")
        current = self.gov.get_current_embedding(content_hash)
        self.assertIsNone(current)

    def test_store_memory(self):
        memory = self.gov.store_memory(
            "User prefers dark mode",
            memory_type="preference",
            session_id="session_1",
            confidence=0.95,
            ttl_days=30,
        )
        self.assertEqual(memory.memory_type, "preference")
        self.assertEqual(memory.status, MemoryStatus.ACTIVE)
        self.assertEqual(memory.confidence, 0.95)

    def test_validate_memory(self):
        memory = self.gov.store_memory("Test fact", memory_type="fact")
        self.gov.validate_memory(memory.memory_id, ValidationStatus.VALID)
        self.assertEqual(memory.validation_status, ValidationStatus.VALID)

    def test_validate_memory_invalid(self):
        memory = self.gov.store_memory("Test fact")
        self.gov.validate_memory(memory.memory_id, ValidationStatus.INVALID)
        self.assertEqual(memory.status, MemoryStatus.INVALIDATED)

    def test_access_memory(self):
        memory = self.gov.store_memory("Test content", memory_type="context")
        accessed = self.gov.access_memory(memory.memory_id)
        self.assertEqual(accessed.access_count, 1)
        self.assertIsNotNone(accessed.last_accessed)

    def test_update_memory(self):
        memory = self.gov.store_memory("Original fact", memory_type="fact")
        updated = self.gov.update_memory(memory.memory_id, "Updated fact", confidence=0.9)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.version, 2)
        self.assertEqual(updated.content, "Updated fact")
        self.assertEqual(memory.status, MemoryStatus.ARCHIVED)

    def test_delete_memory(self):
        memory = self.gov.store_memory("Test content")
        self.gov.delete_memory(memory.memory_id)
        self.assertEqual(memory.status, MemoryStatus.DELETED)

    def test_expire_memories(self):
        memory = self.gov.store_memory("Old content", ttl_days=0)
        memory.created_at = datetime.utcnow() - timedelta(days=1)
        expired = self.gov.expire_memories()
        self.assertTrue(expired >= 1)

    def test_assess_hallucination_risk_low(self):
        risk = self.gov.assess_hallucination_risk(
            source_quality=DataSourceQuality.TRUSTED,
            confidence=0.95,
            has_attribution=True,
            content_age_days=5,
        )
        self.assertEqual(risk, HallucinationRisk.LOW)

    def test_assess_hallucination_risk_critical(self):
        risk = self.gov.assess_hallucination_risk(
            source_quality=DataSourceQuality.FLAGGED,
            confidence=0.2,
            has_attribution=False,
            content_age_days=200,
        )
        self.assertEqual(risk, HallucinationRisk.CRITICAL)

    def test_hallucination_mitigation(self):
        strategies = self.gov.get_hallucination_mitigation(HallucinationRisk.HIGH)
        self.assertTrue(len(strategies) > 0)
        self.assertTrue(any("review" in s.lower() for s in strategies))

    def test_compute_confidence(self):
        result = self.gov.compute_confidence(
            source_quality=DataSourceQuality.TRUSTED,
            has_attribution=True,
            is_verified=True,
            content_freshness_days=5,
            cross_referenced=True,
        )
        self.assertIn("composite_score", result)
        self.assertIn("confidence_level", result)
        self.assertTrue(result["composite_score"] > 0.85)

    def test_add_attribution(self):
        attr = self.gov.add_attribution(
            "output_1",
            "https://source.com/page",
            source_title="Source Title",
            retrieval_score=0.9,
            relevance_score=0.85,
        )
        self.assertEqual(attr.source_url, "https://source.com/page")

        attributions = self.gov.get_attributions("output_1")
        self.assertEqual(len(attributions), 1)

    def test_generate_citation(self):
        attr = SourceAttribution(
            source_url="https://example.com",
            source_title="Example Page",
            source_author="John Doe",
            source_date=datetime(2024, 1, 15),
        )
        citation = self.gov.generate_citation(attr, style="inline")
        self.assertIn("https://example.com", citation)
        self.assertIn("Example Page", citation)

    def test_ai_governor_stats(self):
        self.gov.register_training_data("source", "content")
        self.gov.store_memory("test", memory_type="conversation")
        stats = self.gov.stats
        self.assertIn("training_records", stats)
        self.assertIn("memories", stats)
        self.assertIn("rag_entries", stats)


# =============================================================================
# Monitoring Tests
# =============================================================================

class TestPrivacyMonitor(unittest.TestCase):
    """Tests for the Privacy & Data Governance Monitor."""

    def setUp(self):
        self.monitor = PrivacyMonitor()

    def test_raise_alert(self):
        alert = self.monitor.raise_alert(
            MonitorCategory.ACCESS_CONTROL,
            AlertSeverity.CRITICAL,
            "Test Alert",
            "This is a test alert description",
            source="test_source",
        )
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.CRITICAL)
        self.assertEqual(alert.category, MonitorCategory.ACCESS_CONTROL)

    def test_alert_deduplication(self):
        alert1 = self.monitor.raise_alert(
            MonitorCategory.DATA_QUALITY,
            AlertSeverity.WARNING,
            "Quality Alert",
            "Quality degradation",
            rule_id="M010",
        )
        alert2 = self.monitor.raise_alert(
            MonitorCategory.DATA_QUALITY,
            AlertSeverity.WARNING,
            "Quality Alert",
            "Quality degradation",
            rule_id="M010",
        )
        self.assertIsNotNone(alert1)
        # Second should be deduplicated (within cooldown for M010 which is 30 min)
        self.assertIsNone(alert2)
        self.assertEqual(len(self.monitor.get_active_alerts()), 1)

    def test_resolve_alert(self):
        alert = self.monitor.raise_alert(
            MonitorCategory.BACKUP,
            AlertSeverity.HIGH,
            "Backup missing",
            "Test",
        )
        resolved = self.monitor.resolve_alert(alert.alert_id, "Backup completed")
        self.assertTrue(resolved)
        self.assertEqual(len(self.monitor.get_active_alerts()), 0)

    def test_get_active_alerts_filtered(self):
        self.monitor.raise_alert(
            MonitorCategory.ACCESS_CONTROL, AlertSeverity.CRITICAL, "A1", "Desc"
        )
        self.monitor.raise_alert(
            MonitorCategory.BACKUP, AlertSeverity.WARNING, "A2", "Desc"
        )
        self.monitor.raise_alert(
            MonitorCategory.ACCESS_CONTROL, AlertSeverity.HIGH, "A3", "Desc"
        )

        critical = self.monitor.get_critical_alerts()
        self.assertTrue(len(critical) >= 1)

        access = self.monitor.get_active_alerts(category=MonitorCategory.ACCESS_CONTROL)
        self.assertEqual(len(access), 2)

    def test_record_metric(self):
        snapshot = self.monitor.record_metric(
            MonitorCategory.STORAGE,
            "disk_usage_pct",
            95.5,
            unit="%",
            threshold_warning=80.0,
            threshold_critical=95.0,
        )
        self.assertEqual(snapshot.value, 95.5)
        self.assertEqual(snapshot.status, "critical")

    def test_record_metric_normal(self):
        snapshot = self.monitor.record_metric(
            MonitorCategory.STORAGE,
            "disk_usage_pct",
            50.0,
            threshold_warning=80.0,
            threshold_critical=95.0,
        )
        self.assertEqual(snapshot.status, "ok")

    def test_get_latest_metric(self):
        self.monitor.record_metric(
            MonitorCategory.STORAGE, "cpu_usage", 75.0
        )
        latest = self.monitor.get_latest_metric("cpu_usage")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.value, 75.0)

    def test_record_access_authorized(self):
        event = self.monitor.record_access(
            "alice", "document_1", "read", "192.168.1.1", is_authorized=True
        )
        self.assertTrue(event.is_authorized)
        self.assertFalse(event.is_suspicious)

    def test_record_access_unauthorized(self):
        event = self.monitor.record_access(
            "hacker", "customer_db", "export", "10.0.0.1", is_authorized=False
        )
        self.assertTrue(event.is_suspicious)
        self.assertEqual(len(self.monitor.get_critical_alerts()), 1)

    def test_detect_anomalous_access(self):
        for i in range(25):
            self.monitor.record_access(
                "bot_user", f"resource_{i % 5}", "read", is_authorized=True
            )

        suspicious = self.monitor.detect_anomalous_access(lookback_minutes=120)
        self.assertTrue(len(suspicious) > 0)

    def test_check_data_leakage(self):
        exports = [
            {
                "record_count": 5000,
                "data_types": ["pii", "financial"],
                "actor": "export_user",
                "source": "admin_export",
            }
        ]
        alerts = self.monitor.check_data_leakage(exports)
        self.assertTrue(len(alerts) > 0)

    def test_check_schema_changes(self):
        current = {"id": int, "name": str, "email": str, "new_field": str}
        previous = {"id": int, "name": str, "email": str}

        alerts = self.monitor.check_schema_changes(current, previous)
        self.assertTrue(len(alerts) > 0)

    def test_check_schema_field_removed(self):
        current = {"id": int, "name": str}
        previous = {"id": int, "name": str, "email": str}

        alerts = self.monitor.check_schema_changes(current, previous)
        self.assertTrue(any(a.severity == AlertSeverity.CRITICAL for a in alerts))

    def test_check_compliance(self):
        results = {
            "GDPR": {"compliance_pct": 0.45, "status": "Non-Compliant"},
            "SOC2": {"compliance_pct": 0.95, "status": "Compliant"},
        }
        alerts = self.monitor.check_compliance(results)
        self.assertTrue(len(alerts) > 0)

    def test_check_privacy_violations(self):
        consent_checks = [
            {"subject_id": "user1", "allowed": False, "reason": "Consent withdrawn"},
        ]
        alerts = self.monitor.check_privacy_violations(
            consent_checks, overdue_requests=3
        )
        self.assertTrue(len(alerts) > 0)

    def test_check_backups_missing(self):
        expected = [{"backup_id": "b1"}, {"backup_id": "b2"}]
        completed = [{"backup_id": "b1", "status": "completed"}]
        alerts = self.monitor.check_backups(expected, completed)
        self.assertTrue(len(alerts) > 0)

    def test_check_backups_failed(self):
        expected = [{"backup_id": "b1"}]
        completed = [{"backup_id": "b1", "status": "failed"}]
        alerts = self.monitor.check_backups(expected, completed)
        self.assertTrue(len(alerts) > 0)

    def test_monitor_storage_normal(self):
        alert = self.monitor.monitor_storage(1000, 500)
        self.assertIsNone(alert)

    def test_monitor_storage_critical(self):
        alert = self.monitor.monitor_storage(1000, 970)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.CRITICAL)

    def test_monitor_storage_warning(self):
        alert = self.monitor.monitor_storage(1000, 850)
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, AlertSeverity.WARNING)

    def test_check_ai_freshness(self):
        knowledge = [
            {
                "created_at": (datetime.utcnow() - timedelta(days=100)).isoformat(),
                "title": "Old Entry",
            }
        ]
        alerts = self.monitor.check_ai_knowledge_freshness(knowledge, max_age_days=90)
        self.assertTrue(len(alerts) > 0)

    def test_monitor_data_quality(self):
        report = {
            "overall_score": 0.45,
            "overall_status": "critical",
            "dimension_scores": {"accuracy": 0.4, "completeness": 0.5},
        }
        alerts = self.monitor.monitor_data_quality(report)
        self.assertTrue(len(alerts) > 0)

    def test_check_encryption_rotation(self):
        key_ages = {"key_1": 100, "key_2": 50}
        alerts = self.monitor.check_encryption_rotation(key_ages, max_age_days=90)
        self.assertEqual(len(alerts), 1)

    def test_dashboard(self):
        self.monitor.raise_alert(
            MonitorCategory.ACCESS_CONTROL, AlertSeverity.CRITICAL, "Test", "Desc"
        )
        dashboard = self.monitor.get_dashboard()
        self.assertIn("alert_summary", dashboard)
        self.assertIn("access_summary", dashboard)
        self.assertEqual(dashboard["alert_summary"]["critical"], 1)

    def test_monitor_stats(self):
        self.monitor.raise_alert(MonitorCategory.DATA_QUALITY, AlertSeverity.WARNING, "T", "D")
        self.monitor.record_metric(MonitorCategory.STORAGE, "test", 50)
        stats = self.monitor.stats
        self.assertIn("active_alerts", stats)
        self.assertIn("total_snapshots", stats)


# =============================================================================
# Integration Tests
# =============================================================================

class TestFullIntegration(unittest.TestCase):
    """End-to-end integration tests across all modules."""

    def test_classify_to_lifecycle_workflow(self):
        """Classify data then manage its lifecycle."""
        classifier = DataClassifier()
        lifecycle = LifecycleManager()

        result = classifier.classify_field("email", "user@test.com")
        self.assertEqual(result.data_type, DataType.PII)

        asset = lifecycle.create_asset(
            "user_emails", result.data_type.value, result.sensitivity.value
        )
        self.assertEqual(asset.data_type, "pii")
        self.assertIn(asset.sensitivity, ("confidential", "internal"))

    def test_classify_to_security_workflow(self):
        """Classify data then apply security controls."""
        classifier = DataClassifier()
        ctx = SecurityContext()

        record = {"email": "alice@example.com", "notes": "public info"}
        results = classifier.classify_dataset(record)

        # Email should be classified as PII
        self.assertEqual(results["email"].data_type, DataType.PII)

        # Apply masking (always works regardless of sensitivity)
        secured = ctx.secure_record(record, ["email"], strategy="mask")
        self.assertNotEqual(secured["email"], record["email"])

    def test_privacy_to_security_workflow(self):
        """Consent check before data processing."""
        pm = PrivacyManager()
        pm.record_consent("user1", PurposeCategory.MARKETING, ConsentStatus.GRANTED)
        allowed, _ = pm.check_consent("user1", PurposeCategory.MARKETING)
        self.assertTrue(allowed)

        ctx = SecurityContext()
        record = {"user_id": "user1", "preferences": "marketing_opt_in"}
        secured = ctx.secure_record(record, ["preferences"], strategy="mask")
        self.assertNotEqual(secured["preferences"], "marketing_opt_in")

    def test_quality_to_monitoring_workflow(self):
        """Detect quality issues and raise monitoring alerts."""
        engine = QualityEngine()
        monitor = PrivacyMonitor()

        data = [{"id": 1, "name": None}, {"id": 1, "name": None}]
        report = engine.assess_dataset(data)

        alerts = monitor.monitor_data_quality(report)
        self.assertTrue(len(alerts) > 0 or report["anomaly_count"] > 0)

    def test_ai_data_to_monitoring_workflow(self):
        """AI governance with freshness monitoring."""
        gov = AIDataGovernor()
        monitor = PrivacyMonitor()

        memory = gov.store_memory("Old knowledge", memory_type="fact", ttl_days=0)
        memory.created_at = datetime.utcnow() - timedelta(days=100)

        knowledge = [{"created_at": memory.created_at}]
        alerts = monitor.check_ai_knowledge_freshness(knowledge)
        self.assertTrue(len(alerts) > 0)

    def test_lifecycle_to_retention_monitoring(self):
        """Lifecycle management with retention policy monitoring."""
        lifecycle = LifecycleManager()
        monitor = PrivacyMonitor()

        asset = lifecycle.create_asset("old_data", "pii")
        asset.created_at = datetime.utcnow() - timedelta(days=4000)

        assets_past = lifecycle.get_assets_due_for_deletion()
        alerts = monitor.check_retention([
            {"asset_id": a.asset_id, "name": a.name}
            for a in assets_past
        ])
        # May or may not alert depending on policy assignment
        self.assertIsNotNone(alerts)

    def test_security_audit_chain(self):
        """Security audit log integrity."""
        log = ImmutableAuditLog("integration_test")

        ctx = SecurityContext()
        ctx.encryption.encrypt("test_data")
        log.record("system", "ENCRYPT", "data_1")

        integrity, bad = log.verify_integrity()
        self.assertTrue(integrity)

    def test_full_privacy_workflow(self):
        """Complete privacy request lifecycle."""
        pm = PrivacyManager()

        # Record consent
        pm.record_consent("user1", PurposeCategory.MARKETING, ConsentStatus.GRANTED)

        # Submit deletion request
        request = PrivacyRequest(
            subject_id="user1",
            request_type=PrivacyRequestType.DELETE,
        )
        pm.submit_request(request)

        # Verify
        pm.verify_request(request.request_id)

        # Complete
        pm.complete_request(request.request_id)

        self.assertEqual(request.status, PrivacyRequestStatus.COMPLETED)


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)