"""
Enterprise Agent Class Hierarchy — 17 specialized agents for the full
software delivery lifecycle.

Provides a dataclass-based agent model with enums for status/authority,
a thread-safe AgentRegistry, and an AgentFactory that validates and
instantiates agents from specifications.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, ClassVar, Dict, List, Optional, Type


# ── Enums ──────────────────────────────────────────────────────────────────────


class AgentStatus(str, Enum):
    """Current operational status of an agent."""

    IDLE = "idle"
    BUSY = "busy"
    BLOCKED = "blocked"
    OFFLINE = "offline"


class AuthorityLevel(IntEnum):
    """Hierarchical authority level (1 = lowest, 5 = highest)."""

    INFO = 1        # Advisory / information only
    CONTRIBUTOR = 2  # Can contribute to decisions
    DECISION_MAKER = 3  # Can make domain-specific decisions
    SENIOR = 4       # Can override domain decisions
    EXECUTIVE = 5    # Final decision authority, resolves conflicts


class AgentType(str, Enum):
    """Categorization of the 17 specialized agent roles."""

    EXECUTIVE_ORCHESTRATOR = "executive_orchestrator"
    PRODUCT_MANAGER = "product_manager"
    RESEARCH_AGENT = "research_agent"
    ARCHITECT = "architect"
    BACKEND_ENGINEER = "backend_engineer"
    FRONTEND_ENGINEER = "frontend_engineer"
    UI_DESIGNER = "ui_designer"
    AI_ENGINEER = "ai_engineer"
    DATA_ENGINEER = "data_engineer"
    SECURITY_ENGINEER = "security_engineer"
    DEVSECOPS = "devsecops"
    QA_ENGINEER = "qa_engineer"
    PERFORMANCE_ENGINEER = "performance_engineer"
    COMPLIANCE_OFFICER = "compliance_officer"
    DOCUMENTATION_WRITER = "documentation_writer"
    BUSINESS_ANALYST = "business_analyst"
    CX_SPECIALIST = "cx_specialist"


# ── Agent Type Mapping ─────────────────────────────────────────────────────────

# Maps AgentType enum values to their canonical agent_id strings.
AGENT_TYPE_TO_ID: Dict[AgentType, str] = {
    AgentType.EXECUTIVE_ORCHESTRATOR: "agent-exec-orchestrator",
    AgentType.PRODUCT_MANAGER: "agent-product-manager",
    AgentType.RESEARCH_AGENT: "agent-research",
    AgentType.ARCHITECT: "agent-architect",
    AgentType.BACKEND_ENGINEER: "agent-backend-engineer",
    AgentType.FRONTEND_ENGINEER: "agent-frontend-engineer",
    AgentType.UI_DESIGNER: "agent-ui-designer",
    AgentType.AI_ENGINEER: "agent-ai-engineer",
    AgentType.DATA_ENGINEER: "agent-data-engineer",
    AgentType.SECURITY_ENGINEER: "agent-security-engineer",
    AgentType.DEVSECOPS: "agent-devsecops",
    AgentType.QA_ENGINEER: "agent-qa-engineer",
    AgentType.PERFORMANCE_ENGINEER: "agent-performance-engineer",
    AgentType.COMPLIANCE_OFFICER: "agent-compliance-officer",
    AgentType.DOCUMENTATION_WRITER: "agent-documentation-writer",
    AgentType.BUSINESS_ANALYST: "agent-business-analyst",
    AgentType.CX_SPECIALIST: "agent-cx-specialist",
}

# Reverse mapping: agent_id -> AgentType
AGENT_ID_TO_TYPE: Dict[str, AgentType] = {v: k for k, v in AGENT_TYPE_TO_ID.items()}


# ── Base Agent ─────────────────────────────────────────────────────────────────


@dataclass
class Agent:
    """Base class for all specialized agents.

    Each agent has a unique identifier, a defined role, a set of
    responsibilities, an authority level, required capabilities,
    allowed actions, dependency relationships, and an operational status.

    Attributes:
        agent_id: Unique identifier (e.g. 'agent-exec-orchestrator').
        name: Human-readable display name.
        role: One-line role summary.
        description: Detailed role description.
        responsibilities: Ordered list of core duties.
        authority: Numeric authority level (1-5).
        capabilities: Required skills and knowledge areas.
        allowed_actions: Actions this agent is permitted to perform.
        dependencies: Agent IDs this agent depends on for input/approval.
        status: Current operational status.
    """

    agent_id: str
    name: str
    role: str
    description: str
    responsibilities: List[str] = field(default_factory=list)
    authority: AuthorityLevel = AuthorityLevel.CONTRIBUTOR
    capabilities: List[str] = field(default_factory=list)
    allowed_actions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    status: AgentStatus = AgentStatus.IDLE

    def __post_init__(self) -> None:
        """Validate required fields after initialization."""
        if not self.agent_id:
            raise ValueError("agent_id must not be empty")
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.role:
            raise ValueError("role must not be empty")
        if not isinstance(self.authority, AuthorityLevel):
            self.authority = AuthorityLevel(self.authority)

    def __hash__(self) -> int:
        return hash(self.agent_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Agent):
            return NotImplemented
        return self.agent_id == other.agent_id

    def set_status(self, status: AgentStatus) -> None:
        """Update the agent's operational status."""
        if not isinstance(status, AgentStatus):
            raise TypeError(f"status must be AgentStatus, got {type(status).__name__}")
        self.status = status

    def is_available(self) -> bool:
        """Return True if the agent is idle and can accept work."""
        return self.status == AgentStatus.IDLE

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the agent to a dictionary."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "responsibilities": self.responsibilities.copy(),
            "authority": self.authority.value,
            "capabilities": self.capabilities.copy(),
            "allowed_actions": self.allowed_actions.copy(),
            "dependencies": self.dependencies.copy(),
            "status": self.status.value,
        }


