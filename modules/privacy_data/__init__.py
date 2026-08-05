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
    # Masking / Tokenization engine
    "MaskType",
    "Masker",
    "EmailMasker",
    "PhoneMasker",
    "SsnMasker",
    "CreditCardMasker",
    "NameMasker",
    "GenericMasker",
    "MaskingPolicy",
    "Vault",
    "InMemoryVault",
    "SQLiteVault",
    "TokenizationEngine",
    "MASKER_REGISTRY",
    "PolicyDataMasker",
]

# Convenience imports
from . import masking
from .ai_data import (
    AIDataGovernor,
    AIMemory,
    DataSourceQuality,
    EmbeddingStatus,
    EmbeddingVersion,
    HallucinationRisk,
    MemoryStatus,
    RAGKnowledgeEntry,
    SourceAttribution,
    TrainingDataRecord,
    ValidationStatus,
)
from .classifier import (
    PII_PATTERNS,
    ClassificationConfidence,
    ClassificationResult,
    ClassificationRule,
    DataClassifier,
    DataType,
    SensitivityLevel,
)
from .compliance import (
    ComplianceControl,
    ComplianceMapper,
    ComplianceReportGenerator,
    ControlAssessment,
    ControlDomain,
    Framework,
    FrameworkCompliance,
)
from .lifecycle import (
    DataAsset,
    LifecycleEvent,
    LifecycleManager,
    LifecyclePolicy,
    LifecycleStage,
    StageStatus,
)
from .masking import (
    MASKER_REGISTRY,
    CreditCardMasker,
    EmailMasker,
    GenericMasker,
    InMemoryVault,
    Masker,
    MaskingPolicy,
    MaskType,
    NameMasker,
    PhoneMasker,
    SQLiteVault,
    SsnMasker,
    TokenizationEngine,
    Vault,
)
from .monitoring import (
    AccessEvent,
    AlertSeverity,
    MetricSnapshot,
    MonitorAlert,
    MonitorCategory,
    MonitorRule,
    PrivacyMonitor,
)
from .privacy import (
    ConsentRecord,
    ConsentStatus,
    DataResidency,
    LegalHold,
    PrivacyManager,
    PrivacyRequest,
    PrivacyRequestStatus,
    PrivacyRequestType,
    PurposeCategory,
    RetentionPolicy,
    RetentionRule,
)
from .quality import (
    DataAnomaly,
    QualityDimension,
    QualityEngine,
    QualityMetric,
    QualityRule,
    QualityStatus,
)
from .security import (
    AnonymizationService,
    AuditEntry,
    DataMasker,
    EncryptionAlgorithm,
    EncryptionKey,
    EncryptionService,
    ImmutableAuditLog,
    KeyManager,
    MaskingStrategy,
    SecretsManager,
    SecurityContext,
    TLSConfig,
    TokenizationFormat,
    TokenizationService,
    TransportSecurity,
)

# The masker facade is exposed under an unambiguous alias to keep the
# pre-existing security.DataMasker (strategy-based masker) export intact.
PolicyDataMasker = masking.DataMasker


# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Kernel lifecycle registration -- makes this OS module discoverable by the
# ENI Platform Kernel for initialize/health_check/shutdown orchestration.
# --------------------------------------------------------------------------
import asyncio  # noqa: F401
import logging
import threading
from typing import Any, Dict, Optional  # noqa: F401

from enterprise.platform_kernel import HealthStatus, Module, module

_KERNEL_VERSION = globals().get("__version__", "1.0.0")


_logger = logging.getLogger("enterprise.privacy_data")


@module(name="privacy_data", version=_KERNEL_VERSION)
class PrivacyDataModule(Module):
    """Kernel-managed wrapper around the privacy_data OS module.

    Wraps the most representative entrypoint (DataClassifier) so the platform kernel
    can initialize it, probe its health, and shut it down as part of the ENI
    lifecycle. If the core component cannot be instantiated the module reports
    UNHEALTHY rather than crashing the platform.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._lock = threading.RLock()
        self._component = None
        self._init_error = None

    async def initialize(self) -> None:
        with self._lock:
            self._status = HealthStatus.STARTING
            try:
                self._component = DataClassifier()
                self._status = HealthStatus.HEALTHY
                _logger.info("%s module initialized", self.name)
            except Exception as e:  # pragma: no cover - degrade gracefully
                self._init_error = str(e)
                self._status = HealthStatus.UNHEALTHY
                _logger.warning("%s module failed to initialize: %s", self.name, e)

    async def health_check(self) -> HealthStatus:
        with self._lock:
            if self._component is None:
                return HealthStatus.UNHEALTHY if self._init_error else HealthStatus.DEGRADED
            try:
                self._component.classify_field("email", "user@example.com")
                return HealthStatus.HEALTHY
            except Exception as e:  # pragma: no cover
                _logger.warning("%s health probe failed: %s", self.name, e)
                return HealthStatus.DEGRADED

    async def shutdown(self) -> None:
        with self._lock:
            self._status = HealthStatus.STOPPING
            self._component = None
            self._init_error = None


def create_privacy_data_module(config: dict[str, Any] | None = None) -> PrivacyDataModule:
    """Factory: create a privacy_data module instance."""
    return PrivacyDataModule(config)
