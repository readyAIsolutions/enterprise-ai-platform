"""
Privacy & Data Governance OS Module
====================================
Enterprise-grade privacy, data governance, security, and compliance module.

Modules:
  classifier  - Data classification engine (sensitivity, data type, PII detection)
  lifecycle   - Data lifecycle management (collection → deletion → audit)
  quality     - Data quality engine (8 dimensions, anomaly detection)
  privacy     - Privacy controls (consent, DSAR, retention, legal hold, residency)
  security    - Security controls (encryption, masking, tokenization, secrets, audit)
  compliance  - Compliance mapping (ISO 27001, SOC 2, NIST, GDPR, HIPAA, PCI DSS, CCPA)
  ai_data     - AI data governance (training data, RAG, embeddings, hallucination risk)
  monitoring  - Monitoring and alerting (access, leakage, drift, compliance, quality)
"""

__version__ = "1.0.0"
__author__ = "Eni Builder"
__all__ = [
    # Classifier
    "DataClassifier",
    "ClassificationResult",
    "ClassificationRule",
    "ClassificationConfidence",
    "DataType",
    "SensitivityLevel",
    "PII_PATTERNS",
    # Lifecycle
    "LifecycleManager",
    "DataAsset",
    "LifecycleStage",
    "StageStatus",
    "LifecyclePolicy",
    "LifecycleEvent",
    # Quality
    "QualityEngine",
    "QualityMetric",
    "QualityRule",
    "QualityDimension",
    "QualityStatus",
    "DataAnomaly",
    # Privacy
    "PrivacyManager",
    "ConsentRecord",
    "ConsentStatus",
    "PrivacyRequest",
    "PrivacyRequestType",
    "PrivacyRequestStatus",
    "RetentionRule",
    "RetentionPolicy",
    "LegalHold",
    "PurposeCategory",
    "DataResidency",
    # Security
    "EncryptionService",
    "KeyManager",
    "EncryptionKey",
    "EncryptionAlgorithm",
    "DataMasker",
    "MaskingStrategy",
    "TokenizationService",
    "TokenizationFormat",
    "AnonymizationService",
    "ImmutableAuditLog",
    "AuditEntry",
    "SecretsManager",
    "TransportSecurity",
    "TLSConfig",
    "SecurityContext",
    # Compliance
    "ComplianceMapper",
    "Framework",
    "ControlDomain",
    "ComplianceControl",
    "ControlAssessment",
    "FrameworkCompliance",
    "ComplianceReportGenerator",
    # AI Data
    "AIDataGovernor",
    "TrainingDataRecord",
    "EmbeddingVersion",
    "AIMemory",
    "RAGKnowledgeEntry",
    "SourceAttribution",
    "EmbeddingStatus",
    "MemoryStatus",
    "HallucinationRisk",
    "DataSourceQuality",
    "ValidationStatus",
    # Monitoring
    "PrivacyMonitor",
    "MonitorAlert",
    "AlertSeverity",
    "MonitorCategory",
    "MetricSnapshot",
    "AccessEvent",
    "MonitorRule",
]

# Convenience imports
from .classifier import (
    DataClassifier,
    ClassificationResult,
    ClassificationRule,
    ClassificationConfidence,
    DataType,
    SensitivityLevel,
    PII_PATTERNS,
)
from .lifecycle import (
    LifecycleManager,
    DataAsset,
    LifecycleStage,
    StageStatus,
    LifecyclePolicy,
    LifecycleEvent,
)
from .quality import (
    QualityEngine,
    QualityMetric,
    QualityRule,
    QualityDimension,
    QualityStatus,
    DataAnomaly,
)
from .privacy import (
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
from .security import (
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
)
from .compliance import (
    ComplianceMapper,
    Framework,
    ControlDomain,
    ComplianceControl,
    ControlAssessment,
    FrameworkCompliance,
    ComplianceReportGenerator,
)
from .ai_data import (
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
from .monitoring import (
    PrivacyMonitor,
    MonitorAlert,
    AlertSeverity,
    MonitorCategory,
    MetricSnapshot,
    AccessEvent,
    MonitorRule,
)