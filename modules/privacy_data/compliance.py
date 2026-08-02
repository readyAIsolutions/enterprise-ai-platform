"""
Compliance Mapping Engine
Maps data governance controls to regulatory frameworks:
  ISO 27001, SOC 2, NIST CSF, GDPR, PIPEDA, HIPAA, PCI DSS, CCPA
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


# ─── Framework Definitions ────────────────────────────────────────────────────

class Framework(str, Enum):
    """Supported compliance frameworks."""
    ISO_27001 = "iso_27001"
    SOC2 = "soc_2"
    NIST_CSF = "nist_csf"
    GDPR = "gdpr"
    PIPEDA = "pipeda"
    HIPAA = "hipaa"
    PCI_DSS = "pci_dss"
    CCPA = "ccpa"


class ControlDomain(str, Enum):
    """Control domains/areas within compliance frameworks."""
    ACCESS_CONTROL = "access_control"
    DATA_CLASSIFICATION = "data_classification"
    ENCRYPTION = "encryption"
    DATA_RETENTION = "data_retention"
    DATA_DELETION = "data_deletion"
    AUDIT_LOGGING = "audit_logging"
    INCIDENT_RESPONSE = "incident_response"
    RISK_MANAGEMENT = "risk_management"
    THIRD_PARTY = "third_party"
    CONSENT = "consent"
    DATA_PORTABILITY = "data_portability"
    RIGHT_TO_ACCESS = "right_to_access"
    RIGHT_TO_DELETE = "right_to_delete"
    DATA_MINIMIZATION = "data_minimization"
    PURPOSE_LIMITATION = "purpose_limitation"
    BREACH_NOTIFICATION = "breach_notification"
    DATA_RESIDENCY = "data_residency"
    PRIVACY_BY_DESIGN = "privacy_by_design"
    SECURITY_TRAINING = "security_training"
    VULNERABILITY_MGMT = "vulnerability_management"
    ASSET_MANAGEMENT = "asset_management"
    BUSINESS_CONTINUITY = "business_continuity"
    CHANGE_MANAGEMENT = "change_management"
    MONITORING = "monitoring"
    AI_GOVERNANCE = "ai_governance"


# ─── Control Definition ───────────────────────────────────────────────────────

@dataclass
class ComplianceControl:
    """A specific compliance control requirement."""
    control_id: str
    name: str
    domain: ControlDomain
    description: str
    frameworks: List[Framework]
    implementation_guidance: str = ""
    evidence_required: List[str] = field(default_factory=list)
    test_procedure: str = ""
    is_mandatory: bool = True
    related_controls: List[str] = field(default_factory=list)


@dataclass
class ControlAssessment:
    """Assessment of a single control's implementation status."""
    control_id: str
    implemented: bool
    compliant: bool
    score: float  # 0.0 to 1.0
    findings: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    assessed_at: datetime = field(default_factory=datetime.utcnow)
    assessed_by: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id,
            "implemented": self.implemented,
            "compliant": self.compliant,
            "score": self.score,
            "findings": self.findings,
            "recommendations": self.recommendations,
            "evidence": self.evidence,
            "assessed_at": self.assessed_at.isoformat(),
            "assessed_by": self.assessed_by,
        }


# ─── Framework Compliance Status ──────────────────────────────────────────────

@dataclass
class FrameworkCompliance:
    """Overall compliance status for a framework."""
    framework: Framework
    total_controls: int
    compliant_controls: int
    partially_compliant: int
    non_compliant: int
    score: float
    gap_areas: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    @property
    def compliance_pct(self) -> float:
        if self.total_controls == 0:
            return 1.0
        return self.compliant_controls / self.total_controls

    @property
    def status(self) -> str:
        pct = self.compliance_pct
        if pct >= 0.95:
            return "Fully Compliant"
        elif pct >= 0.80:
            return "Mostly Compliant"
        elif pct >= 0.60:
            return "Partially Compliant"
        elif pct >= 0.40:
            return "Non-Compliant"
        return "Severely Non-Compliant"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "framework": self.framework.value,
            "total_controls": self.total_controls,
            "compliant_controls": self.compliant_controls,
            "partially_compliant": self.partially_compliant,
            "non_compliant": self.non_compliant,
            "score": round(self.score, 4),
            "compliance_pct": round(self.compliance_pct, 4),
            "status": self.status,
            "gap_areas": self.gap_areas,
            "recommendations": self.recommendations,
        }