# ── Specialized Agents ─────────────────────────────────────────────────────────


@dataclass
class ExecutiveOrchestrator(Agent):
    """Top-level coordination agent with final decision authority.

    Serves as the escalation point for conflict resolution and
    cross-team prioritization. Has the highest authority level (5).
    """

    agent_id: str = "agent-exec-orchestrator"
    name: str = "Executive Orchestrator"
    role: str = "Top-level coordination, final decision authority, conflict resolution"
    description: str = (
        "The Executive Orchestrator provides top-level oversight and coordination "
        "across all agent teams. It holds final decision-making authority for "
        "escalated conflicts, priority trade-offs, and strategic direction. "
        "It ensures alignment with business objectives and resolves deadlocks "
        "that cannot be settled at lower authority levels."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Provide top-level strategic oversight and coordination",
            "Resolve escalated conflicts between agents or teams",
            "Make final decisions on priority trade-offs and resource allocation",
            "Ensure alignment between agent outputs and business objectives",
            "Approve or reject escalated architectural and design decisions",
            "Monitor overall project health and agent team performance",
            "Synthesize cross-team outputs into coherent deliverables",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.EXECUTIVE
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Strategic planning",
            "Conflict resolution",
            "Cross-team coordination",
            "Decision-making under uncertainty",
            "Stakeholder management",
            "Risk assessment",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "orchestrate_workflow",
            "resolve_conflict",
            "assign_priority",
            "override_decision",
            "escalate_external",
            "approve_deliverable",
            "reject_deliverable",
        ]
    )
    dependencies: List[str] = field(default_factory=list)


@dataclass
class ProductManager(Agent):
    """Product strategy agent managing requirements, priorities, and backlog."""

    agent_id: str = "agent-product-manager"
    name: str = "Product Manager"
    role: str = "Requirements definition, user stories, priorities, backlog management"
    description: str = (
        "The Product Manager defines and prioritizes product requirements, "
        "manages the backlog, authors user stories, and ensures that the team "
        "builds the right things for the right reasons. Acts as the voice of "
        "the customer and business stakeholders."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Define and prioritize product requirements and features",
            "Write, refine, and maintain user stories with acceptance criteria",
            "Manage and groom the product backlog",
            "Align product roadmap with business strategy and user needs",
            "Facilitate stakeholder communication and expectation management",
            "Define success metrics and KPIs for features",
            "Coordinate with UX, engineering, and business stakeholders",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.SENIOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Product strategy",
            "User story mapping",
            "Backlog management",
            "Stakeholder communication",
            "Market analysis",
            "Roadmap planning",
            "Agile methodologies",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "create_user_story",
            "prioritize_backlog",
            "define_requirements",
            "accept_feature",
            "reject_feature",
            "update_roadmap",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-exec-orchestrator",
            "agent-business-analyst",
            "agent-cx-specialist",
        ]
    )


@dataclass
class ResearchAgent(Agent):
    """Market and technology research agent."""

    agent_id: str = "agent-research"
    name: str = "Research Agent"
    role: str = "Market research, technology evaluation, competitive analysis"
    description: str = (
        "The Research Agent conducts deep market and technology research, "
        "evaluates competitors, identifies emerging trends, and provides "
        "data-driven insights to inform product and technology decisions."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Conduct market research and competitive analysis",
            "Evaluate emerging technologies and frameworks",
            "Produce technology landscape reports",
            "Benchmark competitors' products and features",
            "Identify industry trends and opportunities",
            "Provide data-driven recommendations for technology adoption",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.INFO
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Market research",
            "Technology evaluation",
            "Competitive analysis",
            "Data synthesis",
            "Trend analysis",
            "Technical writing",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "conduct_research",
            "evaluate_technology",
            "benchmark_competitor",
            "publish_research_brief",
            "recommend_adoption",
        ]
    )
    dependencies: List[str] = field(default_factory=list)


