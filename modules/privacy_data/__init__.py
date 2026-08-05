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

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Kernel lifecycle registration -- makes this OS module discoverable by the
# ENI Platform Kernel for initialize/health_check/shutdown orchestration.
# --------------------------------------------------------------------------
import asyncio
import logging
import threading
from typing import Any, Dict, Optional

from enterprise.platform_kernel import HealthStatus, Module, module

_KERNEL_VERSION = globals().get("__version__", "1.0.0")

from .classifier import DataClassifier

_logger = logging.getLogger("enterprise.privacy_data")


@module(name="privacy_data", version=_KERNEL_VERSION)
class PrivacyDataModule(Module):
    """Kernel-managed wrapper around the privacy_data OS module.

    Wraps the most representative entrypoint (DataClassifier) so the platform kernel
    can initialize it, probe its health, and shut it down as part of the ENI
    lifecycle. If the core component cannot be instantiated the module reports
    UNHEALTHY rather than crashing the platform.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
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


def create_privacy_data_module(config: Optional[Dict[str, Any]] = None) -> PrivacyDataModule:
    """Factory: create a privacy_data module instance."""
    return PrivacyDataModule(config)
