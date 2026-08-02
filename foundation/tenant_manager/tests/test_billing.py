"""
Tests for BillingTracker - usage recording, metering, reports, alerts.
"""

import unittest
from datetime import datetime, timedelta

from ..billing import (
    BillingTracker,
    MeteringEngine,
    UsageRecord,
    BillingReport,
    UsageThreshold,
    UsageAlert,
)


class TestMeteringEngine(unittest.TestCase):

    def setUp(self):
        self.engine = MeteringEngine()

    def test_default_rates(self):
        self.assertEqual(self.engine.get_rate("api_call"), 0.0001)
        self.assertEqual(self.engine.get_rate("token_input"), 0.000003)
        self.assertEqual(self.engine.get_rate("token_output"), 0.000015)

    def test_set_and_get_rate(self):
        self.engine.set_rate("custom_metric", 0.05)
        self.assertEqual(self.engine.get_rate("custom_metric"), 0.05)

    def test_unknown_metric_zero_cost(self):
        self.assertEqual(self.engine.get_rate("unknown_metric"), 0.0)

    def test_calculate_cost(self):
        cost = self.engine.calculate_cost("api_call", 1000)
        self.assertAlmostEqual(cost, 0.1)  # 1000 * 0.0001

    def test_calculate_record_cost(self):
        record = UsageRecord(
            record_id="r1", tenant_id="t1",
            timestamp=datetime.utcnow(), metric="api_call", quantity=500,
        )
        cost = self.engine.calculate_record_cost(record)
        self.assertAlmostEqual(cost, 0.05)  # 500 * 0.0001