@dataclass
class Architect(Agent):
    """System architecture and design agent."""

    agent_id: str = "agent-architect"
    name: str = "Architect"
    role: str = "System design, architecture patterns, tech stack, API design"
    description: str = (
        "The Architect designs system architecture, selects technology stacks, "
        "defines API contracts, and ensures that solutions are scalable, "
        "maintainable, and aligned with enterprise standards."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Design system architecture and component topology",
            "Select and justify technology stack decisions",
            "Define API contracts, data models, and integration patterns",
            "Establish architectural standards and design patterns",
            "Review and approve major design decisions",
            "Identify and mitigate architectural risks",
            "Document architecture decision records (ADRs)",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.DECISION_MAKER
    capabilities: List[str] = field(
        default_factory=lambda: [
            "System architecture",
            "API design",
            "Distributed systems",
            "Cloud architecture",
            "Design patterns",
            "Performance modeling",
            "Technical leadership",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "design_architecture",
            "define_api",
            "approve_tech_stack",
            "publish_adr",
            "review_design",
            "identify_risk",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-product-manager",
            "agent-research",
        ]
    )


@dataclass
class BackendEngineer(Agent):
    """Server-side implementation agent."""

    agent_id: str = "agent-backend-engineer"
    name: str = "Backend Engineer"
    role: str = "Server-side implementation, databases, APIs, business logic"
    description: str = (
        "The Backend Engineer implements server-side logic, database schemas, "
        "API endpoints, and business logic. Ensures code quality, performance, "
        "and reliability of backend systems."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Implement server-side business logic and services",
            "Design and implement database schemas and queries",
            "Build and maintain RESTful and GraphQL APIs",
            "Write unit, integration, and contract tests",
            "Optimize database performance and query efficiency",
            "Implement authentication, authorization, and security controls",
            "Participate in code reviews and pair programming",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.CONTRIBUTOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Backend development",
            "Database design",
            "API development",
            "Testing",
            "Performance optimization",
            "Security best practices",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "implement_feature",
            "write_test",
            "review_code",
            "optimize_query",
            "deploy_service",
            "fix_bug",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-architect",
            "agent-qa-engineer",
        ]
    )


@dataclass
class FrontendEngineer(Agent):
    """Client-side implementation agent."""

    agent_id: str = "agent-frontend-engineer"
    name: str = "Frontend Engineer"
    role: str = "Client-side implementation, UI components, state management"
    description: str = (
        "The Frontend Engineer builds user-facing interfaces, implements "
        "UI components, manages client-side state, and ensures responsive, "
        "performant web applications."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Implement responsive UI components and pages",
            "Manage client-side state and data flow",
            "Integrate with backend APIs and services",
            "Write component, integration, and E2E tests",
            "Optimize frontend performance and bundle size",
            "Ensure cross-browser compatibility and accessibility",
            "Participate in design reviews and code reviews",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.CONTRIBUTOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Frontend development",
            "State management",
            "Responsive design",
            "Performance optimization",
            "Testing (unit, integration, E2E)",
            "Accessibility (a11y)",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "implement_component",
            "write_test",
            "integrate_api",
            "optimize_performance",
            "fix_bug",
            "review_code",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-ui-designer",
            "agent-backend-engineer",
        ]
    )


@dataclass
class UIDesigner(Agent):
    """User experience and interface design agent."""

    agent_id: str = "agent-ui-designer"
    name: str = "UI/UX Designer"
    role: str = "User experience, accessibility, design system, wireframes"
    description: str = (
        "The UI/UX Designer creates intuitive user experiences, establishes "
        "design systems, produces wireframes and prototypes, and ensures "
        "accessibility compliance across all user interfaces."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Create user flows, wireframes, and interactive prototypes",
            "Establish and maintain the design system and component library",
            "Conduct usability testing and heuristic evaluations",
            "Ensure WCAG accessibility compliance",
            "Collaborate with product and engineering on design feasibility",
            "Define visual design language and interaction patterns",
            "Gather and incorporate user feedback into designs",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.CONTRIBUTOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "UX design",
            "UI design",
            "Design systems",
            "Prototyping",
            "Usability testing",
            "Accessibility standards",
            "Interaction design",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "create_wireframe",
            "build_prototype",
            "conduct_usability_test",
            "update_design_system",
            "review_accessibility",
            "gather_feedback",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-product-manager",
            "agent-cx-specialist",
        ]
    )


@dataclass
class AIEngineer(Agent):
    """Machine learning and AI engineering agent."""

    agent_id: str = "agent-ai-engineer"
    name: str = "AI Engineer"
    role: str = "ML models, data pipelines, model deployment, AI safety"
    description: str = (
        "The AI Engineer develops, trains, and deploys machine learning models, "
        "builds data pipelines, ensures AI safety and fairness, and integrates "
        "AI capabilities into products."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Design, train, and evaluate machine learning models",
            "Build and maintain ML data pipelines and feature stores",
            "Deploy models to production with monitoring and rollback",
            "Implement AI safety guardrails and fairness assessments",
            "Optimize model inference performance and cost",
            "Conduct model interpretability and explainability analysis",
            "Stay current with AI/ML research and best practices",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.DECISION_MAKER
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Machine learning",
            "Deep learning",
            "Data pipeline engineering",
            "Model deployment (MLOps)",
            "AI safety and ethics",
            "Python, PyTorch, TensorFlow",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "train_model",
            "evaluate_model",
            "deploy_model",
            "build_pipeline",
            "audit_safety",
            "optimize_inference",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-data-engineer",
            "agent-security-engineer",
        ]
    )


