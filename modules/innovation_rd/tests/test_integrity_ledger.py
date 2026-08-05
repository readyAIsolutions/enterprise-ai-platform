"""Tests for the innovation_rd integrity ledger subsystem.

Covers: deterministic fingerprinting, the SQLite hash-chained ledger,
tamper detection by the verifier, reproducibility comparison, the honest
isolation hook, persistence round-trips, and lifecycle behaviour.
"""
import os
import tempfile
import unittest
from datetime import datetime, timezone

from ..integrity_ledger import (
    GENESIS_HASH,
    IntegrityLedger,
    IntegrityVerifier,
    LedgerRecord,
    RunFingerprint,
    VerificationResult,
    filter_env_snapshot,
    record_isolation_run,
    run_is_reproducible,
)


from typing import Any, Dict


def make_fingerprint(**overrides: Any) -> str:
    base: Dict[str, Any] = dict(
        inputs={"dataset": "mnist-v1", "split": "train"},
        code_version="abc123",
        params={"lr": 0.01, "batch": 32},
        seed=42,
        env={"PYTHONHASHSEED": "0", "LANG": "en_US.UTF-8"},
    )
    base.update(overrides)
    return RunFingerprint.compute_hash(
        inputs=base.get("inputs"),
        code_version=str(base.get("code_version", "")),
        params=base.get("params"),
        seed=base.get("seed"),
        env=base.get("env"),
        env_exclude=base.get("env_exclude"),
    )


class FingerprintTests(unittest.TestCase):
    """RunFingerprint determinism and sensitivity."""

    def test_same_inputs_same_hash(self):
        a = make_fingerprint()
        b = make_fingerprint()
        self.assertEqual(a, b)

    def test_recompute_is_stable_across_calls(self):
        fp = RunFingerprint(
            inputs={"x": [1, 2, {"y": 3}]},
            code_version="v1",
            params={"lr": 0.01},
            seed=7,
            env={"A": "1"},
        )
        self.assertEqual(fp.compute(), fp.compute())

    def test_different_inputs_different_hash(self):
        self.assertNotEqual(make_fingerprint(), make_fingerprint(inputs={"dataset": "other"}))

    def test_different_params_different_hash(self):
        self.assertNotEqual(make_fingerprint(), make_fingerprint(params={"lr": 0.02, "batch": 32}))

    def test_different_seed_different_hash(self):
        self.assertNotEqual(make_fingerprint(), make_fingerprint(seed=43))

    def test_different_code_version_different_hash(self):
        self.assertNotEqual(make_fingerprint(), make_fingerprint(code_version="def456"))

    def test_dict_key_order_does_not_change_hash(self):
        h1 = RunFingerprint.compute_hash(params={"lr": 1, "a": 2})
        h2 = RunFingerprint.compute_hash(params={"a": 2, "lr": 1})
        self.assertEqual(h1, h2)

    def test_env_filtering_removes_volatile_keys(self):
        raw = {
            "PYTHONHASHSEED": "0",
            "PATH": "/usr/bin",
            "SHLVL": "1",
            "HOSTNAME": "box",
            "TIMESTAMP_SECRET": "x",
            "TERM": "xterm",
        }
        filtered = filter_env_snapshot(raw)
        self.assertIn("PYTHONHASHSEED", filtered)
        self.assertNotIn("PATH", filtered)
        self.assertNotIn("HOSTNAME", filtered)
        self.assertNotIn("TIMESTAMP_SECRET", filtered)
        self.assertNotIn("TERM", filtered)

    def test_env_difference_changes_hash(self):
        self.assertNotEqual(
            make_fingerprint(env={"PYTHONHASHSEED": "0"}),
            make_fingerprint(env={"PYTHONHASHSEED": "1"}),
        )

    def test_from_experiment_duck_type(self):
        class FakeExp:
            dataset = "ds"
            metrics = ["acc"]
            baseline = 0.5
            budget = 10.0
            variables = {"lr": 0.01}

        fp = RunFingerprint.from_experiment(FakeExp(), code_version="v9", seed=1)
        self.assertEqual(len(fp.compute()), 64)
        self.assertIn("acc", str(fp.inputs))

    def test_seed_none_vs_set_different(self):
        self.assertNotEqual(
            make_fingerprint(seed=None), make_fingerprint(seed=0)
        )

    def test_digest_is_sha256_hex_length(self):
        self.assertEqual(len(make_fingerprint()), 64)


