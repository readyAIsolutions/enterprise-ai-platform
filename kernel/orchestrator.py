"""
ENI Enterprise Orchestrator — Coordinates multi-agent execution across all OS modules.
Follows the pipeline: Kernel → Orchestrator → Context → Specialist Modules → Verification → Integration → Delivery → Monitoring
"""
import time, uuid, logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("eni.orchestrator")

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3

@dataclass
class TaskMessage:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    objective: str = ""
    required_inputs: List[str] = field(default_factory=list)
    required_outputs: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    assigned_agent: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    confidence: float = 0.0
    assumptions: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None

@dataclass
class AgentDefinition:
    name: str
    role: str
    capabilities: List[str]
    module: str
    authority: str  # "execute", "advise", "approve"

class Orchestrator:
    """Multi-agent orchestrator — coordinates the ENI enterprise agent swarm."""
    
    AGENTS = {
        "executive": AgentDefinition("executive", "Executive Orchestrator", 
            ["planning", "decision", "coordination"], "kernel", "approve"),
        "product_manager": AgentDefinition("product_manager", "Product Manager",
            ["requirements", "roadmap", "prioritization"], "kernel", "approve"),
        "architect": AgentDefinition("architect", "System Architect",
            ["design", "architecture", "standards"], "kernel", "execute"),
        "backend": AgentDefinition("backend", "Backend Engineer",
            ["api", "database", "business_logic"], "developer_experience", "execute"),
        "frontend": AgentDefinition("frontend", "Frontend Engineer",
            ["ui", "components", "state"], "developer_experience", "execute"),
        "security": AgentDefinition("security", "Security Engineer",
            ["vulnerability", "audit", "compliance"], "safety_governance", "block"),
        "ai_engineer": AgentDefinition("ai_engineer", "AI Engineer",
            ["prompts", "models", "rag", "embeddings"], "prompt_context", "execute"),
        "data_engineer": AgentDefinition("data_engineer", "Data Engineer",
            ["schema", "pipeline", "quality"], "privacy_data", "execute"),
        "qa": AgentDefinition("qa", "QA Engineer",
            ["testing", "verification", "validation"], "release_change", "execute"),
        "devops": AgentDefinition("devops", "DevSecOps Engineer",
            ["deployment", "monitoring", "infrastructure"], "release_change", "execute"),
        "compliance": AgentDefinition("compliance", "Compliance Officer",
            ["regulatory", "audit", "policy"], "safety_governance", "block"),
        "docs": AgentDefinition("docs", "Documentation Writer",
            ["docs", "guides", "knowledge"], "developer_experience", "execute"),
    }
    
    def __init__(self, max_workers: int = 10):
        self.tasks: Dict[str, TaskMessage] = {}
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.decision_log: List[Dict] = []
    
    def create_task(self, objective: str, priority: TaskPriority = TaskPriority.MEDIUM,
                    agent: str = None, deps: List[str] = None) -> TaskMessage:
        task = TaskMessage(objective=objective, priority=priority)
        if agent:
            task.assigned_agent = agent
        if deps:
            task.dependencies = deps
        self.tasks[task.task_id] = task
        return task
    
    def get_agent(self, name: str) -> Optional[AgentDefinition]:
        return self.AGENTS.get(name)
    
    def assign_best_agent(self, task: TaskMessage) -> str:
        """Basic capability matching — extends with semantic routing."""
        keywords = task.objective.lower()
        for name, agent in self.AGENTS.items():
            for cap in agent.capabilities:
                if cap in keywords:
                    task.assigned_agent = name
                    return name
        task.assigned_agent = "executive"
        return "executive"
    
    def execute_parallel(self, tasks: List[TaskMessage], executor_fn: Callable) -> Dict[str, Any]:
        """Execute tasks in parallel respecting dependency order."""
        results = {}
        ready = [t for t in tasks if not t.dependencies]
        
        futures = {}
        for task in ready:
            task.status = TaskStatus.IN_PROGRESS
            futures[self.executor.submit(executor_fn, task)] = task.task_id
        
        completed = set()
        for future in as_completed(futures):
            tid = futures[future]
            try:
                result = future.result()
                self.tasks[tid].status = TaskStatus.COMPLETED
                self.tasks[tid].result = result
                results[tid] = result
                completed.add(tid)
            except Exception as e:
                self.tasks[tid].status = TaskStatus.FAILED
                self.tasks[tid].error = str(e)
                results[tid] = {"error": str(e)}
        
        return results
    
    def log_decision(self, decision: str, rationale: str, agents_involved: List[str],
                     evidence: Dict = None):
        self.decision_log.append({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "decision": decision,
            "rationale": rationale,
            "agents": agents_involved,
            "evidence": evidence or {}
        })
    
    def conflict_resolve(self, claim_a: Dict, claim_b: Dict) -> Dict:
        """Evidence-based conflict resolution — never by authority alone."""
        conf_a = claim_a.get("confidence", 0)
        conf_b = claim_b.get("confidence", 0)
        decision = {
            "resolution": None,
            "rationale": "",
            "evidence_compared": [claim_a.get("source"), claim_b.get("source")]
        }
        if conf_a > conf_b:
            decision["resolution"] = "claim_a"
            decision["rationale"] = f"Higher confidence ({conf_a} vs {conf_b})"
        elif conf_b > conf_a:
            decision["resolution"] = "claim_b"
            decision["rationale"] = f"Higher confidence ({conf_b} vs {conf_a})"
        else:
            decision["resolution"] = "escalate"
            decision["rationale"] = "Equal confidence — requires human review"
        self.log_decision(
            decision=f"Conflict: {decision['resolution']}",
            rationale=decision["rationale"],
            agents_involved=[claim_a.get("agent", "unknown"), claim_b.get("agent", "unknown")],
            evidence=decision["evidence_compared"]
        )
        return decision