@dataclass
class DataEngineer(Agent):
    """Data architecture and infrastructure agent."""

    agent_id: str = "agent-data-engineer"
    name: str = "Data Engineer"
    role: str = "Data architecture, ETL, data quality, analytics infrastructure"
    description: str = (
        "The Data Engineer designs and maintains data architecture, builds "
        "ETL/ELT pipelines, ensures data quality and governance, and provides "
        "the data infrastructure that powers analytics and AI."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Design and maintain data architecture and data models",
            "Build and orchestrate ETL/ELT data pipelines",
            "Implement data quality monitoring and validation",
            "Manage data warehousing and lakehouse infrastructure",
            "Ensure data governance, lineage, and cataloging",
            "Optimize data storage, partitioning, and retrieval",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.CONTRIBUTOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Data modeling",
            "ETL/ELT pipeline design",
            "SQL and NoSQL databases",
            "Data warehousing",
            "Data quality frameworks",
            "Apache Spark, Airflow, dbt",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "design_schema",
            "build_pipeline",
            "validate_data",
            "monitor_quality",
            "optimize_storage",
            "publish_catalog",
        ]
    )
    dependencies: List[str] = field(default_factory=list)


@dataclass
class SecurityEngineer(Agent):
    """Security engineering agent."""

    agent_id: str = "agent-security-engineer"
    name: str = "Security Engineer"
    role: str = "Threat modeling, vulnerability assessment, security controls"
    description: str = (
        "The Security Engineer identifies threats, assesses vulnerabilities, "
        "implements security controls, conducts penetration testing, and ensures "
        "the overall security posture of systems and applications."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Conduct threat modeling and attack surface analysis",
            "Perform vulnerability assessments and penetration testing",
            "Design and implement security controls and countermeasures",
            "Review code and architecture for security flaws",
            "Manage secrets, keys, and certificate infrastructure",
            "Respond to security incidents and conduct root cause analysis",
            "Define security policies, standards, and best practices",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.DECISION_MAKER
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Threat modeling",
            "Vulnerability assessment",
            "Penetration testing",
            "Security architecture",
            "Incident response",
            "Cryptography",
            "OWASP standards",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "threat_model",
            "vulnerability_scan",
            "penetration_test",
            "security_review",
            "block_deployment",
            "incident_respond",
            "publish_policy",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-architect",
            "agent-compliance-officer",
        ]
    )


@dataclass
class DevSecOps(Agent):
    """Development, security, and operations agent."""

    agent_id: str = "agent-devsecops"
    name: str = "DevSecOps Engineer"
    role: str = "CI/CD, infrastructure, monitoring, deployment automation"
    description: str = (
        "The DevSecOps Engineer builds and maintains CI/CD pipelines, manages "
        "cloud infrastructure, implements monitoring and observability, and "
        "automates deployment workflows with security integrated throughout."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Design and maintain CI/CD pipelines with security gates",
            "Manage cloud infrastructure and Infrastructure as Code (IaC)",
            "Implement monitoring, alerting, and observability",
            "Automate deployment, scaling, and rollback procedures",
            "Manage container orchestration and service mesh",
            "Implement secrets management and secure configuration",
            "Optimize infrastructure costs and resource utilization",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.CONTRIBUTOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "CI/CD pipelines",
            "Infrastructure as Code",
            "Container orchestration (Kubernetes)",
            "Cloud platforms (AWS, GCP, Azure)",
            "Monitoring and observability",
            "Automation and scripting",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "build_pipeline",
            "deploy_service",
            "provision_infra",
            "configure_monitoring",
            "rollback_deployment",
            "manage_secrets",
            "scale_infrastructure",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-security-engineer",
            "agent-architect",
        ]
    )


@dataclass
class QAEngineer(Agent):
    """Quality assurance and testing agent."""

    agent_id: str = "agent-qa-engineer"
    name: str = "QA Engineer"
    role: str = "Test strategy, test automation, quality gates, bug tracking"
    description: str = (
        "The QA Engineer defines test strategies, builds test automation "
        "frameworks, enforces quality gates, tracks defects, and ensures "
        "that every release meets quality standards."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Define and maintain test strategy and test plans",
            "Build and maintain automated test suites (unit, integration, E2E)",
            "Enforce quality gates in the CI/CD pipeline",
            "Track, triage, and manage bug reports",
            "Perform exploratory and regression testing",
            "Report on quality metrics, coverage, and trends",
            "Advocate for quality and testing best practices",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.DECISION_MAKER
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Test automation",
            "Test strategy",
            "Quality metrics",
            "Bug tracking",
            "CI/CD integration",
            "Performance testing",
            "Security testing basics",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "write_test",
            "run_test_suite",
            "approve_release",
            "block_release",
            "file_bug",
            "verify_fix",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-devsecops",
            "agent-performance-engineer",
        ]
    )