class LedgerTests(unittest.TestCase):
    """IntegrityLedger append-only hash-chain behaviour."""

    def test_append_creates_chained_records(self):
        ledger = IntegrityLedger(":memory:")
        try:
            fp = make_fingerprint()
            r1 = ledger.append("run-1", fp, actor="alice", action="created")
            r2 = ledger.append("run-1", fp, actor="alice", action="completed")
            self.assertEqual(r1.prev_hash, GENESIS_HASH)
            self.assertEqual(r2.prev_hash, r1.record_hash)
            self.assertEqual(ledger.count(), 2)
        finally:
            ledger.close()

    def test_records_are_ordered_and_complete(self):
        ledger = IntegrityLedger(":memory:")
        try:
            for i in range(5):
                ledger.append(f"run-{i}", make_fingerprint(seed=i))
            records = ledger.records()
            self.assertEqual([r.seq for r in records], [1, 2, 3, 4, 5])
            self.assertEqual(len(ledger), 5)
        finally:
            ledger.close()

    def test_verifier_accepts_pristine_chain(self):
        ledger = IntegrityLedger(":memory:")
        try:
            for i in range(4):
                ledger.append(f"run-{i}", make_fingerprint(seed=i))
            result = IntegrityVerifier().verify(ledger)
            self.assertTrue(result.valid)
            self.assertEqual(result.total_records, 4)
            self.assertEqual(result.tampered_seq, [])
        finally:
            ledger.close()

    def test_verifier_detects_modified_record(self):
        ledger = IntegrityLedger(":memory:")
        try:
            ledger.append("run-1", make_fingerprint(), actor="alice", action="created")
            ledger.append("run-2", make_fingerprint(seed=2), actor="bob", action="ran")
            # Tamper: rewrite run-2's fingerprint behind the ledger's back.
            ledger._execute_raw(
                "UPDATE integrity_records SET fingerprint=? WHERE run_id='run-2'",
                (make_fingerprint(seed=999),),
            )
            result = IntegrityVerifier().verify(ledger)
            self.assertFalse(result.valid)
            self.assertIn(2, result.tampered_seq)
        finally:
            ledger.close()

    def test_verifier_detects_inserted_record(self):
        ledger = IntegrityLedger(":memory:")
        try:
            ledger.append("run-1", make_fingerprint(), action="created")
            ledger.append("run-2", make_fingerprint(), action="ran")
            # Insert a foreign record at seq=3 with a wrong prev_hash / hash.
            ledger._execute_raw(
                "INSERT INTO integrity_records "
                "(seq, run_id, fingerprint, actor, action, isolation, "
                " recorded_at, prev_hash, record_hash) "
                "VALUES (3, 'evil', ?, 'mallory', 'inserted', 0, ?, ?, ?)",
                (make_fingerprint(seed=7), "2020-01-01T00:00:00+00:00",
                 GENESIS_HASH, "f" * 64),
            )
            result = IntegrityVerifier().verify(ledger)
            self.assertFalse(result.valid)
        finally:
            ledger.close()

    def test_verifier_detects_deleted_record(self):
        ledger = IntegrityLedger(":memory:")
        try:
            for i in range(3):
                ledger.append(f"run-{i}", make_fingerprint(seed=i))
            ledger._execute_raw("DELETE FROM integrity_records WHERE run_id='run-1'")
            result = IntegrityVerifier().verify(ledger)
            self.assertFalse(result.valid)
            self.assertTrue(result.missing_seq)
        finally:
            ledger.close()

    def test_record_fields_round_trip(self):
        ledger = IntegrityLedger(":memory:")
        try:
            ts = datetime.now(timezone.utc).isoformat()
            rec = ledger.append(
                "run-x", make_fingerprint(), actor="sys", action="ran",
                isolation=True, recorded_at=ts,
            )
            self.assertTrue(rec.isolation)
            self.assertEqual(rec.actor, "sys")
            self.assertEqual(rec.recorded_at, ts)
            self.assertIsInstance(rec, LedgerRecord)
        finally:
            ledger.close()