# ─── Control Library ──────────────────────────────────────────────────────────

def _build_control_library() -> List[ComplianceControl]:
    """Build the complete compliance control library."""
    controls: List[ComplianceControl] = []

    # ── ISO 27001 Controls ────────────────────────────────────────────────
    controls.append(ComplianceControl(
        control_id="A.5.1.1",
        name="Information Security Policies",
        domain=ControlDomain.ACCESS_CONTROL,
        description="Policies for information security shall be defined, approved, published, and reviewed.",
        frameworks=[Framework.ISO_27001],
        implementation_guidance="Maintain documented security policies reviewed annually.",
        evidence_required=["Policy document", "Review records", "Approval records"],
    ))
    controls.append(ComplianceControl(
        control_id="A.8.2.1",
        name="Classification of Information",
        domain=ControlDomain.DATA_CLASSIFICATION,
        description="Information shall be classified in terms of legal requirements, value, criticality, and sensitivity.",
        frameworks=[Framework.ISO_27001, Framework.SOC2, Framework.NIST_CSF],
        implementation_guidance="Implement data classification scheme with Public, Internal, Confidential, Restricted levels.",
        evidence_required=["Classification policy", "Data inventory with classifications"],
    ))
    controls.append(ComplianceControl(
        control_id="A.10.1.1",
        name="Cryptographic Controls",
        domain=ControlDomain.ENCRYPTION,
        description="Policy on the use of cryptographic controls for protection of information.",
        frameworks=[Framework.ISO_27001, Framework.PCI_DSS, Framework.HIPAA],
        implementation_guidance="Use AES-256 for data at rest, TLS 1.3 for data in transit.",
        evidence_required=["Encryption policy", "Certificate inventory", "Key management procedures"],
    ))
    controls.append(ComplianceControl(
        control_id="A.12.3.1",
        name="Information Backup",
        domain=ControlDomain.BUSINESS_CONTINUITY,
        description="Backup copies of information, software, and system images shall be taken and tested regularly.",
        frameworks=[Framework.ISO_27001, Framework.SOC2, Framework.HIPAA],
        implementation_guidance="Implement automated daily backups with quarterly restore testing.",
        evidence_required=["Backup schedule", "Restore test results", "Retention policy"],
    ))
    controls.append(ComplianceControl(
        control_id="A.12.4.1",
        name="Event Logging",
        domain=ControlDomain.AUDIT_LOGGING,
        description="Event logs recording user activities, exceptions, faults, and security events shall be produced, kept, and regularly reviewed.",
        frameworks=[Framework.ISO_27001, Framework.SOC2, Framework.PCI_DSS],
        implementation_guidance="Centralized logging with SIEM integration, 90-day retention.",
        evidence_required=["Log configuration", "Log review reports", "SIEM alerts"],
    ))
    controls.append(ComplianceControl(
        control_id="A.16.1.1",
        name="Incident Management",
        domain=ControlDomain.INCIDENT_RESPONSE,
        description="Management responsibilities and procedures shall be established to ensure quick, effective response to security incidents.",
        frameworks=[Framework.ISO_27001, Framework.SOC2],
        implementation_guidance="Documented incident response plan with defined roles and escalation.",
        evidence_required=["IR plan", "Incident records", "Post-mortem reports"],
    ))

    # ── SOC 2 Controls ────────────────────────────────────────────────────
    controls.append(ComplianceControl(
        control_id="CC6.1",
        name="Logical and Physical Access Controls",
        domain=ControlDomain.ACCESS_CONTROL,
        description="Logical and physical access to information assets is restricted to authorized personnel.",
        frameworks=[Framework.SOC2, Framework.ISO_27001, Framework.HIPAA],
        implementation_guidance="RBAC, MFA, least privilege principle.",
        evidence_required=["Access control matrix", "MFA configuration", "Access review records"],
    ))
    controls.append(ComplianceControl(
        control_id="CC6.6",
        name="External Threats Protection",
        domain=ControlDomain.VULNERABILITY_MGMT,
        description="Systems protected against external threats including DDoS, malware, and unauthorized access.",
        frameworks=[Framework.SOC2, Framework.PCI_DSS],
        implementation_guidance="Firewall, WAF, IDS/IPS, regular pen testing.",
        evidence_required=["Firewall rules", "Vulnerability scan reports", "Penetration test results"],
    ))
    controls.append(ComplianceControl(
        control_id="CC7.3",
        name="Security Incident Detection",
        domain=ControlDomain.MONITORING,
        description="Security incidents are identified through monitoring and alerting mechanisms.",
        frameworks=[Framework.SOC2],
        implementation_guidance="24/7 monitoring with automated alerting on anomalies.",
        evidence_required=["Alert configurations", "Incident detection records", "Response times"],
    ))

    # ── NIST CSF Controls ─────────────────────────────────────────────────
    controls.append(ComplianceControl(
        control_id="ID.AM-1",
        name="Asset Inventory",
        domain=ControlDomain.ASSET_MANAGEMENT,
        description="Physical devices and systems are inventoried.",
        frameworks=[Framework.NIST_CSF, Framework.ISO_27001],
        implementation_guidance="Maintain CMDB with all data assets and systems.",
        evidence_required=["Asset inventory", "CMDB records"],
    ))
    controls.append(ComplianceControl(
        control_id="PR.DS-1",
        name="Data-at-Rest Protection",
        domain=ControlDomain.ENCRYPTION,
        description="Data-at-rest is protected.",
        frameworks=[Framework.NIST_CSF, Framework.PCI_DSS, Framework.HIPAA],
        implementation_guidance="Encrypt all stored data with strong ciphers (AES-256 minimum).",
        evidence_required=["Encryption configuration", "Key management system"],
    ))
    controls.append(ComplianceControl(
        control_id="PR.DS-2",
        name="Data-in-Transit Protection",
        domain=ControlDomain.ENCRYPTION,
        description="Data-in-transit is protected.",
        frameworks=[Framework.NIST_CSF, Framework.PCI_DSS],
        implementation_guidance="TLS 1.3 for all communications, mTLS for internal services.",
        evidence_required=["TLS certificates", "Network diagrams"],
    ))
    controls.append(ComplianceControl(
        control_id="DE.CM-1",
        name="Continuous Monitoring",
        domain=ControlDomain.MONITORING,
        description="The network is monitored to detect potential cybersecurity events.",
        frameworks=[Framework.NIST_CSF, Framework.SOC2],
        implementation_guidance="SIEM with correlation rules, anomaly detection.",
        evidence_required=["Monitoring dashboards", "Alert history"],
    ))

    # ── GDPR Controls ─────────────────────────────────────────────────────
    controls.append(ComplianceControl(
        control_id="GDPR-Art.5.1(c)",
        name="Data Minimization",
        domain=ControlDomain.DATA_MINIMIZATION,
        description="Personal data shall be adequate, relevant, and limited to what is necessary.",
        frameworks=[Framework.GDPR, Framework.CCPA],
        implementation_guidance="Only collect data fields that serve a defined business purpose.",
        evidence_required=["Data inventory", "Collection justification", "Field purpose mapping"],
    ))
    controls.append(ComplianceControl(
        control_id="GDPR-Art.5.1(b)",
        name="Purpose Limitation",
        domain=ControlDomain.PURPOSE_LIMITATION,
        description="Personal data shall be collected for specified, explicit, and legitimate purposes.",
        frameworks=[Framework.GDPR, Framework.PIPEDA],
        implementation_guidance="Document processing purposes, do not repurpose without new consent.",
        evidence_required=["Purpose statements", "Processing records", "DPIA"],
    ))
    controls.append(ComplianceControl(
        control_id="GDPR-Art.7",
        name="Consent Management",
        domain=ControlDomain.CONSENT,
        description="Consent must be freely given, specific, informed, and unambiguous.",
        frameworks=[Framework.GDPR, Framework.CCPA, Framework.PIPEDA],
        implementation_guidance="Implement granular consent management with clear opt-in/out mechanisms.",
        evidence_required=["Consent records", "Consent UI screenshots", "Withdrawal mechanism"],
    ))
    controls.append(ComplianceControl(
        control_id="GDPR-Art.15",
        name="Right of Access",
        domain=ControlDomain.RIGHT_TO_ACCESS,
        description="Data subjects shall have the right to access their personal data.",
        frameworks=[Framework.GDPR, Framework.CCPA, Framework.PIPEDA],
        implementation_guidance="Provide self-service data export or automated request handling.",
        evidence_required=["Access request procedures", "Data export templates", "Request logs"],
    ))
    controls.append(ComplianceControl(
        control_id="GDPR-Art.17",
        name="Right to Erasure",
        domain=ControlDomain.RIGHT_TO_DELETE,
        description="Data subjects shall have the right to request deletion of their personal data.",
        frameworks=[Framework.GDPR, Framework.CCPA],
        implementation_guidance="Implement cascading hard-delete with audit trail and retention exceptions.",
        evidence_required=["Deletion procedures", "Deletion logs", "Retention exception records"],
    ))
    controls.append(ComplianceControl(
        control_id="GDPR-Art.20",
        name="Data Portability",
        domain=ControlDomain.DATA_PORTABILITY,
        description="Data subjects have the right to receive their data in a machine-readable format.",
        frameworks=[Framework.GDPR, Framework.CCPA],
        implementation_guidance="Support JSON, CSV export with complete personal data records.",
        evidence_required=["Export endpoints", "Format specifications", "Portability test results"],
    ))
    controls.append(ComplianceControl(
        control_id="GDPR-Art.33",
        name="Breach Notification",
        domain=ControlDomain.BREACH_NOTIFICATION,
        description="Notify supervisory authority within 72 hours of breach discovery.",
        frameworks=[Framework.GDPR, Framework.PIPEDA],
        implementation_guidance="Automated breach detection with notification workflow.",
        evidence_required=["Breach notification template", "Response procedures", "Timeliness records"],
    ))
    controls.append(ComplianceControl(
        control_id="GDPR-Art.44-49",
        name="International Data Transfers",
        domain=ControlDomain.DATA_RESIDENCY,
        description="Restrictions on transfer of personal data to third countries.",
        frameworks=[Framework.GDPR],
        implementation_guidance="Implement SCCs, BCRs, or adequacy decisions for cross-border transfers.",
        evidence_required=["Transfer impact assessment", "SCC documentation", "Data flow maps"],
    ))

    # ─── HIPAA Controls ───────────────────────────────────────────────────
    controls.append(ComplianceControl(
        control_id="HIPAA-164.312(a)(1)",
        name="Access Control - Unique User ID",
        domain=ControlDomain.ACCESS_CONTROL,
        description="Assign a unique name/number for identifying and tracking user identity.",
        frameworks=[Framework.HIPAA],
        implementation_guidance="Unique user IDs, no shared accounts, SSO with identity provider.",
        evidence_required=["User directory", "SSO configuration", "Access audit logs"],
    ))
    controls.append(ComplianceControl(
        control_id="HIPAA-164.312(a)(2)(iv)",
        name="Encryption and Decryption",
        domain=ControlDomain.ENCRYPTION,
        description="Implement a mechanism to encrypt and decrypt electronic PHI.",
        frameworks=[Framework.HIPAA],
        implementation_guidance="Encrypt ePHI at rest and in transit. Key escrow for recovery.",
        evidence_required=["Encryption configuration", "Key management", "PHI data flow map"],
    ))
    controls.append(ComplianceControl(
        control_id="HIPAA-164.312(b)",
        name="Audit Controls",
        domain=ControlDomain.AUDIT_LOGGING,
        description="Implement hardware, software, and/or procedural mechanisms to record and examine activity in systems containing ePHI.",
        frameworks=[Framework.HIPAA],
        implementation_guidance="Tamper-proof audit logs with ePHI access tracking.",
        evidence_required=["Audit log configuration", "Review schedule", "Access reports"],
    ))
    controls.append(ComplianceControl(
        control_id="HIPAA-164.310(d)(1)",
        name="Data Retention - Device/Media Controls",
        domain=ControlDomain.DATA_DELETION,
        description="Implement procedures for final disposition of ePHI and the hardware/electronic media.",
        frameworks=[Framework.HIPAA],
        implementation_guidance="Secure deletion with NIST 800-88 compliance, media sanitization.",
        evidence_required=["Disposal procedures", "Sanitization certificates", "Disposal logs"],
    ))

    # ─── PCI DSS Controls ─────────────────────────────────────────────────
    controls.append(ComplianceControl(
        control_id="PCI-DSS-3.4",
        name="Render PAN Unreadable",
        domain=ControlDomain.ENCRYPTION,
        description="Render PAN unreadable anywhere it is stored using strong cryptography.",
        frameworks=[Framework.PCI_DSS],
        implementation_guidance="Tokenization or truncation for stored PANs, never store CVV.",
        evidence_required=["Tokenization configuration", "PAN scanning results", "Encryption setup"],
    ))
    controls.append(ComplianceControl(
        control_id="PCI-DSS-7.1",
        name="Limit Access by Need-to-Know",
        domain=ControlDomain.ACCESS_CONTROL,
        description="Limit access to cardholder data by business need-to-know.",
        frameworks=[Framework.PCI_DSS],
        implementation_guidance="RBAC per PCI role definitions, quarterly access reviews.",
        evidence_required=["Access control matrix", "Quarterly review records", "Role definitions"],
    ))
    controls.append(ComplianceControl(
        control_id="PCI-DSS-10.2",
        name="Automated Audit Trails",
        domain=ControlDomain.AUDIT_LOGGING,
        description="Implement automated audit trails for all access to cardholder data.",
        frameworks=[Framework.PCI_DSS],
        implementation_guidance="Immutable logs, centralized collection, tamper detection.",
        evidence_required=["Log configuration", "Log integrity checks", "Retention policy"],
    ))

    # ─── CCPA Controls ────────────────────────────────────────────────────
    controls.append(ComplianceControl(
        control_id="CCPA-1798.100",
        name="Right to Know",
        domain=ControlDomain.RIGHT_TO_ACCESS,
        description="Consumers have the right to know what personal information is collected.",
        frameworks=[Framework.CCPA],
        implementation_guidance="Provide data disclosure portal with collected categories and sources.",
        evidence_required=["Disclosure portal", "Data mapping", "Response templates"],
    ))
    controls.append(ComplianceControl(
        control_id="CCPA-1798.105",
        name="Right to Delete",
        domain=ControlDomain.RIGHT_TO_DELETE,
        description="Consumers have the right to request deletion of personal information.",
        frameworks=[Framework.CCPA],
        implementation_guidance="Automated deletion workflow with service provider notification.",
        evidence_required=["Deletion workflow", "Service provider notification records"],
    ))
    controls.append(ComplianceControl(
        control_id="CCPA-1798.120",
        name="Right to Opt-Out of Sale",
        domain=ControlDomain.CONSENT,
        description="Consumers have the right to opt-out of the sale of personal information.",
        frameworks=[Framework.CCPA],
        implementation_guidance="Clear 'Do Not Sell My Info' link, opt-out preference signal support.",
        evidence_required=["Opt-out mechanism", "Preference records", "Third-party data sharing records"],
    ))

    # ─── PIPEDA Controls ──────────────────────────────────────────────────
    controls.append(ComplianceControl(
        control_id="PIPEDA-Sch1-4.3",
        name="Consent",
        domain=ControlDomain.CONSENT,
        description="Knowledge and consent of the individual required for collection, use, or disclosure.",
        frameworks=[Framework.PIPEDA],
        implementation_guidance="Obtain meaningful consent with clear language and purpose.",
        evidence_required=["Consent forms", "Purpose statements", "Consent records"],
    ))
    controls.append(ComplianceControl(
        control_id="PIPEDA-Sch1-4.5",
        name="Limiting Use, Disclosure, and Retention",
        domain=ControlDomain.DATA_RETENTION,
        description="Personal information shall not be used or disclosed for purposes other than those for which it was collected.",
        frameworks=[Framework.PIPEDA],
        implementation_guidance="Retention schedules, purpose-based access controls.",
        evidence_required=["Retention policy", "Access enforcement records"],
    ))

    # ─── AI Governance ────────────────────────────────────────────────────
    controls.append(ComplianceControl(
        control_id="AI-GOV-001",
        name="AI Training Data Governance",
        domain=ControlDomain.AI_GOVERNANCE,
        description="Training data must be reviewed for bias, toxicity, PII leakage, and provenance.",
        frameworks=[Framework.GDPR, Framework.NIST_CSF],
        implementation_guidance="Implement data provenance tracking, bias audits, PII scanning on training data.",
        evidence_required=["Training data audit reports", "Bias assessment", "PII scan results"],
    ))
    controls.append(ComplianceControl(
        control_id="AI-GOV-002",
        name="AI Memory Governance",
        domain=ControlDomain.AI_GOVERNANCE,
        description="AI agent memory must be controllable, deletable, and subject to data subject rights.",
        frameworks=[Framework.GDPR, Framework.CCPA],
        implementation_guidance="Implement memory deletion, expiration, user-facing controls.",
        evidence_required=["Memory management controls", "Deletion logs", "Expiration policies"],
    ))

    return controls