@dataclass
class PerformanceEngineer(Agent):
    """Performance and scalability engineering agent."""

    agent_id: str = "agent-performance-engineer"
    name: str = "Performance Engineer"
    role: str = "Load testing, optimization, capacity planning"
    description: str = (
        "The Performance Engineer conducts load and stress testing, identifies "
        "bottlenecks, optimizes system performance, plans capacity, and ensures "
        "systems meet latency and throughput SLOs."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Design and execute load, stress, and soak tests",
            "Profile and optimize application and database performance",
            "Identify and resolve performance bottlenecks",
            "Define and monitor SLOs, SLIs, and error budgets",
            "Plan capacity and forecast resource requirements",
            "Benchmark system performance against targets",
            "Recommend architecture changes for scalability",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.CONTRIBUTOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Load testing (k6, JMeter, Locust)",
            "Performance profiling",
            "Database optimization",
            "Capacity planning",
            "SLO/SLI definition",
            "Distributed tracing",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "run_load_test",
            "profile_application",
            "identify_bottleneck",
            "recommend_optimization",
            "forecast_capacity",
            "report_metrics",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-architect",
            "agent-devsecops",
        ]
    )


@dataclass
class ComplianceOfficer(Agent):
    """Regulatory compliance and audit agent."""

    agent_id: str = "agent-compliance-officer"
    name: str = "Compliance Officer"
    role: str = "Regulatory compliance, audit trails, policy enforcement"
    description: str = (
        "The Compliance Officer ensures that all systems, processes, and "
        "deliverables adhere to relevant regulations (GDPR, SOC 2, HIPAA, "
        "etc.), maintains audit trails, and enforces organizational policies."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Map regulatory requirements to technical controls",
            "Conduct compliance assessments and gap analyses",
            "Maintain audit trails and evidence collection",
            "Define and enforce compliance policies",
            "Prepare for and support external audits",
            "Monitor regulatory changes and update controls",
            "Report on compliance posture to leadership",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.SENIOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Regulatory compliance (GDPR, SOC 2, HIPAA)",
            "Audit management",
            "Policy enforcement",
            "Risk assessment",
            "Control framework design",
            "Documentation",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "assess_compliance",
            "define_policy",
            "enforce_control",
            "block_noncompliant",
            "generate_audit_report",
            "flag_violation",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-security-engineer",
            "agent-exec-orchestrator",
        ]
    )


@dataclass
class DocumentationWriter(Agent):
    """Technical documentation agent."""

    agent_id: str = "agent-documentation-writer"
    name: str = "Documentation Writer"
    role: str = "Technical documentation, API docs, knowledge base"
    description: str = (
        "The Documentation Writer creates and maintains technical documentation, "
        "API references, user guides, runbooks, and knowledge base articles to "
        "ensure all systems are well-documented and accessible."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Write and maintain technical documentation and user guides",
            "Generate and curate API documentation",
            "Build and maintain the internal knowledge base",
            "Document architecture decisions and design rationales",
            "Create runbooks, playbooks, and troubleshooting guides",
            "Establish documentation standards and templates",
            "Review documentation for accuracy and completeness",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.INFO
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Technical writing",
            "API documentation (OpenAPI, GraphQL)",
            "Knowledge base management",
            "Information architecture",
            "Diagramming and visual communication",
            "Markdown, reStructuredText, AsciiDoc",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "write_documentation",
            "generate_api_docs",
            "update_knowledge_base",
            "create_runbook",
            "review_docs",
            "publish_docs",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-architect",
            "agent-product-manager",
        ]
    )


@dataclass
class BusinessAnalyst(Agent):
    """Business analysis and requirements agent."""

    agent_id: str = "agent-business-analyst"
    name: str = "Business Analyst"
    role: str = "Business requirements, ROI analysis, stakeholder alignment"
    description: str = (
        "The Business Analyst bridges business and technology, gathering "
        "and analyzing business requirements, performing ROI analysis, "
        "facilitating stakeholder alignment, and ensuring solutions deliver "
        "measurable business value."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Elicit, analyze, and document business requirements",
            "Conduct ROI analysis and business case development",
            "Model business processes and identify improvement opportunities",
            "Facilitate stakeholder workshops and alignment sessions",
            "Define measurable success criteria and KPIs",
            "Trace requirements through to delivered functionality",
            "Assess solution fit against business objectives",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.CONTRIBUTOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Business analysis",
            "Requirements elicitation",
            "ROI and cost-benefit analysis",
            "Process modeling (BPMN)",
            "Stakeholder management",
            "Data analysis",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "gather_requirements",
            "analyze_roi",
            "model_process",
            "facilitate_workshop",
            "define_kpi",
            "validate_solution",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-product-manager",
            "agent-cx-specialist",
        ]
    )