class ReproducibilityTests(unittest.TestCase):
    """run_is_reproducible comparison."""

    def test_same_fingerprints_reproducible(self):
        a = make_fingerprint()
        b = make_fingerprint()
        self.assertTrue(run_is_reproducible(a, b))

    def test_different_inputs_not_reproducible(self):
        self.assertFalse(
            run_is_reproducible(
                make_fingerprint(inputs={"dataset": "mnist"}),
                make_fingerprint(inputs={"dataset": "cifar"}),
            )
        )

    def test_accepts_fingerprint_objects_and_digests(self):
        fp1 = make_fingerprint()
        obj = RunFingerprint.compute_hash(
            inputs={"dataset": "mnist-v1", "split": "train"},
            code_version="abc123", params={"lr": 0.01, "batch": 32},
            seed=42, env={"PYTHONHASHSEED": "0", "LANG": "en_US.UTF-8"},
        )
        self.assertTrue(run_is_reproducible(fp1, obj))

    def test_reproducible_via_objects(self):
        a = RunFingerprint(inputs={"d": 1}, code_version="v", seed=1)
        b = RunFingerprint(inputs={"d": 1}, code_version="v", seed=1)
        self.assertTrue(run_is_reproducible(a, b))
        c = RunFingerprint(inputs={"d": 2}, code_version="v", seed=1)
        self.assertFalse(run_is_reproducible(a, c))


class IsolationHookTests(unittest.TestCase):
    """Honest isolation hook records the sandbox fact in the chain."""

    def test_isolation_flag_recorded(self):
        ledger = IntegrityLedger(":memory:")
        try:
            rec = record_isolation_run(ledger, "run-iso", make_fingerprint())
            self.assertTrue(rec.isolation)
            self.assertEqual(rec.action, "isolated_run")
            stored = ledger.records()[0]
            self.assertTrue(stored.isolation)
        finally:
            ledger.close()

    def test_isolated_and_plain_runs_distinguishable_in_chain(self):
        ledger = IntegrityLedger(":memory:")
        try:
            ledger.append("plain", make_fingerprint(seed=1), action="ran")
            record_isolation_run(ledger, "sandboxed", make_fingerprint(seed=2))
            recs = ledger.records()
            self.assertFalse(recs[0].isolation)
            self.assertTrue(recs[1].isolation)
        finally:
            ledger.close()

    def test_changing_inputs_changes_fingerprint_for_isolated_run(self):
        fp_before = make_fingerprint(inputs={"dataset": "v1"})
        fp_after = make_fingerprint(inputs={"dataset": "v2"})
        self.assertNotEqual(fp_before, fp_after)
        # The isolation record must not be reproducible against the changed run.
        self.assertFalse(run_is_reproducible(fp_before, fp_after))


class PersistenceLifecycleTests(unittest.TestCase):
    """Persistence round-trip and ledger lifecycle."""

    def test_persistence_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "ledger.db")
            ledger = IntegrityLedger(db)
            try:
                ledger.append("run-p", make_fingerprint(), actor="alice", action="ran")
                self.assertEqual(ledger.count(), 1)
            finally:
                ledger.close()

            # Reopen the same file: records and chain must survive.
            ledger2 = IntegrityLedger(db)
            try:
                self.assertEqual(ledger2.count(), 1)
                self.assertTrue(IntegrityVerifier().verify(ledger2).valid)
                ledger2.append("run-q", make_fingerprint(seed=3), action="verified")
                self.assertEqual(ledger2.count(), 2)
            finally:
                ledger2.close()

            # Chain remains valid across the full history.
            ledger3 = IntegrityLedger(db)
            try:
                self.assertTrue(IntegrityVerifier().verify(ledger3).valid)
                self.assertEqual(ledger3.count(), 2)
            finally:
                ledger3.close()

    def test_context_manager_lifecycle(self):
        with IntegrityLedger(":memory:") as ledger:
            ledger.append("run-c", make_fingerprint(), action="ran")
            self.assertEqual(ledger.count(), 1)

    def test_append_only_no_public_mutation(self):
        ledger = IntegrityLedger(":memory:")
        try:
            ledger.append("run-1", make_fingerprint(), action="ran")
            # Only _execute_raw (a test helper) can mutate; public surface is
            # read + append. Verify pristine chain.
            self.assertTrue(IntegrityVerifier().verify(ledger).valid)
            self.assertEqual(len([m for m in dir(ledger) if m.startswith("append") or m == "records"]), 2)
        finally:
            ledger.close()

    def test_verification_result_summary(self):
        result = VerificationResult(valid=True, total_records=3)
        self.assertIn("VALID", result.summary())
        bad = VerificationResult(valid=False, total_records=2, tampered_seq=[1])
        self.assertIn("INVALID", bad.summary())
        self.assertIn("tampered=[1]", bad.summary())


if __name__ == "__main__":
    unittest.main()
