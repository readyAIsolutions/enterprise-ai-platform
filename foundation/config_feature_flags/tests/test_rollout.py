"""
Tests for RolloutManager.
"""

import time

import pytest

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[5]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from enterprise.foundation.config_feature_flags.rollout import (
    CanaryRelease,
    RolloutConfig,
    RolloutManager,
    RolloutStage,
    RolloutStatus,
    RolloutState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mgr():
    """Return a fresh RolloutManager."""
    return RolloutManager()


@pytest.fixture
def config():
    """A typical rollout config with fast pause duration for testing."""
    return RolloutConfig(
        name="test-rollout",
        stages=[
            RolloutStage.STAGE_1,
            RolloutStage.STAGE_10,
            RolloutStage.STAGE_25,
            RolloutStage.STAGE_50,
            RolloutStage.STAGE_100,
        ],
        pause_duration=0.01,  # tiny for fast tests
        error_threshold=0.05,
    )


# ---------------------------------------------------------------------------
# Rollout lifecycle tests
# ---------------------------------------------------------------------------

class TestRolloutLifecycle:
    """Tests for the full rollout lifecycle."""

    def test_start_rollout(self, mgr, config):
        state = mgr.start_rollout(config)
        assert state.name == "test-rollout"
        assert state.status == RolloutStatus.IN_PROGRESS
        assert state.current_stage == RolloutStage.STAGE_1
        assert state.current_percentage == 1

    def test_duplicate_start_raises(self, mgr, config):
        mgr.start_rollout(config)
        with pytest.raises(ValueError, match="already active"):
            mgr.start_rollout(config)

    def test_advance_stage(self, mgr, config):
        mgr.start_rollout(config)
        time.sleep(0.02)  # exceed pause_duration
        state = mgr.advance_stage("test-rollout")
        assert state.current_stage == RolloutStage.STAGE_10
        assert state.current_percentage == 10

    def test_advance_all_stages(self, mgr, config):
        mgr.start_rollout(config)
        for expected in [RolloutStage.STAGE_10, RolloutStage.STAGE_25,
                         RolloutStage.STAGE_50, RolloutStage.STAGE_100]:
            time.sleep(0.02)
            state = mgr.advance_stage("test-rollout")
            assert state.current_stage == expected

        # Final stage -> COMPLETED
        assert state.status == RolloutStatus.COMPLETED

    def test_already_completed_advance(self, mgr, config):
        mgr.start_rollout(config)
        for _ in range(6):
            time.sleep(0.02)
            mgr.advance_stage("test-rollout")
        state = mgr.get_state("test-rollout")
        assert state.status == RolloutStatus.COMPLETED
        # Further advances keep it completed
        mgr.advance_stage("test-rollout")
        assert mgr.get_state("test-rollout").status == RolloutStatus.COMPLETED

    def test_pause_and_resume(self, mgr, config):
        mgr.start_rollout(config)
        state = mgr.pause("test-rollout")
        assert state.status == RolloutStatus.PAUSED

        state = mgr.resume("test-rollout")
        assert state.status == RolloutStatus.IN_PROGRESS

    def test_advance_nonexistent_rollout(self, mgr):
        with pytest.raises(KeyError):
            mgr.advance_stage("ghost")


# ---------------------------------------------------------------------------
# Rollback tests
# ---------------------------------------------------------------------------

class TestRollback:
    """Tests for rollout rollback."""

    def test_rollback_to_previous_stage(self, mgr, config):
        mgr.start_rollout(config)
        time.sleep(0.02)
        mgr.advance_stage("test-rollout")  # 1% -> 10%
        time.sleep(0.02)
        mgr.advance_stage("test-rollout")  # 10% -> 25%

        state = mgr.rollback("test-rollout", "Bug found")
        assert state.status == RolloutStatus.ROLLED_BACK
        assert state.current_stage == RolloutStage.STAGE_10
        assert state.current_percentage == 10

    def test_rollback_from_first_stage(self, mgr, config):
        mgr.start_rollout(config)
        state = mgr.rollback("test-rollout")
        assert state.current_percentage == 0
        assert state.current_stage == RolloutStage.STAGE_0

    def test_rollback_resets_metrics(self, mgr, config):
        mgr.start_rollout(config)
        mgr.report_result("test-rollout", success=False, count=5)
        mgr.report_result("test-rollout", success=True, count=5)
        assert mgr.get_state("test-rollout").error_rate == 0.5

        mgr.rollback("test-rollout")
        state = mgr.get_state("test-rollout")
        assert state.error_count == 0
        assert state.request_count == 0
        assert state.error_rate == 0.0


# ---------------------------------------------------------------------------
# Error tracking and auto-rollback tests
# ---------------------------------------------------------------------------

class TestErrorTracking:
    """Tests for error tracking and automatic rollback."""

    def test_report_success(self, mgr, config):
        mgr.start_rollout(config)
        state = mgr.report_result("test-rollout", success=True, count=50)
        assert state.error_rate == 0.0

    def test_report_failure(self, mgr, config):
        mgr.start_rollout(config)
        state = mgr.report_result("test-rollout", success=False, count=5)
        state = mgr.report_result("test-rollout", success=True, count=5)
        assert state.error_rate == 0.5

    def test_auto_rollback_on_error_threshold(self, mgr, config):
        config.error_threshold = 0.05  # 5%
        mgr.start_rollout(config)
        # 20 requests, 2 errors = 10% > 5% threshold
        mgr.report_result("test-rollout", success=False, count=2)
        state = mgr.report_result("test-rollout", success=True, count=18)
        assert state.status == RolloutStatus.ROLLED_BACK
        assert "error rate" in state.history[-1][3].lower()

    def test_no_auto_rollback_with_small_sample(self, mgr, config):
        """Auto-rollback should not trigger with < 10 samples."""
        config.error_threshold = 0.01  # very low
        mgr.start_rollout(config)
        # Only 3 errors, 3 total = 100% but only 3 samples
        state = mgr.report_result("test-rollout", success=False, count=3)
        assert state.status != RolloutStatus.ROLLED_BACK

    def test_reset_metrics_on_stage_advance(self, mgr, config):
        mgr.start_rollout(config)
        mgr.report_result("test-rollout", success=False, count=5)
        mgr.report_result("test-rollout", success=True, count=95)
        mgr.reset_metrics("test-rollout")
        state = mgr.get_state("test-rollout")
        assert state.error_rate == 0.0

    def test_pause_on_threshold_but_no_rollback_on_advance(self, mgr, config):
        """When advancing a stage, if error_rate > threshold, pause instead.

        We deliberately stay under the auto-rollback sample minimum (10)
        so that report_result won't auto-rollback, then advance_stage
        sees the high error rate and pauses.
        """
        config.error_threshold = 0.05
        mgr.start_rollout(config)
        # 9 requests, 9 errors = 100% error, but under 10 so no auto-rollback
        mgr.report_result("test-rollout", success=False, count=9)

        time.sleep(0.02)
        state = mgr.advance_stage("test-rollout")
        assert state.status == RolloutStatus.PAUSED


# ---------------------------------------------------------------------------
# Canary release tests
# ---------------------------------------------------------------------------

class TestCanaryRelease:
    """Tests for canary release functionality."""

    def test_start_canary(self, mgr):
        canary = mgr.start_canary("canary-1", percentage=5, duration=600)
        assert canary.name == "canary-1"
        assert canary.percentage == 5
        assert canary.duration == 600

    def test_duplicate_canary_raises(self, mgr):
        mgr.start_canary("canary-1")
        with pytest.raises(ValueError, match="already exists"):
            mgr.start_canary("canary-1")

    def test_canary_elapsed_and_is_complete(self, mgr):
        canary = mgr.start_canary("quick", duration=0.01)
        time.sleep(0.02)
        assert canary.is_complete

    def test_record_canary_metric(self, mgr):
        canary = mgr.start_canary("c1")
        canary.record_metric("error_rate", 0.02)
        canary.record_metric("latency_p99", 150)
        assert canary.metrics["error_rate"] == 0.02
        assert canary.metrics["latency_p99"] == 150

    def test_should_promote_good_canary(self, mgr):
        canary = CanaryRelease(
            name="good", percentage=5,
            started_at=time.time() - 700, duration=600,  # expired
            metrics={"error_rate": 0.01},
        )
        should, reason = mgr.should_promote_canary(canary, error_threshold=0.05)
        assert should is True

    def test_should_not_promote_bad_canary(self, mgr):
        canary = CanaryRelease(
            name="bad", percentage=5,
            started_at=time.time() - 700, duration=600,
            metrics={"error_rate": 0.10},
        )
        should, reason = mgr.should_promote_canary(canary, error_threshold=0.05)
        assert should is False
        assert "error rate" in reason.lower()

    def test_should_not_promote_unfinished_canary(self, mgr):
        canary = mgr.start_canary("running", duration=600)
        should, reason = mgr.should_promote_canary(canary)
        assert should is False
        assert "still running" in reason.lower()

    def test_promote_canary(self, mgr):
        canary = mgr.start_canary("c1", percentage=10)
        state = mgr.promote_canary(canary, "my-rollout")
        assert state.current_percentage == 10

    def test_abort_canary(self, mgr):
        mgr.start_canary("c1")
        assert len(mgr.list_canaries()) == 1
        mgr.abort_canary("c1")
        assert len(mgr.list_canaries()) == 0

    def test_get_canary(self, mgr):
        mgr.start_canary("find-me")
        c = mgr.get_canary("find-me")
        assert c is not None
        assert mgr.get_canary("ghost") is None


# ---------------------------------------------------------------------------
# Query / listing tests
# ---------------------------------------------------------------------------

class TestQuery:
    """Tests for state querying."""

    def test_get_state(self, mgr, config):
        assert mgr.get_state("missing") is None
        mgr.start_rollout(config)
        assert mgr.get_state("test-rollout") is not None

    def test_list_rollouts(self, mgr, config):
        mgr.start_rollout(config)
        mgr.start_rollout(RolloutConfig(name="second"))
        assert len(mgr.list_rollouts()) == 2

    def test_list_active_rollouts(self, mgr, config):
        mgr.start_rollout(config)
        mgr.start_rollout(RolloutConfig(name="second"))
        mgr.pause("second")
        active = mgr.list_active_rollouts()
        assert len(active) == 2  # both in_progress and paused

        mgr.rollback("test-rollout")
        active = mgr.list_active_rollouts()
        assert len(active) == 1  # only paused remains

    def test_need_stage_advancement(self, mgr, config):
        config.pause_duration = 0.5
        mgr.start_rollout(config)
        assert mgr.need_stage_advancement("test-rollout") is False
        time.sleep(0.55)
        assert mgr.need_stage_advancement("test-rollout") is True

    def test_need_stage_advancement_nonexistent(self, mgr):
        with pytest.raises(KeyError):
            mgr.need_stage_advancement("ghost")


# ---------------------------------------------------------------------------
# Callback tests
# ---------------------------------------------------------------------------

class TestCallbacks:
    """Tests for rollout event callbacks."""

    def test_on_rollback_callback(self, mgr, config):
        calls = []

        def cb(name, state):
            calls.append((name, state.status))

        mgr.on_rollback(cb)
        mgr.start_rollout(config)
        mgr.rollback("test-rollout")
        assert len(calls) == 1
        assert calls[0][0] == "test-rollout"

    def test_on_promote_callback(self, mgr, config):
        calls = []

        def cb(name, stage):
            calls.append((name, stage))

        mgr.on_promote(cb)
        mgr.start_rollout(config)
        time.sleep(0.02)
        mgr.advance_stage("test-rollout")
        assert len(calls) == 1
        assert calls[0][1] == RolloutStage.STAGE_10


# ---------------------------------------------------------------------------
# RolloutConfig validation
# ---------------------------------------------------------------------------

class TestConfigValidation:
    """Tests for RolloutConfig parameter validation."""

    def test_invalid_error_threshold(self):
        with pytest.raises(ValueError):
            RolloutConfig(name="bad", error_threshold=1.5)
        with pytest.raises(ValueError):
            RolloutConfig(name="bad", error_threshold=-0.1)

    def test_invalid_canary_percentage(self):
        with pytest.raises(ValueError):
            RolloutConfig(name="bad", canary_percentage=101)
        with pytest.raises(ValueError):
            RolloutConfig(name="bad", canary_percentage=-1)

    def test_valid_config(self):
        config = RolloutConfig(name="valid")
        assert config.name == "valid"
        assert config.error_threshold == 0.05
        assert len(config.stages) == 5


# ---------------------------------------------------------------------------
# RolloutStage utility
# ---------------------------------------------------------------------------

class TestRolloutStage:
    """Tests for RolloutStage enum."""

    def test_from_percentage(self):
        assert RolloutStage.from_percentage(0) == RolloutStage.STAGE_0
        assert RolloutStage.from_percentage(1) == RolloutStage.STAGE_1
        assert RolloutStage.from_percentage(5) == RolloutStage.STAGE_10
        assert RolloutStage.from_percentage(10) == RolloutStage.STAGE_10
        assert RolloutStage.from_percentage(26) == RolloutStage.STAGE_50
        assert RolloutStage.from_percentage(100) == RolloutStage.STAGE_100
        assert RolloutStage.from_percentage(200) == RolloutStage.STAGE_100