@dataclass
class CXSpecialist(Agent):
    """Customer experience specialist agent."""

    agent_id: str = "agent-cx-specialist"
    name: str = "CX Specialist"
    role: str = "Customer experience, user feedback, satisfaction metrics"
    description: str = (
        "The CX Specialist focuses on the end-to-end customer journey, "
        "collects and analyzes user feedback, measures satisfaction metrics, "
        "and advocates for the customer in every product decision."
    )
    responsibilities: List[str] = field(
        default_factory=lambda: [
            "Map and analyze end-to-end customer journeys",
            "Collect and synthesize user feedback and sentiment",
            "Define and measure customer satisfaction metrics (CSAT, NPS)",
            "Identify pain points and opportunities for experience improvement",
            "Conduct user interviews and observational studies",
            "Advocate for customer needs in product and design decisions",
            "Track experience metrics over time and report trends",
        ]
    )
    authority: AuthorityLevel = AuthorityLevel.CONTRIBUTOR
    capabilities: List[str] = field(
        default_factory=lambda: [
            "Customer journey mapping",
            "User research",
            "Feedback analysis",
            "Satisfaction metrics (CSAT, NPS, CES)",
            "Empathy and advocacy",
            "Data-driven storytelling",
        ]
    )
    allowed_actions: List[str] = field(
        default_factory=lambda: [
            "map_journey",
            "collect_feedback",
            "measure_satisfaction",
            "identify_painpoint",
            "conduct_interview",
            "advocate_customer",
        ]
    )
    dependencies: List[str] = field(
        default_factory=lambda: [
            "agent-product-manager",
            "agent-ui-designer",
        ]
    )


# ── Agent Registry ─────────────────────────────────────────────────────────────


class AgentRegistry:
    """Thread-safe registry for managing all agent classes and instances.

    Provides lookup by agent_id, enumeration of all registered agent types,
    and instance tracking. All mutations are protected by a re-entrant lock.

    Usage:
        registry = AgentRegistry()
        registry.register(ExecutiveOrchestrator)
        cls = registry.get("agent-exec-orchestrator")
        agent = registry.create_instance("agent-exec-orchestrator")
    """

    # All 17 agent classes pre-registered
    _BUILTIN_AGENTS: ClassVar[List[Type[Agent]]] = [
        ExecutiveOrchestrator,
        ProductManager,
        ResearchAgent,
        Architect,
        BackendEngineer,
        FrontendEngineer,
        UIDesigner,
        AIEngineer,
        DataEngineer,
        SecurityEngineer,
        DevSecOps,
        QAEngineer,
        PerformanceEngineer,
        ComplianceOfficer,
        DocumentationWriter,
        BusinessAnalyst,
        CXSpecialist,
    ]

    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
        self._agent_classes: Dict[str, Type[Agent]] = {}
        self._instances: Dict[str, Agent] = {}
        self._register_builtins()

    def _register_builtins(self) -> None:
        """Register all 17 built-in agent classes."""
        for cls in self._BUILTIN_AGENTS:
            instance = cls()
            self._agent_classes[instance.agent_id] = cls

    def register(self, agent_cls: Type[Agent]) -> None:
        """Register an agent class.

        Args:
            agent_cls: A subclass of Agent to register.

        Raises:
            TypeError: If agent_cls is not a subclass of Agent.
            ValueError: If an agent with this ID is already registered.
        """
        if not issubclass(agent_cls, Agent):
            raise TypeError(
                f"agent_cls must be a subclass of Agent, got {agent_cls.__name__}"
            )

        # Create a temporary instance to extract the agent_id
        temp = agent_cls()
        agent_id = temp.agent_id

        with self._lock:
            if agent_id in self._agent_classes:
                existing = self._agent_classes[agent_id].__name__
                raise ValueError(
                    f"Agent ID '{agent_id}' is already registered by {existing}. "
                    f"Cannot re-register with {agent_cls.__name__}."
                )
            self._agent_classes[agent_id] = agent_cls

    def get(self, agent_id: str) -> Optional[Type[Agent]]:
        """Get the agent class for the given agent_id.

        Args:
            agent_id: The unique agent identifier.

        Returns:
            The Agent subclass, or None if not found.
        """
        with self._lock:
            return self._agent_classes.get(agent_id)

    def get_instance(self, agent_id: str) -> Optional[Agent]:
        """Get a registered agent instance.

        Args:
            agent_id: The unique agent identifier.

        Returns:
            The agent instance, or None if not found or not instantiated.
        """
        with self._lock:
            return self._instances.get(agent_id)

    def create_instance(self, agent_id: str, **overrides: Any) -> Agent:
        """Create and register an agent instance.

        Creates a new instance from the registered class and stores it.

        Args:
            agent_id: The unique agent identifier.
            **overrides: Keyword arguments to override default field values.

        Returns:
            The created agent instance.

        Raises:
            KeyError: If agent_id is not registered.
            ValueError: If the instance cannot be created.
        """
        with self._lock:
            agent_cls = self._agent_classes.get(agent_id)
            if agent_cls is None:
                raise KeyError(f"No agent class registered for ID '{agent_id}'")

            kwargs: Dict[str, Any] = {}
            if overrides:
                kwargs.update(overrides)
            kwargs.setdefault("agent_id", agent_id)

            try:
                instance = agent_cls(**kwargs)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Failed to create instance of {agent_cls.__name__}: {exc}"
                ) from exc

            self._instances[agent_id] = instance
            return instance

    def list_all(self) -> Dict[str, str]:
        """Return a mapping of all registered agent IDs to class names."""
        with self._lock:
            return {aid: cls.__name__ for aid, cls in self._agent_classes.items()}

    def list_instances(self) -> Dict[str, Agent]:
        """Return a shallow copy of all instantiated agents."""
        with self._lock:
            return dict(self._instances)

    def list_by_authority(self, min_authority: AuthorityLevel) -> List[Agent]:
        """Return all instantiated agents at or above the given authority level."""
        with self._lock:
            return [
                agent
                for agent in self._instances.values()
                if agent.authority >= min_authority
            ]

    def list_by_status(self, status: AgentStatus) -> List[Agent]:
        """Return all instantiated agents matching the given status."""
        with self._lock:
            return [
                agent
                for agent in self._instances.values()
                if agent.status == status
            ]

    def list_available(self) -> List[Agent]:
        """Return all idle agents ready to accept work."""
        return self.list_by_status(AgentStatus.IDLE)

    def list_blocked(self) -> List[Agent]:
        """Return all blocked agents."""
        return self.list_by_status(AgentStatus.BLOCKED)

    def get_dependents(self, agent_id: str) -> List[Agent]:
        """Return all instantiated agents that depend on the given agent_id."""
        with self._lock:
            return [
                agent
                for agent in self._instances.values()
                if agent_id in agent.dependencies
            ]

    def get_dependency_chain(self, agent_id: str) -> List[str]:
        """Resolve the full dependency chain for an agent (topological order).

        Returns a list of agent IDs that must be available before this agent
        can operate, ordered from root dependencies inward.

        Args:
            agent_id: The agent to compute dependencies for.

        Returns:
            Ordered list of dependency agent IDs (excluding the agent itself).
        """
        with self._lock:
            agent = self._instances.get(agent_id)
            if agent is None:
                return []

            resolved: List[str] = []
            seen: set = set()

            def _resolve(aid: str) -> None:
                if aid in seen:
                    return
                seen.add(aid)
                dep_agent = self._instances.get(aid)
                if dep_agent:
                    for dep_id in dep_agent.dependencies:
                        _resolve(dep_id)
                if aid != agent_id:
                    resolved.append(aid)

            _resolve(agent_id)
            return resolved

    def find_by_capability(self, capability: str) -> List[Agent]:
        """Find all instantiated agents possessing a given capability.

        Performs a case-insensitive substring match against capability strings.
        """
        cap_lower = capability.lower()
        with self._lock:
            return [
                agent
                for agent in self._instances.values()
                if any(cap_lower in c.lower() for c in agent.capabilities)
            ]

    def count(self) -> int:
        """Return the number of registered agent classes."""
        with self._lock:
            return len(self._agent_classes)

    def instance_count(self) -> int:
        """Return the number of instantiated agents."""
        with self._lock:
            return len(self._instances)

    def reset(self) -> None:
        """Clear all registered instances (classes are preserved)."""
        with self._lock:
            self._instances.clear()

    def __len__(self) -> int:
        return self.count()

    def __contains__(self, agent_id: str) -> bool:
        with self._lock:
            return agent_id in self._agent_classes

    def __iter__(self):
        with self._lock:
            return iter(self._agent_classes.items())