# ─── Compliance Mapper ────────────────────────────────────────────────────────

class ComplianceMapper:
    """
    Enterprise compliance mapping engine.

    Maps controls to frameworks, assesses compliance posture,
    and generates gap analyses.

    Usage:
        mapper = ComplianceMapper()
        status = mapper.assess_framework(Framework.GDPR, control_assessments)
        gap_report = mapper.generate_gap_analysis(assessments)
    """

    def __init__(self, custom_controls: Optional[List[ComplianceControl]] = None):
        self._controls: Dict[str, ComplianceControl] = {}
        for c in _build_control_library():
            self._controls[c.control_id] = c
        if custom_controls:
            for c in custom_controls:
                self._controls[c.control_id] = c

    # ── Control Query ─────────────────────────────────────────────────────

    def get_controls_by_framework(self, framework: Framework) -> List[ComplianceControl]:
        """Get all controls for a specific framework."""
        return [c for c in self._controls.values() if framework in c.frameworks]

    def get_controls_by_domain(self, domain: ControlDomain) -> List[ComplianceControl]:
        """Get all controls for a specific domain."""
        return [c for c in self._controls.values() if c.domain == domain]

    def get_control(self, control_id: str) -> Optional[ComplianceControl]:
        """Get a specific control by ID."""
        return self._controls.get(control_id)

    def get_all_controls(self) -> List[ComplianceControl]:
        return list(self._controls.values())

    def get_framework_overlap(
        self, fw_a: Framework, fw_b: Framework
    ) -> List[ComplianceControl]:
        """Find controls shared between two frameworks."""
        return [
            c for c in self._controls.values()
            if fw_a in c.frameworks and fw_b in c.frameworks
        ]

    # ── Assessment ────────────────────────────────────────────────────────

    def assess_framework(
        self,
        framework: Framework,
        assessments: Dict[str, ControlAssessment],
    ) -> FrameworkCompliance:
        """Assess overall compliance for a framework."""
        controls = self.get_controls_by_framework(framework)
        if not controls:
            return FrameworkCompliance(
                framework=framework,
                total_controls=0,
                compliant_controls=0,
                partially_compliant=0,
                non_compliant=0,
                score=0.0,
            )

        total = len(controls)
        compliant = 0
        partial = 0
        non_compliant = 0
        gaps: List[str] = []
        recommendations: List[str] = []

        total_score = 0.0
        assessed_count = 0

        for control in controls:
            if control.control_id in assessments:
                assessment = assessments[control.control_id]
                total_score += assessment.score
                assessed_count += 1

                if assessment.score >= 0.90:
                    compliant += 1
                elif assessment.score >= 0.60:
                    partial += 1
                    gaps.append(f"{control.control_id}: {control.name} — partially implemented")
                    recommendations.extend(assessment.recommendations)
                else:
                    non_compliant += 1
                    gaps.append(f"{control.control_id}: {control.name} — not implemented")
                    recommendations.extend(assessment.recommendations)
            else:
                non_compliant += 1
                gaps.append(f"{control.control_id}: {control.name} — no assessment available")
                recommendations.append(f"Assess and implement control {control.control_id}")

        score = total_score / max(assessed_count, 1) if assessed_count > 0 else 0.0

        return FrameworkCompliance(
            framework=framework,
            total_controls=total,
            compliant_controls=compliant,
            partially_compliant=partial,
            non_compliant=non_compliant,
            score=round(score, 4),
            gap_areas=list(set(gaps)),
            recommendations=list(set(recommendations))[:10],
        )

    def assess_all_frameworks(
        self,
        assessments: Dict[str, ControlAssessment],
    ) -> Dict[Framework, FrameworkCompliance]:
        """Assess compliance across all frameworks."""
        results: Dict[Framework, FrameworkCompliance] = {}
        for framework in Framework:
            results[framework] = self.assess_framework(framework, assessments)
        return results

    def generate_gap_analysis(
        self,
        assessments: Dict[str, ControlAssessment],
    ) -> Dict[str, Any]:
        """Generate comprehensive gap analysis across all frameworks."""
        framework_results = self.assess_all_frameworks(assessments)

        all_gaps: List[Dict[str, Any]] = []
        all_recommendations: List[str] = []

        for fw, result in framework_results.items():
            for gap in result.gap_areas:
                all_gaps.append({
                    "framework": fw.value,
                    "gap": gap,
                })
            all_recommendations.extend(result.recommendations)

        # Identify critical gaps (controls shared across 3+ frameworks that are failing)
        critical_gaps = []
        for control in self._controls.values():
            framework_count = len(control.frameworks)
            if framework_count >= 3:
                assessment = assessments.get(control.control_id)
                if assessment and assessment.score < 0.60:
                    critical_gaps.append({
                        "control_id": control.control_id,
                        "name": control.name,
                        "frameworks": [f.value for f in control.frameworks],
                        "framework_count": framework_count,
                        "score": assessment.score,
                    })

        return {
            "framework_results": {fw.value: r.to_dict() for fw, r in framework_results.items()},
            "total_gaps": len(all_gaps),
            "gaps": all_gaps[:50],
            "recommendations": list(set(all_recommendations))[:20],
            "critical_gaps": critical_gaps,
            "highest_risk_frameworks": [
                fw.value for fw, r in framework_results.items()
                if r.compliance_pct < 0.80
            ],
            "generated_at": datetime.utcnow().isoformat(),
        }

    def map_data_classification_to_compliance(
        self,
        sensitivity: str,
        data_type: str,
    ) -> List[Dict[str, Any]]:
        """Map a data classification to applicable compliance requirements."""
        requirements: List[Dict[str, Any]] = []

        mapping = {
            "restricted": [
                (Framework.PCI_DSS, "Encryption required for restricted data"),
                (Framework.GDPR, "Special category data handling required"),
                (Framework.HIPAA, "ePHI protection required"),
            ],
            "confidential": [
                (Framework.GDPR, "Personal data processing rules apply"),
                (Framework.SOC2, "Confidential data controls required"),
                (Framework.ISO_27001, "Information classification controls apply"),
            ],
            "internal": [
                (Framework.ISO_27001, "Internal data handling policy"),
                (Framework.SOC2, "Access control considerations"),
            ],
            "public": [
                (Framework.ISO_27001, "Minimal controls"),
            ],
        }

        type_mapping = {
            "pii": [(Framework.GDPR, "PII handling"), (Framework.CCPA, "PII disclosure")],
            "financial": [(Framework.PCI_DSS, "Financial data protection")],
            "medical": [(Framework.HIPAA, "PHI protections")],
            "legal": [(Framework.GDPR, "Legal hold considerations")],
            "ai_memory": [(Framework.GDPR, "AI data subject rights")],
        }

        for fw, req in mapping.get(sensitivity.lower(), []):
            requirements.append({
                "framework": fw.value,
                "requirement": req,
                "trigger": f"Sensitivity: {sensitivity}",
            })

        for fw, req in type_mapping.get(data_type.lower(), []):
            requirements.append({
                "framework": fw.value,
                "requirement": req,
                "trigger": f"Data type: {data_type}",
            })

        return requirements

    def generate_evidence_checklist(
        self, framework: Framework
    ) -> List[Dict[str, Any]]:
        """Generate evidence collection checklist for a framework audit."""
        controls = self.get_controls_by_framework(framework)
        checklist: List[Dict[str, Any]] = []
        for c in controls:
            checklist.append({
                "control_id": c.control_id,
                "name": c.name,
                "evidence_required": c.evidence_required,
                "test_procedure": c.test_procedure or "Review evidence artifacts",
                "implementation_guidance": c.implementation_guidance,
            })
        return checklist

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "total_controls": len(self._controls),
            "controls_by_framework": {
                fw.value: len(self.get_controls_by_framework(fw))
                for fw in Framework
            },
            "controls_by_domain": {
                d.value: len(self.get_controls_by_domain(d))
                for d in ControlDomain
            },
        }