class TestBillingTracker(unittest.TestCase):

    def setUp(self):
        self.tracker = BillingTracker()

    # --- Usage Tracking ---

    def test_record_usage(self):
        record = self.tracker.record_usage("t1", "api_call", 100)
        self.assertTrue(record.record_id.startswith("rec_"))
        self.assertEqual(record.tenant_id, "t1")
        self.assertEqual(record.metric, "api_call")
        self.assertEqual(record.quantity, 100)
        self.assertGreater(record.cost, 0)

    def test_record_usage_with_details(self):
        record = self.tracker.record_usage(
            "t1", "token_input", 15000,
            resource_details={"model": "gpt-4", "endpoint": "/chat"},
        )
        self.assertEqual(record.resource_details["model"], "gpt-4")

    def test_multiple_records_increment_counter(self):
        self.tracker.record_usage("t1", "api_call", 100)
        self.tracker.record_usage("t1", "api_call", 200)
        self.tracker.record_usage("t2", "api_call", 50)
        t1_records = self.tracker.get_usage("t1")
        t2_records = self.tracker.get_usage("t2")
        self.assertEqual(len(t1_records), 2)
        self.assertEqual(len(t2_records), 1)

    def test_get_usage_filtered(self):
        now = datetime.utcnow()
        self.tracker.record_usage("t1", "api_call", 100)
        self.tracker.record_usage("t1", "storage_gb_hour", 10)
        api = self.tracker.get_usage("t1", metric="api_call")
        self.assertEqual(len(api), 1)
        self.assertEqual(api[0].metric, "api_call")

    def test_get_usage_time_filtered(self):
        now = datetime.utcnow()
        record = self.tracker.record_usage("t1", "api_call", 100)
        # Query with future start - should be empty
        future = now + timedelta(days=1)
        results = self.tracker.get_usage("t1", start_time=future)
        self.assertEqual(len(results), 0)

    # --- Usage Summary ---

    def test_get_usage_summary(self):
        self.tracker.record_usage("t1", "api_call", 100)
        self.tracker.record_usage("t1", "api_call", 200)
        self.tracker.record_usage("t1", "token_input", 5000)

        summary = self.tracker.get_usage_summary("t1")
        self.assertIn("api_call", summary)
        self.assertIn("token_input", summary)
        self.assertEqual(summary["api_call"]["quantity"], 300)

    def test_get_total_cost(self):
        self.tracker.record_usage("t1", "api_call", 1000)
        self.tracker.record_usage("t1", "api_call", 500)
        cost = self.tracker.get_total_cost("t1")
        self.assertAlmostEqual(cost, 1500 * 0.0001)

    # --- Billing Reports ---

    def test_generate_report(self):
        self.tracker.record_usage("t1", "api_call", 1000)
        self.tracker.record_usage("t1", "token_input", 5000)
        self.tracker.record_usage("t1", "compute_hour", 10)
        now = datetime.utcnow()
        start = now - timedelta(days=30)

        report = self.tracker.generate_report("t1", start, now)
        self.assertTrue(report.report_id.startswith("rpt_"))
        self.assertEqual(report.tenant_id, "t1")
        self.assertEqual(report.period_start, start)
        self.assertIn("api_call", report.metrics)
        self.assertGreater(report.total_cost, 0)
        self.assertEqual(len(report.line_items), 3)

    def test_generate_report_csv(self):
        self.tracker.record_usage("t1", "api_call", 100)
        now = datetime.utcnow()
        start = now - timedelta(days=1)
        csv_str = self.tracker.generate_report_csv("t1", start, now)
        self.assertIn("Report ID", csv_str)
        self.assertIn("t1", csv_str)
        self.assertIn("api_call", csv_str)

    def test_get_all_tenant_costs(self):
        self.tracker.record_usage("t1", "api_call", 1000)
        self.tracker.record_usage("t2", "api_call", 2000)
        costs = self.tracker.get_all_tenant_costs()
        self.assertIn("t1", costs)
        self.assertIn("t2", costs)
        self.assertGreater(costs["t2"], costs["t1"])

    # --- Thresholds & Alerts ---

    def test_set_threshold(self):
        thresh = self.tracker.set_threshold(
            "t1", "api_call", absolute_limit=10000,
            warning_percent=50, critical_percent=80,
        )
        self.assertEqual(thresh.tenant_id, "t1")
        self.assertEqual(thresh.metric, "api_call")
        self.assertEqual(thresh.absolute_limit, 10000)

    def test_check_thresholds_warning(self):
        self.tracker.set_threshold(
            "t1", "api_call", absolute_limit=1000, warning_percent=50,
        )
        # Record 600 (60% of 1000) -> should trigger WARNING
        self.tracker.record_usage("t1", "api_call", 600)
        triggered = self.tracker.check_thresholds("t1")
        self.assertTrue(any(t[0] == UsageAlert.WARNING for t in triggered))

    def test_check_thresholds_critical(self):
        self.tracker.set_threshold(
            "t1", "api_call", absolute_limit=1000, critical_percent=80,
        )
        self.tracker.record_usage("t1", "api_call", 900)
        triggered = self.tracker.check_thresholds("t1")
        self.assertTrue(any(t[0] == UsageAlert.CRITICAL for t in triggered))

    def test_check_thresholds_quota_exceeded(self):
        self.tracker.set_threshold(
            "t1", "api_call", absolute_limit=500,
        )
        self.tracker.record_usage("t1", "api_call", 600)
        triggered = self.tracker.check_thresholds("t1")
        self.assertTrue(any(t[0] == UsageAlert.QUOTA_EXCEEDED for t in triggered))

    def test_check_thresholds_below_warning(self):
        self.tracker.set_threshold(
            "t1", "api_call", absolute_limit=1000, warning_percent=50,
        )
        self.tracker.record_usage("t1", "api_call", 400)
        triggered = self.tracker.check_thresholds("t1")
        self.assertEqual(len(triggered), 0)

    def test_remove_threshold(self):
        thresh = self.tracker.set_threshold("t1", "api_call", 1000)
        self.assertTrue(self.tracker.remove_threshold(thresh.threshold_id))
        self.assertFalse(self.tracker.remove_threshold(thresh.threshold_id))

    def test_get_thresholds(self):
        self.tracker.set_threshold("t1", "api_call", 1000)
        self.tracker.set_threshold("t1", "storage_gb_hour", 500)
        self.tracker.set_threshold("t2", "api_call", 2000)
        t1_thresholds = self.tracker.get_thresholds("t1")
        self.assertEqual(len(t1_thresholds), 2)

    def test_alert_callbacks(self):
        alerts_fired = []

        def on_warning(tenant_id, threshold, current_usage):
            alerts_fired.append(("warning", tenant_id, threshold.metric))

        def on_critical(tenant_id, threshold, current_usage):
            alerts_fired.append(("critical", tenant_id, threshold.metric))

        self.tracker.on_alert(UsageAlert.WARNING, on_warning)
        self.tracker.on_alert(UsageAlert.CRITICAL, on_critical)

        self.tracker.set_threshold("t1", "api_call", 1000, warning_percent=50)
        self.tracker.record_usage("t1", "api_call", 600)

        self.assertTrue(any(a[0] == "warning" and a[1] == "t1" for a in alerts_fired))

    def test_off_alert(self):
        calls = []
        cb = lambda tid, th, cu: calls.append(tid)
        self.tracker.on_alert(UsageAlert.WARNING, cb)
        self.tracker.off_alert(UsageAlert.WARNING, cb)
        self.tracker.set_threshold("t1", "api_call", 100, warning_percent=10)
        self.tracker.record_usage("t1", "api_call", 50)
        self.assertEqual(len(calls), 0)

    # --- Analytics ---

    def test_get_usage_trend(self):
        self.tracker.record_usage("t1", "api_call", 100)
        self.tracker.record_usage("t1", "api_call", 200)
        trend = self.tracker.get_usage_trend("t1", "api_call", days=7, interval="day")
        self.assertGreaterEqual(len(trend), 1)
        self.assertIn("timestamp", trend[0])
        self.assertIn("quantity", trend[0])
        self.assertIn("cost", trend[0])

    def test_get_top_tenants_by_cost(self):
        self.tracker.record_usage("big_spender", "api_call", 100000)
        self.tracker.record_usage("small_spender", "api_call", 100)
        top = self.tracker.get_top_tenants_by_cost(limit=5)
        self.assertGreaterEqual(len(top), 2)
        self.assertEqual(top[0][0], "big_spender")

    # --- Cleanup ---

    def test_cleanup(self):
        self.tracker.record_usage("t1", "api_call", 100)
        self.tracker.cleanup()
        self.assertEqual(len(self.tracker.get_usage("t1")), 0)

    # --- Edge Cases ---

    def test_zero_quantity(self):
        record = self.tracker.record_usage("t1", "api_call", 0)
        self.assertEqual(record.cost, 0.0)

    def test_empty_tenant_usage(self):
        records = self.tracker.get_usage("nonexistent_tenant")
        self.assertEqual(len(records), 0)

    def test_empty_usage_summary(self):
        summary = self.tracker.get_usage_summary("empty_tenant")
        self.assertEqual(summary, {})

    def test_period_before_records(self):
        now = datetime.utcnow()
        # Query period entirely before any records
        start = now - timedelta(days=60)
        end = now - timedelta(days=30)
        self.tracker.record_usage("t1", "api_call", 100)
        report = self.tracker.generate_report("t1", start, end)
        self.assertEqual(report.total_cost, 0.0)

    def test_roundtrip_record(self):
        record = self.tracker.record_usage(
            "t1", "token_output", 1000,
            resource_details={"model": "claude-3"},
        )
        # Retrieve the exact record
        records = self.tracker.get_usage("t1", metric="token_output")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].record_id, record.record_id)
        self.assertEqual(records[0].resource_details["model"], "claude-3")


if __name__ == "__main__":
    unittest.main()