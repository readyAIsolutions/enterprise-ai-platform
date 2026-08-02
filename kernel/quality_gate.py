"""
ENI Enterprise Quality Gate Engine — Enforces deployment gates across all modules.
"""
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

class GateSeverity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class GateDefinition:
    id: str
    name: str
    description: str
    severity: GateSeverity
    module: str
    check_fn: str  # reference to checker
    required_evidence: List[str] = field(default_factory=list)
    timeout_seconds: int = 60

class QualityGateEngine:
    """Central quality gate enforcement for all modules."""
    
    GATES = {
        "security_tests": GateDefinition(
            id="QG-001", name="Security Tests Pass",
            description="All security tests must pass",
            severity=GateSeverity.CRITICAL, module="safety_governance",
            required_evidence=["test_results", "vulnerability_scan"]
        ),
        "ai_evaluations": GateDefinition(
            id="QG-002", name="AI Evaluations Pass",
            description="Hallucination rate, accuracy, safety checks",
            severity=GateSeverity.CRITICAL, module="safety_governance",
            required_evidence=["eval_report", "hallucination_rate", "bias_score"]
        ),
        "guardrails": GateDefinition(
            id="QG-003", name="Guardrails Pass",
            description="Prompt injection, jailbreak resistance verified",
            severity=GateSeverity.CRITICAL, module="safety_governance",
            required_evidence=["injection_test", "jailbreak_test"]
        ),
        "privacy_review": GateDefinition(
            id="QG-004", name="Privacy Review Pass",
            description="PII handling, data minimization verified",
            severity=GateSeverity.CRITICAL, module="privacy_data",
            required_evidence=["pii_scan", "data_flow_map"]
        ),
        "red_team": GateDefinition(
            id="QG-005", name="Red Team Testing Pass",
            description="Adversarial testing completed",
            severity=GateSeverity.HIGH, module="safety_governance",
            required_evidence=["red_team_report"]
        ),
        "monitoring_active": GateDefinition(
            id="QG-006", name="Monitoring Active",
            description="All monitoring systems operational",
            severity=GateSeverity.CRITICAL, module="safety_governance",
            required_evidence=["monitoring_status"]
        ),
        "rollback_plan": GateDefinition(
            id="QG-007", name="Rollback Plan Exists",
            description="Verified rollback procedure available",
            severity=GateSeverity.CRITICAL, module="release_change",
            required_evidence=["rollback_procedure", "rollback_test"]
        ),
        "data_quality": GateDefinition(
            id="QG-008", name="Data Quality Pass",
            description="Accuracy, completeness, freshness verified",
            severity=GateSeverity.CRITICAL, module="privacy_data",
            required_evidence=["quality_metrics"]
        ),
        "encryption": GateDefinition(
            id="QG-009", name="Encryption Verified",
            description="At-rest and in-transit encryption confirmed",
            severity=GateSeverity.CRITICAL, module="privacy_data",
            required_evidence=["encryption_scan"]
        ),
        "backups": GateDefinition(
            id="QG-010", name="Backups Verified",
            description="Backup integrity and restoration tested",
            severity=GateSeverity.CRITICAL, module="disaster_recovery",
            required_evidence=["backup_test", "restore_test"]
        ),
        "prompt_version": GateDefinition(
            id="QG-011", name="Prompt Version Valid",
            description="Prompt version is current and approved",
            severity=GateSeverity.MEDIUM, module="prompt_context",
            required_evidence=["version_check"]
        ),
        "context_conflicts": GateDefinition(
            id="QG-012", name="No Context Conflicts",
            description="No conflicting context detected",
            severity=GateSeverity.MEDIUM, module="prompt_context",
            required_evidence=["conflict_report"]
        ),
        "agent_verification": GateDefinition(
            id="QG-013", name="Agent Verification",
            description="All agent outputs independently verified",
            severity=GateSeverity.HIGH, module="agent_coordination",
            required_evidence=["verification_report"]
        ),
        "dependency_check": GateDefinition(
            id="QG-014", name="Dependencies Satisfied",
            description="All module dependencies met",
            severity=GateSeverity.CRITICAL, module="agent_coordination",
            required_evidence=["dependency_graph"]
        ),
        "knowledge_provenance": GateDefinition(
            id="QG-015", name="Knowledge Provenance",
            description="All critical facts have provenance",
            severity=GateSeverity.HIGH, module="knowledge_graph",
            required_evidence=["provenance_report"]
        ),
        "recovery_test": GateDefinition(
            id="QG-016", name="Recovery Tested",
            description="Disaster recovery procedure validated",
            severity=GateSeverity.CRITICAL, module="disaster_recovery",
            required_evidence=["recovery_test_log"]
        ),
        "change_record": GateDefinition(
            id="QG-017", name="Change Recorded",
            description="Change documented and approved",
            severity=GateSeverity.CRITICAL, module="release_change",
            required_evidence=["change_record", "approval"]
        ),
    }
    
    @classmethod
    def get_gate(cls, gate_id: str) -> Optional[GateDefinition]:
        return cls.GATES.get(gate_id)
    
    @classmethod
    def get_module_gates(cls, module_name: str) -> List[GateDefinition]:
        return [g for g in cls.GATES.values() if g.module == module_name]
    
    @classmethod
    def get_critical_gates(cls) -> List[GateDefinition]:
        return [g for g in cls.GATES.values() if g.severity == GateSeverity.CRITICAL]
    
    @classmethod
    def validate_evidence(cls, gate_id: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
        gate = cls.get_gate(gate_id)
        if not gate:
            return {"valid": False, "error": f"Unknown gate: {gate_id}"}
        missing = [e for e in gate.required_evidence if e not in evidence]
        return {
            "valid": len(missing) == 0,
            "gate": gate.name,
            "missing_evidence": missing,
            "provided_evidence": list(evidence.keys())
        }
    
    @classmethod
    def all_gate_summary(cls) -> Dict[str, List[str]]:
        return {
            "critical": [g.name for g in cls.GATES.values() if g.severity == GateSeverity.CRITICAL],
            "high": [g.name for g in cls.GATES.values() if g.severity == GateSeverity.HIGH],
            "medium": [g.name for g in cls.GATES.values() if g.severity == GateSeverity.MEDIUM],
        }