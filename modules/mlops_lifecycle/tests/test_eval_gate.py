"""Tests for the Evaluation Gate Engine (quality gates on metrics)."""

from modules.mlops_lifecycle.eval_gate_engine import (
    Comparison,
    EvalGateEngine,
    EvaluationPipeline,
    GatePolicy,
    GateResult,
    create_eval_gate_engine,
)


def test_create_eval_gate_engine_returns_default_instance():
    eng = create_eval_gate_engine()
    assert isinstance(eng, EvalGateEngine)


def test_policy_passes_when_metric_meets_threshold():
    policy = GatePolicy(name="accuracy_min", metric="accuracy", operator=Comparison.GE, threshold=0.9)
    result = policy.evaluate(_report({"accuracy": 0.95}))
    assert isinstance(result, GateResult)
    assert result.passed is True


def test_policy_fails_when_threshold_not_met():
    policy = GatePolicy(name="accuracy_min", metric="accuracy", operator=Comparison.GE, threshold=0.9)
    result = policy.evaluate(_report({"accuracy": 0.6}))
    assert result.passed is False


def test_policy_fails_when_metric_missing():
    policy = GatePolicy(name="latency_max", metric="latency_p99", operator=Comparison.LE, threshold=150.0)
    result = policy.evaluate(_report({"accuracy": 0.9}))
    assert result.passed is False
    assert "not present" in result.reason


def _report(metrics):
    from modules.mlops_lifecycle.eval_gate_engine import EvaluationReport

    return EvaluationReport(version="v1", metrics=metrics)


def test_gate_all_pass_gates():
    eng = EvalGateEngine()
    pipeline = EvaluationPipeline(
        name="release",
        policies=[
            GatePolicy(name="acc", metric="accuracy", operator=Comparison.GE, threshold=0.9),
            GatePolicy(name="err", metric="error_rate", operator=Comparison.LE, threshold=0.02),
        ],
    )
    results = eng.run_pipeline(pipeline, {"accuracy": 0.95, "error_rate": 0.005}, version="v2")
    assert EvalGateEngine.passed(results) is True
    assert len(results) == 2


def test_gate_blocks_when_any_policy_fails():
    eng = EvalGateEngine()
    pipeline = EvaluationPipeline(
        name="release",
        policies=[GatePolicy(name="acc", metric="accuracy", operator=Comparison.GE, threshold=0.9)],
    )
    results = eng.run_pipeline(pipeline, {"accuracy": 0.7}, version="v3")
    summary = eng.gate_summary(results)
    assert summary["all_passed"] is False
    assert summary["failed"] == 1


def test_pipeline_registry_and_history():
    eng = EvalGateEngine()
    pipe = EvaluationPipeline(name="p", policies=[GatePolicy(name="a", metric="m", operator=Comparison.GE, threshold=1.0)])
    pid = eng.register_pipeline(pipe)
    assert eng.get_pipeline(pid).name == "p"
    eng.run_pipeline(pid, {"m": 2.0})
    assert len(eng.history()) == 1