# ─── Compliance Report Generator ──────────────────────────────────────────────

class ComplianceReportGenerator:
    """Generate formatted compliance reports."""

    @staticmethod
    def generate_executive_summary(
        framework_results: Dict[Framework, FrameworkCompliance],
    ) -> Dict[str, Any]:
        """Generate executive summary of compliance posture."""
        total_compliant = sum(r.compliant_controls for r in framework_results.values())
        total_partial = sum(r.partially_compliant for r in framework_results.values())
        total_non = sum(r.non_compliant for r in framework_results.values())
        grand_total = total_compliant + total_partial + total_non

        overall_pct = total_compliant / max(grand_total, 1)

        if overall_pct >= 0.95:
            posture = "Strong"
            risk_level = "Low"
        elif overall_pct >= 0.80:
            posture = "Adequate"
            risk_level = "Medium"
        elif overall_pct >= 0.60:
            posture = "Needs Improvement"
            risk_level = "High"
        else:
            posture = "Critical"
            risk_level = "Critical"

        return {
            "overall_posture": posture,
            "risk_level": risk_level,
            "overall_compliance_pct": round(overall_pct, 4),
            "total_controls_assessed": grand_total,
            "compliant": total_compliant,
            "partially_compliant": total_partial,
            "non_compliant": total_non,
            "framework_breakdown": {
                fw.value: {
                    "compliance_pct": r.compliance_pct,
                    "status": r.status,
                    "gaps": r.gap_areas[:5],
                }
                for fw, r in framework_results.items()
            },
            "generated_at": datetime.utcnow().isoformat(),
        }