# ── Agent Factory ──────────────────────────────────────────────────────────────


class AgentFactory:
    """Factory for creating and validating agent instances.

    Wraps AgentRegistry with validation logic, pre- and post-creation hooks,
    and batch instantiation capabilities.

    Usage:
        factory = AgentFactory()
        exec_agent = factory.create("agent-exec-orchestrator")
        all_agents = factory.create_all()
    """

    def __init__(self, registry: Optional[AgentRegistry] = None) -> None:
        """Initialize the factory with an optional existing registry.

        Args:
            registry: An existing AgentRegistry. Creates a new one if not provided.
        """
        self._registry = registry or AgentRegistry()
        self._pre_create_hooks: List[callable] = []
        self._post_create_hooks: List[callable] = []

    @property
    def registry(self) -> AgentRegistry:
        """Return the underlying AgentRegistry."""
        return self._registry

    def add_pre_create_hook(self, hook: callable) -> None:
        """Add a hook called before each agent is created.

        The hook receives (agent_id, kwargs) and may modify kwargs in-place
        or raise an exception to abort creation.
        """
        self._pre_create_hooks.append(hook)

    def add_post_create_hook(self, hook: callable) -> None:
        """Add a hook called after each agent is created.

        The hook receives the created agent instance.
        """
        self._post_create_hooks.append(hook)

    def create(self, agent_id: str, **overrides: Any) -> Agent:
        """Create a single agent with validation and hooks.

        Args:
            agent_id: The agent identifier to create.
            **overrides: Field values to override on the agent.

        Returns:
            The created agent instance.

        Raises:
            KeyError: If agent_id is not registered.
            ValueError: If validation fails.
        """
        # Run pre-create hooks
        kwargs = dict(overrides)
        for hook in self._pre_create_hooks:
            hook(agent_id, kwargs)

        # Validate the agent class exists
        if agent_id not in self._registry:
            raise KeyError(
                f"Agent ID '{agent_id}' is not registered. "
                f"Available: {list(self._registry.list_all().keys())}"
            )

        agent_cls = self._registry.get(agent_id)

        # Validate that overrides don't include invalid fields
        valid_fields = {
            f.name
            for f in agent_cls.__dataclass_fields__.values()  # type: ignore[attr-defined]
        }
        invalid = set(kwargs.keys()) - valid_fields
        if invalid:
            raise ValueError(
                f"Invalid field(s) for {agent_cls.__name__}: {invalid}. "
                f"Valid fields: {valid_fields}"
            )

        # Validate authority level if provided
        if "authority" in kwargs and not isinstance(
            kwargs["authority"], AuthorityLevel
        ):
            try:
                kwargs["authority"] = AuthorityLevel(int(kwargs["authority"]))
            except (ValueError, TypeError):
                raise ValueError(
                    f"Invalid authority level: {kwargs['authority']}. "
                    f"Must be one of {[a.value for a in AuthorityLevel]}"
                )

        # Validate status if provided
        if "status" in kwargs and not isinstance(kwargs["status"], AgentStatus):
            try:
                kwargs["status"] = AgentStatus(kwargs["status"])
            except ValueError:
                raise ValueError(
                    f"Invalid status: {kwargs['status']}. "
                    f"Must be one of {[s.value for s in AgentStatus]}"
                )

        # Create the instance
        instance = self._registry.create_instance(agent_id, **kwargs)

        # Run post-create hooks
        for hook in self._post_create_hooks:
            hook(instance)

        return instance

    def create_all(
        self, status: AgentStatus = AgentStatus.IDLE
    ) -> Dict[str, Agent]:
        """Create one instance of every registered agent type.

        Args:
            status: Initial status for all created agents (default: IDLE).

        Returns:
            Dict mapping agent_id to the created instance.
        """
        results: Dict[str, Agent] = {}
        for agent_id in self._registry.list_all():
            try:
                results[agent_id] = self.create(agent_id, status=status)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to create agent '{agent_id}': {exc}"
                ) from exc
        return results

    def create_team(
        self,
        agent_ids: List[str],
        status: AgentStatus = AgentStatus.IDLE,
    ) -> Dict[str, Agent]:
        """Create a specific subset of agents as a team.

        Args:
            agent_ids: List of agent IDs to create.
            status: Initial status for all created agents.

        Returns:
            Dict mapping agent_id to the created instance.

        Raises:
            KeyError: If any agent_id is not registered.
        """
        results: Dict[str, Agent] = {}
        for agent_id in agent_ids:
            results[agent_id] = self.create(agent_id, status=status)
        return results

    def create_with_dependencies(
        self,
        agent_ids: List[str],
        status: AgentStatus = AgentStatus.IDLE,
    ) -> Dict[str, Agent]:
        """Create a set of agents, automatically including all dependencies.

        Args:
            agent_ids: The desired agent IDs.
            status: Initial status for all created agents.

        Returns:
            Dict mapping agent_id to the created instance for all agents.

        Raises:
            KeyError: If any agent_id (including dependencies) is not registered.
        """
        # Collect all required IDs including full dependency chains
        all_ids: set = set()
        for aid in agent_ids:
            if aid not in self._registry:
                raise KeyError(f"Agent ID '{aid}' is not registered")
            all_ids.add(aid)
            # Walk dependencies
            agent_cls = self._registry.get(aid)
            temp = agent_cls()
            stack = list(temp.dependencies)
            while stack:
                dep_id = stack.pop()
                if dep_id not in all_ids:
                    all_ids.add(dep_id)
                    dep_cls = self._registry.get(dep_id)
                    if dep_cls:
                        dep_temp = dep_cls()
                        stack.extend(dep_temp.dependencies)

        return self.create_team(list(all_ids), status=status)

    def validate_all(self) -> List[str]:
        """Validate all registered agent classes for consistency.

        Checks that every dependency references a registered agent type
        and performs basic field validation.

        Returns:
            A list of warning/error messages (empty if all valid).
        """
        issues: List[str] = []
        with self._registry._lock:
            for agent_id, agent_cls in self._registry._agent_classes.items():
                try:
                    temp = agent_cls()
                except Exception as exc:
                    issues.append(f"[{agent_id}] Instantiation failed: {exc}")
                    continue

                # Validate dependencies exist
                for dep_id in temp.dependencies:
                    if dep_id not in self._registry._agent_classes:
                        issues.append(
                            f"[{agent_id}] Dependency '{dep_id}' is not registered"
                        )

                # Validate authority range
                if not (1 <= temp.authority.value <= 5):
                    issues.append(
                        f"[{agent_id}] Authority {temp.authority} out of range [1-5]"
                    )

        return issues

    def blueprint(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return a blueprint dictionary of the agent's default configuration.

        Useful for inspecting an agent's fields before creating an instance.

        Args:
            agent_id: The agent identifier.

        Returns:
            Dict of field names to default values, or None if not found.
        """
        agent_cls = self._registry.get(agent_id)
        if agent_cls is None:
            return None
        temp = agent_cls()
        return temp.to_dict()