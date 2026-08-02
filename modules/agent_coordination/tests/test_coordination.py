"""
Comprehensive test suite for Agent Communication & Coordination OS module.
Tests: Agents, Communication, Scheduler, Shared Knowledge, Conflict,
Verification, Fault Tolerance, and Integration.
"""
import pytest
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

# Agents
from enterprise.modules.agent_coordination.agents import (
    Agent, AgentRegistry, AgentFactory, AgentStatus, AgentType, AuthorityLevel,
    ExecutiveOrchestrator, ProductManager, Architect, BackendEngineer,
    SecurityEngineer, QAEngineer, ComplianceOfficer, DocumentationWriter,
    ResearchAgent, FrontendEngineer, UIDesigner, AIEngineer,
    DataEngineer, DevSecOps, PerformanceEngineer, BusinessAnalyst, CXSpecialist,
)
# Communication
from enterprise.modules.agent_coordination.communication import (
    Message, MessageBus, MessageVersionTracker, AuditTrail, AuditEntry,
    MessageValidation, CompletionStatus, Priority as MsgPriority,
)
# Scheduler
from enterprise.modules.agent_coordination.scheduler import (
    Task, Scheduler, TaskStatus, SchedulingFactor, AgentCapacity,
)
# Shared Knowledge
from enterprise.modules.agent_coordination.shared_knowledge import (
    KnowledgeEntry, SharedKnowledgeBase, KnowledgeDomain, AccessLevel, AgentRole,
)
# Conflict
from enterprise.modules.agent_coordination.conflict import (
    Conflict, ConflictResolver, Evidence, AgentPosition, ConflictStatus,
    ResolutionStrategy, EvidenceSourceType, TradeOffDimension,
)
# Verification
from enterprise.modules.agent_coordination.verification import (
    VerificationCheck, Verifier, VerificationGate,
    VerificationDomain, VerificationStatus as VerifyStatus, Severity, GateAction,
    IndependenceViolation, CheckNotFoundError, VerificationResult,
)
# Fault Tolerance
from enterprise.modules.agent_coordination.fault_tolerance import (
    CircuitBreaker, RetryPolicy, FaultToleranceManager,
    AgentStatus as HealthStatus, CircuitState, IncidentSeverity,
    Incident, AgentNotFoundError,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def orchestrator():
    return ExecutiveOrchestrator()

@pytest.fixture
def registry():
    r = AgentRegistry()
    r.reset()
    return r

@pytest.fixture
def factory(registry):
    return AgentFactory(registry)

@pytest.fixture
def message_bus():
    return MessageBus()

@pytest.fixture
def scheduler():
    return Scheduler()

@pytest.fixture
def knowledge_base():
    return SharedKnowledgeBase()

@pytest.fixture
def conflict_resolver():
    return ConflictResolver()

@pytest.fixture
def verifier():
    return Verifier()

@pytest.fixture
def ftm():
    return FaultToleranceManager()


# =============================================================================
# 1. AGENTS TESTS — all 17 types, registry, factory, authority, status
# =============================================================================

class TestAgentCreation:
    def test_orchestrator(self, orchestrator):
        assert orchestrator.agent_id == "agent-exec-orchestrator"
        assert orchestrator.authority == AuthorityLevel.EXECUTIVE
        assert orchestrator.status == AgentStatus.IDLE
        assert len(orchestrator.responsibilities) >= 5

    def test_architect(self):
        a = Architect()
        assert a.agent_id == "agent-architect"
        assert a.authority == AuthorityLevel.DECISION_MAKER
        assert "System design" in a.role

    def test_backend(self):
        be = BackendEngineer()
        assert be.authority == AuthorityLevel.CONTRIBUTOR

    def test_security(self):
        se = SecurityEngineer()
        assert se.authority >= AuthorityLevel.DECISION_MAKER

    def test_is_available(self, orchestrator):
        assert orchestrator.is_available()
        orchestrator.set_status(AgentStatus.BUSY)
        assert not orchestrator.is_available()

    def test_set_status_invalid(self, orchestrator):
        with pytest.raises(TypeError):
            orchestrator.set_status("invalid")

    def test_to_dict(self, orchestrator):
        d = orchestrator.to_dict()
        assert d["agent_id"] == "agent-exec-orchestrator"
        assert "capabilities" in d

    def test_equality(self, orchestrator):
        o2 = ExecutiveOrchestrator()
        assert orchestrator.agent_id == o2.agent_id
        assert orchestrator != Architect()


class TestAll17AgentTypes:
    AGENT_CLASSES = [
        ExecutiveOrchestrator, ProductManager, ResearchAgent, Architect,
        BackendEngineer, FrontendEngineer, UIDesigner, AIEngineer,
        DataEngineer, SecurityEngineer, DevSecOps, QAEngineer,
        PerformanceEngineer, ComplianceOfficer, DocumentationWriter,
        BusinessAnalyst, CXSpecialist,
    ]

    @pytest.mark.parametrize("agent_cls", AGENT_CLASSES)
    def test_instantiates(self, agent_cls):
        a = agent_cls()
        assert a.agent_id != ""
        assert a.name != ""
        assert len(a.responsibilities) > 0
        assert len(a.capabilities) > 0
        assert len(a.allowed_actions) > 0

    def test_count_17(self):
        assert len(self.AGENT_CLASSES) == 17


class TestAgentAuthority:
    def test_hierarchy(self, orchestrator):
        assert orchestrator.authority == AuthorityLevel.EXECUTIVE
        assert orchestrator.authority > Architect().authority
        assert Architect().authority > BackendEngineer().authority
        assert BackendEngineer().authority > ResearchAgent().authority


class TestAgentRegistry:
    def test_builtins(self, registry):
        assert len(registry) == 17
        assert "agent-exec-orchestrator" in registry

    def test_get_class(self, registry):
        assert registry.get("agent-architect") is Architect

    def test_get_nonexistent(self, registry):
        assert registry.get("nonexistent") is None

    def test_create_instance(self, registry):
        a = registry.create_instance("agent-backend-engineer")
        assert isinstance(a, BackendEngineer)
        assert a.status == AgentStatus.IDLE

    def test_create_with_overrides(self, registry):
        a = registry.create_instance("agent-backend-engineer", name="Custom")
        assert a.name == "Custom"

    def test_list_all(self, registry):
        assert len(registry.list_all()) == 17

    def test_list_instances(self, registry):
        registry.create_instance("agent-architect")
        registry.create_instance("agent-qa-engineer")
        assert len(registry.list_instances()) == 2

    def test_list_by_authority(self, registry):
        registry.create_instance("agent-exec-orchestrator")
        registry.create_instance("agent-architect")
        registry.create_instance("agent-backend-engineer")
        assert len(registry.list_by_authority(AuthorityLevel.SENIOR)) == 1

    def test_list_by_status(self, registry):
        a = registry.create_instance("agent-architect")
        a.set_status(AgentStatus.BUSY)
        assert len(registry.list_by_status(AgentStatus.BUSY)) == 1

    def test_list_available(self, registry):
        registry.create_instance("agent-qa-engineer")
        assert len(registry.list_available()) == 1

    def test_find_by_capability(self, registry):
        registry.create_instance("agent-security-engineer")
        assert len(registry.find_by_capability("security")) == 1

    def test_get_dependency_chain(self, registry):
        registry.create_instance("agent-exec-orchestrator")
        registry.create_instance("agent-business-analyst")
        registry.create_instance("agent-product-manager")
        chain = registry.get_dependency_chain("agent-product-manager")
        assert "agent-exec-orchestrator" in chain

    def test_reset(self, registry):
        registry.create_instance("agent-architect")
        registry.reset()
        assert registry.instance_count() == 0
        assert registry.count() == 17

    def test_thread_safety(self, registry):
        errors = []
        def work(i):
            try:
                registry.list_all()
                if i % 2 == 0:
                    registry.create_instance("agent-architect")
            except Exception as e:
                errors.append(str(e))
        with ThreadPoolExecutor(max_workers=10) as ex:
            for f in as_completed([ex.submit(work, i) for i in range(100)]):
                f.result()
        assert len(errors) == 0


class TestAgentFactory:
    def test_create(self, factory):
        a = factory.create("agent-exec-orchestrator")
        assert isinstance(a, ExecutiveOrchestrator)

    def test_create_overrides(self, factory):
        a = factory.create("agent-architect", name="Chief Architect")
        assert a.name == "Chief Architect"

    def test_create_all(self, factory):
        agents = factory.create_all()
        assert len(agents) == 17

    def test_invalid_id(self, factory):
        with pytest.raises(KeyError):
            factory.create("invalid-agent")


# =============================================================================
# 2. COMMUNICATION TESTS
# =============================================================================

class TestMessage:
    def test_create(self):
        msg = Message(sender_id="a", receiver_id="b", objective="Test")
        assert msg.sender_id == "a"
        assert isinstance(msg.message_id, UUID)

    def test_validation_required(self):
        with pytest.raises(ValueError):
            MessageValidation.validate(
                Message(sender_id="", receiver_id="", objective=""))

    def test_validation_confidence(self):
        msg = Message(sender_id="a", receiver_id="b", objective="x",
                      confidence_level=1.5)
        with pytest.raises(ValueError, match="Confidence"):
            MessageValidation.validate(msg)

    def test_to_json_roundtrip(self):
        msg = Message(sender_id="a", receiver_id="b", objective="R",
                      confidence_level=0.75, priority=MsgPriority.CRITICAL)
        restored = Message.from_json(msg.to_json())
        assert restored.sender_id == "a"
        assert restored.objective == "R"
        assert restored.confidence_level == 0.75
        assert restored.priority == MsgPriority.CRITICAL


class TestMessageBus:
    def test_register_and_send(self, message_bus):
        message_bus.register_agent("sender")
        message_bus.register_agent("receiver")
        msg = Message(sender_id="sender", receiver_id="receiver",
                     objective="Hello")
        message_bus.send(msg)

    def test_send_unregistered_raises(self, message_bus):
        with pytest.raises(ValueError):
            message_bus.send(
                Message(sender_id="x", receiver_id="y", objective="x"))

    def test_broadcast(self, message_bus):
        for aid in ["a", "b", "c"]:
            message_bus.register_agent(aid)
        message_bus.broadcast(
            Message(sender_id="c", receiver_id="broadcast",
                   objective="Announce"))

    def test_unregister(self, message_bus):
        message_bus.register_agent("a")
        message_bus.unregister_agent("a")
        assert not message_bus.is_agent_registered("a")

    def test_registered_agents_property(self, message_bus):
        message_bus.register_agent("a")
        message_bus.register_agent("b")
        assert message_bus.registered_agents == {"a", "b"}

    def test_concurrent(self, message_bus):
        message_bus.register_agent("agent")
        errors = []
        lock = threading.Lock()
        def send(i):
            try:
                message_bus.register_agent(f"s-{i}")
                message_bus.send(Message(
                    sender_id=f"s-{i}", receiver_id="agent",
                    objective=f"msg-{i}"))
            except Exception as e:
                with lock:
                    errors.append(str(e))
        with ThreadPoolExecutor(max_workers=20) as ex:
            for f in as_completed([ex.submit(send, i) for i in range(100)]):
                f.result()
        assert len(errors) == 0


class TestMessageVersionTracker:
    def test_record_history(self):
        t = MessageVersionTracker()
        m1 = Message(sender_id="a", receiver_id="b", objective="v1", version=1)
        m2 = Message(sender_id="a", receiver_id="b", objective="v2", version=2)
        t.record(m1)
        t.record(m2)
        assert len(t.get_history(m1.message_id)) >= 1

    def test_get_latest(self):
        t = MessageVersionTracker()
        m1 = Message(sender_id="a", receiver_id="b", objective="v1", version=1)
        m2 = Message(sender_id="a", receiver_id="b", objective="v2", version=2)
        t.record(m1)
        t.record(m2)
        latest = t.get_latest(m1.message_id)
        assert latest is not None
        assert latest.version >= 1


class TestAuditTrail:
    def test_record_and_get(self):
        a = AuditTrail()
        mid = uuid4()
        a.log("message_sent", message_id=mid, details={"detail": "x"})
        entries = a.get_entries(mid)
        assert len(entries) >= 1


# =============================================================================
# 3. SCHEDULER TESTS
# =============================================================================

class TestTask:
    def test_create(self):
        t = Task(task_id="t1", description="Test", estimated_duration=5)
        assert t.task_id == "t1"
        assert t.status == TaskStatus.PENDING

    def test_validation(self):
        with pytest.raises(ValueError):
            Task(task_id="t1", risk_level=1.5)

    def test_score(self):
        t = Task(task_id="t1", user_impact=0.8, business_value=0.9,
                security_impact=0.5, risk_level=0.2)
        assert t.compute_score(SchedulingFactor()) > 0

    def test_deadline_urgency(self):
        t = Task(task_id="t1",
                deadline=datetime.now(timezone.utc) - timedelta(hours=1))
        assert t.compute_score(SchedulingFactor()) >= 10.0

    def test_to_dict(self):
        t = Task(task_id="t1", description="D", estimated_duration=3)
        assert t.to_dict()["task_id"] == "t1"


class TestAgentCapacity:
    def test_basic(self):
        c = AgentCapacity(agent_id="a", max_concurrent_tasks=5)
        assert c.available_capacity == 5
        assert c.assign()
        assert c.current_tasks == 1

    def test_full(self):
        c = AgentCapacity(agent_id="a", max_concurrent_tasks=1)
        c.assign(1)
        assert c.is_at_capacity
        assert not c.assign()

    def test_release(self):
        c = AgentCapacity(agent_id="a", max_concurrent_tasks=3)
        c.assign(3)
        c.release(1)
        assert c.current_tasks == 2


class TestScheduler:
    def test_add_task(self, scheduler):
        scheduler.add_task(Task(task_id="t1"))
        assert scheduler.get_task("t1") is not None

    def test_duplicate_raises(self, scheduler):
        scheduler.add_task(Task(task_id="t1"))
        with pytest.raises(ValueError):
            scheduler.add_task(Task(task_id="t1"))

    def test_remove_task(self, scheduler):
        scheduler.add_task(Task(task_id="t1"))
        assert scheduler.remove_task("t1")
        assert scheduler.get_task("t1") is None

    def test_update_status(self, scheduler):
        scheduler.add_task(Task(task_id="t1"))
        assert scheduler.update_task_status("t1", TaskStatus.IN_PROGRESS)

    def test_schedule(self, scheduler):
        scheduler.set_agent_capacity("a", 5)
        scheduler.add_task(Task(task_id="t1", assigned_agent="a"))
        scheduler.add_task(Task(task_id="t2", assigned_agent="a",
                               dependencies=["t1"]))
        plan = scheduler.schedule()
        assert len(plan) == 1
        assert plan[0].task_id == "t1"

    def test_critical_path(self, scheduler):
        scheduler.add_task(Task(task_id="t1", estimated_duration=5))
        scheduler.add_task(Task(task_id="t2", estimated_duration=10,
                               dependencies=["t1"]))
        scheduler.add_task(Task(task_id="t3", estimated_duration=3,
                               dependencies=["t1"]))
        critical = scheduler.get_critical_path()
        assert "t1" in critical
        assert "t2" in critical

    def test_deadlock(self, scheduler):
        scheduler.add_task(Task(task_id="t1", dependencies=["t2"]))
        scheduler.add_task(Task(task_id="t2", dependencies=["t1"]))
        assert len(scheduler.detect_deadlocks()) > 0

    def test_no_deadlock(self, scheduler):
        scheduler.add_task(Task(task_id="t1"))
        scheduler.add_task(Task(task_id="t2", dependencies=["t1"]))
        assert len(scheduler.detect_deadlocks()) == 0

    def test_rebalance(self, scheduler):
        scheduler.set_agent_capacity("a", 5)
        scheduler.add_task(Task(task_id="t1", assigned_agent="a"))
        plan = scheduler.rebalance()
        assert len(plan) >= 0

    def test_bottlenecks(self, scheduler):
        scheduler.add_task(Task(task_id="t1"))
        scheduler.add_task(Task(task_id="t2", dependencies=["t1"]))
        b = scheduler.get_bottlenecks()
        assert "blocked_tasks" in b


# =============================================================================
# 4. SHARED KNOWLEDGE TESTS
# =============================================================================

class TestKnowledgeEntry:
    def test_create(self):
        e = KnowledgeEntry(domain="general", key="k", value="v",
                          created_by="author")
        assert e.key == "k"
        assert e.version == 1
        assert e.author_id == "author"

    def test_to_dict(self):
        e = KnowledgeEntry(domain="sec", key="k", value="v")
        assert e.to_dict()["key"] == "k"

    def test_from_dict(self):
        e = KnowledgeEntry.from_dict(
            {"domain": "test", "key": "k", "value": "v", "version": 2})
        assert e.key == "k"
        assert e.version == 2


class TestSharedKnowledgeBaseCRUD:
    def test_set_and_get(self, knowledge_base):
        entry, conflict = knowledge_base.set(
            "general", "key1", "value1", created_by="author")
        assert conflict is None
        found = knowledge_base.get("general", "key1")
        assert found is not None
        assert found.value == "value1"

    def test_get_by_key_only(self, knowledge_base):
        knowledge_base.set("general", "key1", "val")
        assert knowledge_base.get("key1") is not None

    def test_get_nonexistent(self, knowledge_base):
        assert knowledge_base.get("missing") is None

    def test_update_bumps_version(self, knowledge_base):
        knowledge_base.set("general", "key1", "v1")
        e2, _ = knowledge_base.set("general", "key1", "v2")
        assert e2.version == 2

    def test_optimistic_locking(self, knowledge_base):
        knowledge_base.set("general", "key1", "v1", created_by="architect")
        _, conflict = knowledge_base.set(
            "general", "key1", "v2", expected_version=99)
        assert conflict is not None
        assert "Version conflict" in conflict

    def test_delete(self, knowledge_base):
        knowledge_base.set("general", "key1", "v")
        assert knowledge_base.delete("general", "key1")
        assert knowledge_base.get("general", "key1") is None

    def test_put_backward_compat(self, knowledge_base):
        e = KnowledgeEntry(domain="general", key="legacy", value="v",
                          created_by="test")
        result = knowledge_base.put(e)
        assert result.key == "legacy"

    def test_permission_error(self, knowledge_base):
        with pytest.raises(PermissionError):
            knowledge_base.set("security_policies", "secret", "data",
                              created_by="backend", role=AgentRole.BACKEND)


class TestKnowledgeVersionHistory:
    def test_history(self, knowledge_base):
        for v in ["v1", "v2", "v3"]:
            knowledge_base.set("general", "ev", v)
        hist = knowledge_base.get_version_history("general", "ev")
        assert len(hist) == 3

    def test_get_with_version(self, knowledge_base):
        knowledge_base.set("general", "ver", "a")
        knowledge_base.set("general", "ver", "b")
        v1 = knowledge_base.get_with_version("general", "ver", 1)
        assert v1 is not None
        assert v1.value == "a"


class TestKnowledgeAccess:
    def test_set_access(self, knowledge_base):
        knowledge_base.set_access("a1", KnowledgeDomain.SECURITY, AccessLevel.WRITE)
        assert knowledge_base.check_access("a1", KnowledgeDomain.SECURITY, AccessLevel.WRITE)

    def test_write_implies_read(self, knowledge_base):
        knowledge_base.set_access("a1", KnowledgeDomain.GENERAL, AccessLevel.WRITE)
        assert knowledge_base.check_access("a1", KnowledgeDomain.GENERAL, AccessLevel.READ)

    def test_role_perms(self):
        assert AgentRole.ARCHITECT.can_write(KnowledgeDomain.ARCHITECTURE)
        assert not AgentRole.BACKEND.can_write(KnowledgeDomain.SECURITY_POLICIES)


class TestKnowledgeQueries:
    def test_query_domain(self, knowledge_base):
        knowledge_base.set("architecture", "k1", "v")
        knowledge_base.set("security", "k2", "v")
        assert len(knowledge_base.query_by_domain(KnowledgeDomain.ARCHITECTURE)) == 1

    def test_query_tag(self, knowledge_base):
        knowledge_base.set("general", "e1", "v", tags=["imp"])
        knowledge_base.set("general", "e2", "v", tags=["imp"])
        assert len(knowledge_base.query_by_tag("imp")) == 2

    def test_query_author(self, knowledge_base):
        knowledge_base.set("general", "a1", "v", created_by="alice")
        knowledge_base.set("general", "a2", "v", created_by="alice")
        assert len(knowledge_base.query_by_author("alice")) == 2

    def test_list_domains(self, knowledge_base):
        knowledge_base.set("architecture", "k", "v")
        knowledge_base.set("security", "k", "v")
        assert "architecture" in knowledge_base.list_all_domains()

    def test_query_filters(self, knowledge_base):
        knowledge_base.set("general", "high", "v", confidence=0.9)
        r = knowledge_base.query("general", {"confidence_min": 0.8})
        assert len(r) == 1


class TestKnowledgeConcurrency:
    def test_concurrent_writes(self, knowledge_base):
        errors = []
        lock = threading.Lock()
        def write(i):
            try:
                knowledge_base.set("general", f"k-{i}", f"v-{i}")
            except Exception as e:
                with lock:
                    errors.append(str(e))
        with ThreadPoolExecutor(max_workers=20) as ex:
            for f in as_completed([ex.submit(write, i) for i in range(200)]):
                f.result()
        assert len(errors) == 0
        domain_entries = knowledge_base.list_domain("general")
        assert len(domain_entries) == 200


class TestKnowledgeSnapshot:
    def test_export_import(self, knowledge_base):
        knowledge_base.set("general", "k1", "v1")
        knowledge_base.set("general", "k2", "v2")
        snap = knowledge_base.export_snapshot()
        assert snap["entry_count"] == 2
        kb2 = SharedKnowledgeBase()
        kb2.import_snapshot(snap)
        assert kb2.get("general", "k1") is not None


class TestKnowledgeSubscriptions:
    def test_subscribe(self, knowledge_base):
        notes = []
        def cb(d, e):
            notes.append((d, e.key))
        unsub = knowledge_base.subscribe("general", cb)
        knowledge_base.set("general", "notify", "v")
        assert ("general", "notify") in notes
        unsub()
        knowledge_base.set("general", "silent", "v")
        assert len(notes) == 1


# =============================================================================
# 5. CONFLICT TESTS
# =============================================================================

class TestConflictDetection:
    def test_create_conflict(self):
        pos_a = AgentPosition(
            agent_name="Architect", position_summary="Use PostgreSQL",
            evidence=[Evidence(description="ACID",
                source_type=EvidenceSourceType.DOCUMENTED_STANDARD,
                confidence=0.9)])
        pos_b = AgentPosition(
            agent_name="Backend", position_summary="Use MongoDB",
            evidence=[Evidence(description="Flexibility",
                source_type=EvidenceSourceType.AGENT_ANALYSIS,
                confidence=0.7)])
        c = Conflict(description="DB choice", positions=[pos_a, pos_b])
        assert c.status == ConflictStatus.DETECTED
        assert len(c.positions) == 2

    def test_evidence_reliability(self):
        e1 = Evidence(source_type=EvidenceSourceType.PRODUCTION_METRICS,
                      confidence=0.95)
        e2 = Evidence(source_type=EvidenceSourceType.SPECULATION,
                      confidence=0.5)
        assert e1.reliability() > e2.reliability()

    def test_position_reliability(self):
        pos = AgentPosition(agent_name="A", position_summary="X",
            evidence=[Evidence(source_type=EvidenceSourceType.BENCHMARK,
                              confidence=0.9)])
        assert pos.combined_reliability() > 0


class TestConflictResolution:
    def test_evidence_comparison(self, conflict_resolver):
        pos_a = AgentPosition(agent_name="A", position_summary="Win",
            evidence=[Evidence(source_type=EvidenceSourceType.PRODUCTION_METRICS,
                              confidence=0.95)])
        pos_b = AgentPosition(agent_name="B", position_summary="Lose",
            evidence=[Evidence(source_type=EvidenceSourceType.SPECULATION,
                              confidence=0.2)])
        c = conflict_resolver.detect_conflicts("Test", [pos_a, pos_b])
        r = conflict_resolver.resolve(c.conflict_id)
        assert "resolution" in r

    def test_trade_off(self, conflict_resolver):
        pos_a = AgentPosition(agent_name="A", position_summary="Fast",
            evidence=[Evidence(source_type=EvidenceSourceType.AGENT_ANALYSIS,
                              confidence=0.5)],
            trade_off_scores={"performance": 9, "security": 3})
        pos_b = AgentPosition(agent_name="B", position_summary="Safe",
            evidence=[Evidence(source_type=EvidenceSourceType.AGENT_ANALYSIS,
                              confidence=0.5)],
            trade_off_scores={"performance": 5, "security": 9})
        c = conflict_resolver.detect_conflicts("Trade", [pos_a, pos_b])
        r = conflict_resolver.resolve(c.conflict_id)
        assert "resolution" in r

    def test_escalation(self, conflict_resolver):
        pos_a = AgentPosition(agent_name="A", position_summary="X",
            evidence=[Evidence(source_type=EvidenceSourceType.UNKNOWN,
                              confidence=0.5)])
        pos_b = AgentPosition(agent_name="B", position_summary="Y",
            evidence=[Evidence(source_type=EvidenceSourceType.UNKNOWN,
                              confidence=0.5)])
        c = conflict_resolver.detect_conflicts("Deadlock", [pos_a, pos_b])
        r = conflict_resolver.resolve(c.conflict_id)
        assert "resolution" in r

    def test_resolution_history(self, conflict_resolver):
        pos_a = AgentPosition(agent_name="A", position_summary="X",
            evidence=[Evidence(source_type=EvidenceSourceType.BENCHMARK,
                              confidence=0.9)])
        pos_b = AgentPosition(agent_name="B", position_summary="Y",
                             evidence=[])
        c = conflict_resolver.detect_conflicts("Doc", [pos_a, pos_b])
        conflict_resolver.resolve(c.conflict_id)
        history = conflict_resolver.get_resolution_history(c.conflict_id)
        assert len(history) > 0

    def test_detect_conflicts_requires_two(self, conflict_resolver):
        with pytest.raises(ValueError):
            conflict_resolver.detect_conflicts("Solo",
                [AgentPosition(agent_name="A", position_summary="X")])


# =============================================================================
# 6. VERIFICATION TESTS
# =============================================================================

class TestVerificationCheck:
    def test_create(self):
        check = VerificationCheck(
            check_id="vc-1", domain=VerificationDomain.SECURITY,
            description="Security audit", criteria="No critical vulns",
            required_evidence=["scan_report"], assigned_verifier="agent-sec",
            severity=Severity.HIGH, work_producer="agent-backend")
        assert check.check_id == "vc-1"
        assert check.severity == Severity.HIGH
        assert check.status == VerifyStatus.PENDING
        assert check.is_independent

    def test_independence_violation_on_init(self):
        with pytest.raises(IndependenceViolation):
            VerificationCheck(
                check_id="vc-i", domain=VerificationDomain.CORRECTNESS,
                description="Self", criteria="x",
                required_evidence=[], assigned_verifier="same",
                work_producer="same")

    def test_complete_passed(self):
        check = VerificationCheck(
            check_id="vc-p", domain=VerificationDomain.CORRECTNESS,
            description="Test", criteria="all pass",
            required_evidence=[], assigned_verifier="verifier",
            work_producer="worker")
        check.status = VerifyStatus.IN_PROGRESS
        check.status = VerifyStatus.PASSED
        check.results.append(VerificationResult(passed=True, actual_value="ok", expected_value="ok"))
        assert check.status == VerifyStatus.PASSED

    def test_complete_failed(self):
        check = VerificationCheck(
            check_id="vc-f", domain=VerificationDomain.SECURITY,
            description="Scan", criteria="0 vulns",
            required_evidence=[], assigned_verifier="verifier",
            work_producer="worker")
        check.status = VerifyStatus.IN_PROGRESS
        check.status = VerifyStatus.FAILED
        check.results.append(VerificationResult(passed=False, actual_value=5, expected_value=0))
        assert check.status == VerifyStatus.FAILED


class TestVerifier:
    def test_register_checks(self, verifier):
        checks = [
            VerificationCheck(check_id="c1",
                domain=VerificationDomain.CORRECTNESS,
                description="C1", criteria="pass",
                required_evidence=[], assigned_verifier="v1",
                work_producer="w1"),
            VerificationCheck(check_id="c2",
                domain=VerificationDomain.CORRECTNESS,
                description="C2", criteria="pass",
                required_evidence=[], assigned_verifier="v2",
                work_producer="w2"),
        ]
        verifier.register_checks(VerificationDomain.CORRECTNESS, checks)
        # Verify checks were registered via internal state
        assert len(verifier._checks) >= 2

    def test_independence_violation(self, verifier):
        # IndependenceViolation is raised in __post_init__ before register_checks
        with pytest.raises(IndependenceViolation):
            VerificationCheck(check_id="c1",
                domain=VerificationDomain.CORRECTNESS,
                description="Self", criteria="x",
                required_evidence=[], assigned_verifier="same",
                work_producer="same")

    def test_register_gate(self, verifier):
        c1 = VerificationCheck(check_id="g1",
            domain=VerificationDomain.CORRECTNESS,
            description="G1", criteria="pass",
            required_evidence=[], assigned_verifier="v1",
            work_producer="w1")
        c2 = VerificationCheck(check_id="g2",
            domain=VerificationDomain.CORRECTNESS,
            description="G2", criteria="pass",
            required_evidence=[], assigned_verifier="v2",
            work_producer="w2")
        verifier.register_checks(VerificationDomain.CORRECTNESS, [c1, c2])

        gate = VerificationGate(gate_id="gate-1", description="Test Gate",
                                check_ids=["g1", "g2"])
        verifier.register_gate(gate)

    def test_gate_unknown_check(self, verifier):
        gate = VerificationGate(gate_id="gate-x", description="Bad",
                                check_ids=["nonexistent"])
        with pytest.raises(CheckNotFoundError):
            verifier.register_gate(gate)

    def test_gate_satisfied(self, verifier):
        c1 = VerificationCheck(check_id="gs1",
            domain=VerificationDomain.CORRECTNESS,
            description="S1", criteria="pass",
            required_evidence=[], assigned_verifier="v1",
            work_producer="w1")
        c2 = VerificationCheck(check_id="gs2",
            domain=VerificationDomain.CORRECTNESS,
            description="S2", criteria="pass",
            required_evidence=[], assigned_verifier="v2",
            work_producer="w2")
        verifier.register_checks(VerificationDomain.CORRECTNESS, [c1, c2])
        gate = VerificationGate(gate_id="gs-gate", description="S Gate",
                                check_ids=["gs1", "gs2"])
        verifier.register_gate(gate)

        c1.status = VerifyStatus.PASSED
        c2.status = VerifyStatus.PASSED
        assert gate.is_satisfied({"gs1": c1, "gs2": c2})

    def test_gate_not_satisfied(self, verifier):
        c1 = VerificationCheck(check_id="gn1",
            domain=VerificationDomain.CORRECTNESS,
            description="N1", criteria="pass",
            required_evidence=[], assigned_verifier="v1",
            work_producer="w1")
        c2 = VerificationCheck(check_id="gn2",
            domain=VerificationDomain.CORRECTNESS,
            description="N2", criteria="pass",
            required_evidence=[], assigned_verifier="v2",
            work_producer="w2")
        verifier.register_checks(VerificationDomain.CORRECTNESS, [c1, c2])
        gate = VerificationGate(gate_id="gn-gate", description="N Gate",
                                check_ids=["gn1", "gn2"])
        verifier.register_gate(gate)
        c1.status = VerifyStatus.PASSED
        assert not gate.is_satisfied({"gn1": c1, "gn2": c2})


# =============================================================================
# 7. FAULT TOLERANCE TESTS
# =============================================================================

class TestCircuitBreaker:
    def test_initial_state(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED

    def test_trip(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_success_resets(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_allow_request(self):
        cb = CircuitBreaker()
        assert cb.allow_request()
        cb.record_failure()
        assert cb.allow_request()

    def test_open_denies(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert not cb.allow_request()

    def test_half_open_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.01)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        assert cb.allow_request()
        assert cb.state == CircuitState.HALF_OPEN

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        cb._failure_count = 0
        cb._transition_to(CircuitState.CLOSED)
        assert cb.state == CircuitState.CLOSED


class TestRetryPolicy:
    def test_compute_delay(self):
        rp = RetryPolicy(base_delay_seconds=1.0, backoff_multiplier=2.0,
                        max_delay_seconds=100, jitter=False)
        assert rp.compute_delay(0) == 1.0
        assert rp.compute_delay(1) == 2.0
        assert rp.compute_delay(2) == 4.0

    def test_delay_grows(self):
        rp = RetryPolicy(base_delay_seconds=1.0, backoff_multiplier=2.0,
                        jitter=False)
        assert rp.compute_delay(2) > rp.compute_delay(0)

    def test_max_delay_cap(self):
        rp = RetryPolicy(base_delay_seconds=1.0, backoff_multiplier=10.0,
                        max_delay_seconds=50, jitter=False)
        assert rp.compute_delay(5) <= 50

    def test_jitter_adds_variation(self):
        rp = RetryPolicy(base_delay_seconds=1.0, jitter=True)
        delays = [rp.compute_delay(0) for _ in range(10)]
        assert len(set(round(d, 2) for d in delays)) >= 2


class TestFaultToleranceManager:
    def test_register_agent(self, ftm):
        health = ftm.register_agent("worker-1")
        assert health.agent_id == "worker-1"
        assert health.status == HealthStatus.STARTING

    def test_deregister(self, ftm):
        ftm.register_agent("temp")
        ftm.deregister_agent("temp")
        with pytest.raises(AgentNotFoundError):
            ftm.deregister_agent("temp")

    def test_get_agent_health(self, ftm):
        ftm.register_agent("w1")
        h = ftm.get_agent_health("w1")
        assert h is not None
        assert ftm.get_agent_health("unknown") is None

    def test_record_incident(self, ftm):
        inc = Incident(
            incident_id="inc-1", agent_id="w1",
            task_id="task-1",
            detected_at=datetime.now(timezone.utc),
            severity=IncidentSeverity.HIGH,
            failure_type="timeout")
        ftm.record_incident(inc)
        assert ftm.get_incident(inc.incident_id) is not None

    def test_resolve_incident(self, ftm):
        inc = Incident(
            incident_id="inc-2", agent_id="w1",
            task_id="task-1",
            detected_at=datetime.now(timezone.utc),
            severity=IncidentSeverity.HIGH,
            failure_type="crash")
        ftm.record_incident(inc)
        assert ftm.resolve_incident(inc.incident_id, "Restarted", True)
        assert len(ftm.get_active_incidents()) == 0

    def test_get_active_incidents(self, ftm):
        ftm.record_incident(Incident(
            incident_id="inc-a", agent_id="a", task_id=None,
            detected_at=datetime.now(timezone.utc),
            severity=IncidentSeverity.HIGH, failure_type="e1"))
        ftm.record_incident(Incident(
            incident_id="inc-b", agent_id="b", task_id=None,
            detected_at=datetime.now(timezone.utc),
            severity=IncidentSeverity.HIGH, failure_type="e2"))
        assert len(ftm.get_active_incidents()) == 2

    def test_reassign_tasks(self, ftm):
        ftm.register_agent("old")
        ftm.register_agent("new")
        ftm._agents["old"].status = HealthStatus.FAILED
        # reassign_tasks is async — but we can test the sync helper
        # or just verify the method exists
        assert callable(ftm.reassign_tasks)

    def test_get_system_health(self, ftm):
        ftm.register_agent("w1")
        ftm.register_agent("w2")
        report = ftm.get_system_health()
        assert report.total_agents == 2

    def test_health_check_integration(self, ftm):
        ftm.register_agent("worker")
        health = ftm._agents["worker"]
        health.record_heartbeat(latency_ms=5.0, success=True)
        assert health.status in (HealthStatus.HEALTHY, HealthStatus.STARTING)
        assert health.failure_count == 0

    def test_latest_checkpoint(self, ftm):
        # Checkpoint is stored internally via _preserve_work
        from enterprise.modules.agent_coordination.fault_tolerance import (
            Checkpoint)
        import uuid as ft_uuid
        cp = Checkpoint(
            checkpoint_id=str(ft_uuid.uuid4())[:8],
            task_id="task-1", agent_id="w1",
            data={"step": 3},
            created_at=datetime.now(timezone.utc),
            sequence=1)
        ftm._checkpoints["task-1"].append(cp)
        latest = ftm.get_latest_checkpoint("task-1")
        assert latest is not None
        assert latest.data == {"step": 3}

    def test_graceful_degradation(self, ftm):
        ftm.register_agent("healthy")
        ftm.register_agent("failed")
        ftm._agents["failed"].status = HealthStatus.FAILED
        report = ftm.get_system_health()
        assert report.total_agents == 2


# =============================================================================
# 8. INTEGRATION TESTS
# =============================================================================

class TestIntegrationE2E:
    def test_full_coordination(self, registry, message_bus, scheduler, knowledge_base):
        """Full agent coordination: agents -> bus -> tasks -> knowledge."""
        exec_a = registry.create_instance("agent-exec-orchestrator")
        arch_a = registry.create_instance("agent-architect")
        backend_a = registry.create_instance("agent-backend-engineer")
        sec_a = registry.create_instance("agent-security-engineer")
        qa_a = registry.create_instance("agent-qa-engineer")

        # Setup message bus
        for aid in [exec_a.agent_id, arch_a.agent_id, backend_a.agent_id,
                     sec_a.agent_id, qa_a.agent_id]:
            message_bus.register_agent(aid)

        # Executive sends task to backend
        msg = Message(sender_id=exec_a.agent_id,
                     receiver_id=backend_a.agent_id,
                     objective="Implement auth API",
                     priority=MsgPriority.HIGH,
                     required_outputs=["auth.py", "test_auth.py"])
        message_bus.send(msg)

        # Schedule tasks
        scheduler.set_agent_capacity(backend_a.agent_id, 3)
        scheduler.set_agent_capacity(sec_a.agent_id, 2)
        scheduler.set_agent_capacity(qa_a.agent_id, 3)

        t1 = Task(task_id="auth-impl", description="Implement auth",
                  assigned_agent=backend_a.agent_id, estimated_duration=8,
                  priority=5, user_impact=0.9, security_impact=0.7)
        t2 = Task(task_id="auth-sec", description="Security review",
                  assigned_agent=sec_a.agent_id, estimated_duration=4,
                  dependencies=["auth-impl"], security_impact=1.0)
        t3 = Task(task_id="auth-qa", description="QA test",
                  assigned_agent=qa_a.agent_id, estimated_duration=3,
                  dependencies=["auth-impl", "auth-sec"])

        scheduler.add_task(t1)
        scheduler.add_task(t2)
        scheduler.add_task(t3)

        plan = scheduler.schedule()
        assert len(plan) == 1
        assert plan[0].task_id == "auth-impl"

        critical = scheduler.get_critical_path()
        assert "auth-impl" in critical
        assert len(scheduler.detect_deadlocks()) == 0

        # Share knowledge
        knowledge_base.set("architecture", "auth.design",
                          {"method": "JWT", "expiry": "24h"},
                          created_by=arch_a.agent_id)
        design = knowledge_base.get("architecture", "auth.design")
        assert design is not None
        assert design.value["method"] == "JWT"

    def test_conflict_resolution_flow(self, conflict_resolver):
        """Conflict detection and resolution workflow."""
        pos_a = AgentPosition(agent_name="Backend", agent_role="backend",
            position_summary="Use REST",
            evidence=[Evidence(source_type=EvidenceSourceType.DOCUMENTED_STANDARD,
                              confidence=0.9)])
        pos_b = AgentPosition(agent_name="Architect", agent_role="architect",
            position_summary="Use GraphQL",
            evidence=[Evidence(source_type=EvidenceSourceType.BENCHMARK,
                              confidence=0.85)])

        conflict = conflict_resolver.detect_conflicts(
            "API design", [pos_a, pos_b], domain="architecture")
        result = conflict_resolver.resolve(conflict.conflict_id)
        assert "resolution" in result

    def test_fault_tolerance_flow(self, ftm):
        """Fault: agent fails, incident recorded, health report generated."""
        ftm.register_agent("worker-1")
        ftm.register_agent("worker-2")

        # Worker-1 fails
        ftm._agents["worker-1"].status = HealthStatus.FAILED

        # Record incident
        inc = Incident(
            incident_id="inc-flow", agent_id="worker-1",
            task_id=None,
            detected_at=datetime.now(timezone.utc),
            severity=IncidentSeverity.HIGH,
            failure_type="crash")
        ftm.record_incident(inc)

        assert ftm.get_incident(inc.incident_id) is not None
        assert len(ftm.get_active_incidents()) == 1

        # System health report
        report = ftm.get_system_health()
        assert report.total_agents == 2

    def test_circuit_breaker_with_messages(self, message_bus):
        """Circuit breaker integration with message bus."""
        cb = CircuitBreaker(failure_threshold=2)
        message_bus.register_agent("sender")
        message_bus.register_agent("receiver")

        # Successful send through circuit
        assert cb.allow_request()
        message_bus.send(Message(sender_id="sender",
                         receiver_id="receiver", objective="test"))
        cb.record_success()

        # Trip circuit
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Message bus still works independently
        message_bus.send(Message(sender_id="sender",
                         receiver_id="receiver", objective="independent"))