"""
ENI Module Registry — Describes each OS module's inputs, outputs, dependencies, 
permissions, and activation conditions.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

@dataclass
class ModuleSpec:
    id: str
    name: str
    version: str
    description: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    activation_conditions: List[str] = field(default_factory=list)
    quality_gates: List[str] = field(default_factory=list)
    blocking: bool = False
    agents: List[str] = field(default_factory=list)

class ModuleRegistry:
    """Complete registry of all ENI enterprise OS modules."""
    
    MODULES = {
        "safety_governance": ModuleSpec(
            id="M-001", name="AI Safety & Governance OS", version="1.0.0",
            description="Safety, security, guardrails, red-teaming, monitoring for all AI operations",
            inputs=["project_context", "ai_system_spec", "deployment_config"],
            outputs=["risk_assessment", "guardrail_spec", "eval_report", "red_team_report",
                     "monitoring_dashboard", "incident_response_plan"],
            dependencies=[],
            permissions=["audit_read", "security_write", "monitoring_admin"],
            activation_conditions=["any_ai_deployment", "model_change", "prompt_change"],
            quality_gates=["QG-001", "QG-002", "QG-003", "QG-005", "QG-006"],
            blocking=True, agents=["security", "compliance"]
        ),
        "privacy_data": ModuleSpec(
            id="M-002", name="Privacy & Data Governance OS", version="1.0.0",
            description="Data lifecycle management, classification, encryption, compliance",
            inputs=["data_sources", "data_flows", "compliance_requirements"],
            outputs=["data_architecture", "classification_matrix", "privacy_assessment",
                     "encryption_policy", "backup_strategy", "compliance_report"],
            dependencies=[],
            permissions=["data_read", "data_classify", "audit_write"],
            activation_conditions=["new_data_source", "pii_processing", "compliance_change"],
            quality_gates=["QG-004", "QG-008", "QG-009"],
            blocking=True, agents=["data_engineer", "compliance"]
        ),
        "prompt_context": ModuleSpec(
            id="M-003", name="Prompt & Context Management OS", version="1.0.0",
            description="Prompt registry, versioning, token optimization, context management",
            inputs=["system_prompts", "user_prompts", "memory_sources", "rag_sources"],
            outputs=["optimized_prompt", "context_package", "token_budget", "eval_report"],
            dependencies=["knowledge_graph"],
            permissions=["prompt_read", "prompt_write", "context_manage"],
            activation_conditions=["any_ai_request", "prompt_change", "model_switch"],
            quality_gates=["QG-011", "QG-012"],
            blocking=False, agents=["ai_engineer"]
        ),
        "agent_coordination": ModuleSpec(
            id="M-004", name="Agent Communication & Coordination OS", version="1.0.0",
            description="Multi-agent orchestration, task scheduling, shared knowledge, conflict resolution",
            inputs=["project_objective", "agent_definitions", "task_graph"],
            outputs=["task_assignments", "communication_log", "integration_report",
                     "decision_log", "lessons_learned"],
            dependencies=["kernel"],
            permissions=["orchestrate", "task_assign", "agent_manage"],
            activation_conditions=["multi_agent_task", "complex_project"],
            quality_gates=["QG-013", "QG-014"],
            blocking=True, agents=["executive", "product_manager", "architect"]
        ),
        "knowledge_graph": ModuleSpec(
            id="M-005", name="Knowledge Graph OS", version="1.0.0",
            description="Structured knowledge network — entities, relationships, provenance, retrieval",
            inputs=["documents", "code", "decisions", "requirements", "apis"],
            outputs=["entity_catalog", "relationship_catalog", "provenance_model",
                     "retrieval_plan", "graph_quality_report"],
            dependencies=[],
            permissions=["graph_read", "graph_write", "entity_manage"],
            activation_conditions=["knowledge_intensive_task", "dependency_analysis"],
            quality_gates=["QG-015"],
            blocking=False, agents=["data_engineer", "ai_engineer"]
        ),
        "developer_experience": ModuleSpec(
            id="M-006", name="Developer Experience OS", version="1.0.0",
            description="Golden paths, platform, documentation, AI coding agent rules",
            inputs=["repository_standards", "platform_capabilities", "developer_feedback"],
            outputs=["dx_strategy", "golden_paths", "repository_templates",
                     "onboarding_guide", "ai_coding_policy"],
            dependencies=["knowledge_graph"],
            permissions=["dev_read", "dev_write", "platform_manage"],
            activation_conditions=["new_project", "new_developer", "tool_change"],
            quality_gates=[],
            blocking=False, agents=["backend", "frontend", "docs"]
        ),
        "innovation_rd": ModuleSpec(
            id="M-007", name="Innovation, Research & Development OS", version="1.0.0",
            description="Research pipeline, experiments, IP, technology scouting",
            inputs=["research_area", "technology_landscape", "business_goals"],
            outputs=["research_brief", "experiment_plan", "benchmark_report",
                     "ip_assessment", "innovation_roadmap"],
            dependencies=[],
            permissions=["research_read", "experiment_create", "ip_classify"],
            activation_conditions=["technology_evaluation", "experiment_request"],
            quality_gates=[],
            blocking=False, agents=["ai_engineer", "architect"]
        ),
        "disaster_recovery": ModuleSpec(
            id="M-008", name="Disaster Recovery & Business Continuity OS", version="1.0.0",
            description="Backup, recovery, continuity planning, crisis management",
            inputs=["service_inventory", "failure_scenarios", "infrastructure_map"],
            outputs=["bia_report", "rto_rpo_matrix", "dr_plan", "bc_plan",
                     "backup_architecture", "crisis_communication_plan"],
            dependencies=["safety_governance"],
            permissions=["dr_read", "dr_write", "backup_admin"],
            activation_conditions=["infrastructure_change", "security_incident"],
            quality_gates=["QG-010", "QG-016"],
            blocking=True, agents=["devops", "security"]
        ),
        "release_change": ModuleSpec(
            id="M-009", name="Release & Change Management OS", version="1.0.0",
            description="CI/CD, change control, deployment strategies, configuration management",
            inputs=["change_request", "release_artifacts", "deployment_target"],
            outputs=["release_plan", "change_record", "deployment_checklist",
                     "rollback_procedure", "release_notes"],
            dependencies=["safety_governance", "privacy_data"],
            permissions=["release_read", "release_deploy", "change_approve"],
            activation_conditions=["any_deployment", "configuration_change"],
            quality_gates=["QG-007", "QG-017"],
            blocking=True, agents=["devops", "qa"]
        ),
        "customer_experience": ModuleSpec(
            id="M-010", name="Customer Experience & Support OS", version="1.0.0",
            description="CX journey, support workflows, feedback, service recovery",
            inputs=["customer_data", "feedback_streams", "support_tickets"],
            outputs=["journey_map", "support_model", "slo_matrix",
                     "escalation_matrix", "feedback_program"],
            dependencies=[],
            permissions=["cx_read", "support_write", "feedback_collect"],
            activation_conditions=["customer_facing_release", "support_issue"],
            quality_gates=[],
            blocking=False, agents=["product_manager", "docs"]
        ),
    }
    
    @classmethod
    def get(cls, module_id: str) -> Optional[ModuleSpec]:
        return cls.MODULES.get(module_id)
    
    @classmethod
    def list_all(cls) -> Dict[str, str]:
        return {k: v.name for k, v in cls.MODULES.items()}
    
    @classmethod
    def get_blocking_modules(cls) -> List[ModuleSpec]:
        return [m for m in cls.MODULES.values() if m.blocking]
    
    @classmethod
    def get_dependency_order(cls, required_modules: List[str]) -> List[str]:
        """Topological sort of modules respecting dependencies."""
        visited = set()
        order = []
        
        def visit(name):
            if name in visited:
                return
            visited.add(name)
            mod = cls.get(name)
            if mod:
                for dep in mod.dependencies:
                    if dep in cls.MODULES:
                        visit(dep)
            order.append(name)
        
        for m in required_modules:
            if m in cls.MODULES:
                visit(m)
        
        return order
    
    @classmethod
    def get_all_gates(cls, module_ids: List[str]) -> List[str]:
        gates = []
        for mid in module_ids:
            mod = cls.get(mid)
            if mod:
                gates.extend(mod.quality_gates)
        return list(set(gates))