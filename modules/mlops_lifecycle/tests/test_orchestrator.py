"""Tests for the Lifecycle Orchestrator pipeline state machine."""

from modules.mlops_lifecycle.lifecycle_orchestrator import (
    LifecycleOrchestrator,
    OrchestrationPolicy,
    PipelineStage,
    RunStatus,
    StageStatus,
    create_lifecycle_orchestrator,
)


def test_create_lifecycle_orchestrator_returns_default_instance():
    orch = create_lifecycle_orchestrator()
    assert isinstance(orch, LifecycleOrchestrator)


def test_run_pipeline_sequential_success():
    orch = LifecycleOrchestrator()
    run = orch.create_run("exp_run", policy=OrchestrationPolicy(stop_on_failure=True))
    order = []

    def make(step):
        def fn():
            order.append(step)
            return {"step": step}
        return fn

    status = orch.run_pipeline(
        run,
        {
            PipelineStage.EXPERIMENT: make("experiment"),
            PipelineStage.TRAINING: make("training"),
            PipelineStage.EVALUATION: make("evaluation"),
        },
    )
    assert status is RunStatus.SUCCEEDED
    assert order == ["experiment", "training", "evaluation"]
    assert run.result_for(PipelineStage.TRAINING).status is StageStatus.PASSED


def test_run_pipeline_stops_on_failure_when_configured():
    orch = LifecycleOrchestrator()
    run = orch.create_run("fail_run", policy=OrchestrationPolicy(stop_on_failure=True))
    called = []

    def failing():
        called.append("failing")
        raise RuntimeError("gate failed")

    def after():
        called.append("after")
        return {}

    status = orch.run_pipeline(
        run,
        {PipelineStage.EXPERIMENT: failing, PipelineStage.TRAINING: after},
    )
    assert status is RunStatus.FAILED
    assert "after" not in called
    assert run.result_for(PipelineStage.EXPERIMENT).status is StageStatus.FAILED


def test_execute_stage_retries_then_succeeds():
    orch = LifecycleOrchestrator()
    run = orch.create_run("retry_run", policy=OrchestrationPolicy(max_retries=3))
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")
        return {"ok": True}

    result = orch.execute_stage(run, PipelineStage.TRAINING, flaky)
    assert result.status is StageStatus.PASSED
    assert result.retries == 2
    assert run.context.get("ok") is True


def test_stage_order_follows_policy():
    orch = LifecycleOrchestrator()
    policy = OrchestrationPolicy(stage_order=[PipelineStage.PROMOTION, PipelineStage.EXPERIMENT])
    run = orch.create_run("ordered", policy=policy)
    order = []
    orch.run_pipeline(
        run,
        {
            PipelineStage.PROMOTION: (lambda: order.append("promo") or {}),
            PipelineStage.EXPERIMENT: (lambda: order.append("exp") or {}),
        },
    )
    assert order == ["promo", "exp"]


def test_list_runs_and_run_serialization():
    orch = LifecycleOrchestrator()
    run = orch.create_run("ser")
    orch.execute_stage(run, PipelineStage.EVALUATION, lambda: {"acc": 0.95})
    assert len(orch.list_runs()) == 1
    assert orch.get_run(run.run_id).run_id == run.run_id
    data = run.to_dict()
    assert data["name"] == "ser"
    assert PipelineStage.EVALUATION.value in data["stage_results"]
    assert data["stage_results"][PipelineStage.EVALUATION.value]["status"] == StageStatus.PASSED.value
