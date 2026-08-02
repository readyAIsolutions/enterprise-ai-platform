"""
ENI Platform Kernel — Central orchestration engine for the enterprise AI OS.
Dynamically loads modules, enforces quality gates, maintains audit trails.
"""
import json, time, uuid, logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger("eni.kernel")

class ModuleAuthority(Enum):
    REQUIRED = "required"
    ADVISORY = "advisory"
    BLOCKING = "blocking"
    OBSERVER = "observer"

class GateStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    SKIPPED = "skipped"

@dataclass
class QualityGate:
    name: str
    status: GateStatus = GateStatus.PENDING
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    blocker: bool = False

@dataclass
class ModuleActivation:
    module_name: str
    authority: ModuleAuthority
    config: Dict[str, Any] = field(default_factory=dict)

@dataclass
class KernelContext:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    project: str = ""
    objective: str = ""
    modules: List[ModuleActivation] = field(default_factory=list)
    gates: List[QualityGate] = field(default_factory=list)
    audit_log: List[Dict] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    completed_at: Optional[str] = None

class PlatformKernel:
    """Central kernel — loads modules, enforces gates, orchestrates execution."""
    
    def __init__(self, module_path: str = None):
        self.module_path = Path(module_path or Path(__file__).parent.parent / "modules")
        self.registry = {}
        self._discover_modules()
    
    def _discover_modules(self):
        for d in self.module_path.iterdir():
            if d.is_dir() and (d / "__init__.py").exists():
                self.registry[d.name] = {
                    "path": str(d),
                    "activated": False,
                    "version": self._read_version(d)
                }
    
    def _read_version(self, path: Path) -> str:
        init = path / "__init__.py"
        if init.exists():
            text = init.read_text()
            for line in text.split("\n"):
                if "__version__" in line:
                    return line.split("=")[-1].strip().strip('"\'')
        return "0.0.0"
    
    def audit(self, ctx: KernelContext, event: str, data: Dict = None):
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "session": ctx.session_id,
            "event": event,
            "data": data or {}
        }
        ctx.audit_log.append(entry)
        logger.info(f"AUDIT [{ctx.session_id}] {event}")
    
    def activate_module(self, ctx: KernelContext, name: str, 
                        authority: ModuleAuthority = ModuleAuthority.REQUIRED,
                        config: Dict = None) -> bool:
        if name not in self.registry:
            self.audit(ctx, f"module_missing:{name}", {"error": "Module not found"})
            return False
        ctx.modules.append(ModuleActivation(name, authority, config or {}))
        self.registry[name]["activated"] = True
        self.audit(ctx, f"module_activated:{name}", {"authority": authority.value})
        return True
    
    def add_gate(self, ctx: KernelContext, name: str, blocker: bool = False) -> QualityGate:
        gate = QualityGate(name=name, blocker=blocker)
        ctx.gates.append(gate)
        return gate
    
    def pass_gate(self, ctx: KernelContext, name: str, evidence: Dict = None):
        for g in ctx.gates:
            if g.name == name:
                g.status = GateStatus.PASSED
                g.evidence = evidence or {}
                g.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")
                self.audit(ctx, f"gate_passed:{name}", evidence)
                return
        # Auto-create if gate doesn't exist
        ctx.gates.append(QualityGate(name=name, status=GateStatus.PASSED, 
                                      evidence=evidence or {}))
        self.audit(ctx, f"gate_passed:{name}", evidence)
    
    def fail_gate(self, ctx: KernelContext, name: str, reason: str):
        for g in ctx.gates:
            if g.name == name:
                g.status = GateStatus.FAILED
                g.evidence = {"reason": reason}
                self.audit(ctx, f"gate_failed:{name}", {"reason": reason})
                return
        ctx.gates.append(QualityGate(name=name, status=GateStatus.FAILED,
                                      evidence={"reason": reason}))
    
    def check_blockers(self, ctx: KernelContext) -> List[str]:
        """Returns list of failed blocker gates."""
        return [g.name for g in ctx.gates if g.blocker and g.status == GateStatus.FAILED]
    
    def all_required_passed(self, ctx: KernelContext) -> bool:
        required = [g for g in ctx.gates if g.blocker]
        return all(g.status == GateStatus.PASSED for g in required)
    
    def finalize(self, ctx: KernelContext) -> Dict[str, Any]:
        ctx.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.audit(ctx, "kernel_finalized")
        return {
            "session_id": ctx.session_id,
            "project": ctx.project,
            "objective": ctx.objective,
            "modules_activated": [(m.module_name, m.authority.value) for m in ctx.modules],
            "gates": [(g.name, g.status.value) for g in ctx.gates],
            "blockers": self.check_blockers(ctx),
            "all_required_passed": self.all_required_passed(ctx),
            "audit_entries": len(ctx.audit_log),
            "metrics": ctx.metrics,
            "started_at": ctx.started_at,
            "completed_at": ctx.completed_at,
            "artifacts": list(ctx.artifacts.keys())
        }

# Singleton
_kernel_instance = None

def get_kernel() -> PlatformKernel:
    global _kernel_instance
    if _kernel_instance is None:
        _kernel_instance = PlatformKernel()
    return _kernel_instance

def new_context(project: str, objective: str) -> KernelContext:
    return KernelContext(project=project, objective=objective)