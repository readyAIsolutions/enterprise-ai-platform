"""Master-class masking & tokenization engine tests."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")

from enterprise.modules.privacy_data.masking import (
    MaskType,
    MaskingPolicy,
    EmailMasker,
    PhoneMasker,
    SsnMasker,
    CreditCardMasker,
    NameMasker,
    GenericMasker,
    InMemoryVault,
    SQLiteVault,
    TokenizationEngine,
    DataMasker,
    MASKER_REGISTRY,
)


# ─── Masker format tests ──────────────────────────────────────────────────────

class TestEmailMasker(unittest.TestCase):
    def test_keeps_domain_masks_local(self):
        out = EmailMasker().mask("alice.smith@example.com")
        self.assertTrue(out.endswith("@example.com"))
        self.assertNotEqual(out, "alice.smith@example.com")
        self.assertNotIn("alice", out.split("@")[0].lower())

    def test_deterministic(self):
        m = EmailMasker()
        self.assertEqual(m.mask("bob@corp.io"), m.mask("bob@corp.io"))

    def test_idempotent(self):
        m = EmailMasker()
        once = m.mask("carol@x.com")
        self.assertEqual(m.mask(once), once)

    def test_non_email_falls_back(self):
        out = EmailMasker().mask("notanemail")
        self.assertNotEqual(out, "notanemail")


class TestPhoneMasker(unittest.TestCase):
    def test_keeps_last_four(self):
        out = PhoneMasker().mask("+1 (555) 123-4567")
        self.assertTrue(out.endswith("4567"))
        self.assertNotIn("555", out.replace("4567", ""))

    def test_format_preserved(self):
        out = PhoneMasker().mask("555-123-4567")
        self.assertEqual(out.count("-"), 2)

    def test_deterministic_and_idempotent(self):
        m = PhoneMasker()
        v = "415-867-5309"
        self.assertEqual(m.mask(v), m.mask(v))
        self.assertEqual(m.mask(m.mask(v)), m.mask(v))


class TestSsnMasker(unittest.TestCase):
    def test_ssn_xxx_xx_last4(self):
        self.assertEqual(SsnMasker().mask("123-45-6789"), "XXX-XX-6789")

    def test_ssn_bare_digits(self):
        self.assertEqual(SsnMasker().mask("123456789"), "XXX-XX-6789")

    def test_deterministic(self):
        m = SsnMasker()
        self.assertEqual(m.mask("111-22-3333"), m.mask("111-22-3333"))


class TestCreditCardMasker(unittest.TestCase):
    def test_keeps_last_four(self):
        out = CreditCardMasker().mask("4111 1111 1111 1111")
        self.assertTrue(out.endswith("1111"))
        self.assertNotEqual(out, "4111 1111 1111 1111")

    def test_grouping_preserved(self):
        out = CreditCardMasker().mask("4111-1111-1111-1111")
        self.assertEqual(out.count("-"), 3)

    def test_deterministic(self):
        m = CreditCardMasker()
        self.assertEqual(m.mask("4000 0000 0000 0002"), m.mask("4000 0000 0000 0002"))


class TestNameMasker(unittest.TestCase):
    def test_keeps_initials(self):
        out = NameMasker().mask("John Albert Smith")
        # first word keeps initial J, middle fully masked, last word keeps initial S
        self.assertTrue(out.startswith("J"))
        self.assertTrue(out.endswith("S****") or out.endswith("h"))
        self.assertEqual(len(out), len("John Albert Smith"))

    def test_deterministic(self):
        m = NameMasker()
        self.assertEqual(m.mask("Jane Doe"), m.mask("Jane Doe"))


class TestGenericMasker(unittest.TestCase):
    def test_length_preserved(self):
        out = GenericMasker().mask("hello123")
        self.assertEqual(len(out), len("hello123"))
        self.assertEqual(out, "*****" + "***")

    def test_punctuation_kept(self):
        out = GenericMasker().mask("a-b.c")
        self.assertEqual(out, "*-*.*")


# ─── MaskingPolicy field-level tests ──────────────────────────────────────────

class TestMaskingPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = MaskingPolicy({
            "email": MaskType.EMAIL,
            "phone": MaskType.PHONE,
            "ssn": MaskType.SSN,
            "card": MaskType.CREDIT_CARD,
            "name": MaskType.NAME,
            "notes": MaskType.GENERIC,
        })

    def test_applies_field_level(self):
        record = {
            "name": "Alice Wonder",
            "email": "alice@example.com",
            "phone": "555-123-4567",
            "ssn": "123-45-6789",
            "card": "4111 1111 1111 1111",
            "notes": "hello world",
        }
        masked = self.policy.apply(record)
        self.assertEqual(masked["name"], "A**** W*****")
        self.assertTrue(masked["email"].endswith("@example.com"))
        self.assertEqual(masked["ssn"], "XXX-XX-6789")
        self.assertTrue(masked["card"].endswith("1111"))
        self.assertNotEqual(masked["notes"], "hello world")

    def test_field_str_coerced(self):
        p = MaskingPolicy({"email": "email", "phone": "phone"})
        masked = p.apply({"email": "x@y.z", "phone": "1234567890"})
        self.assertTrue(masked["email"].endswith("@y.z"))

    def test_unknown_field_left_untouched(self):
        masked = self.policy.apply({"other": "keep me", "email": "a@b.c"})
        self.assertEqual(masked["other"], "keep me")

    def test_non_string_types_preserved(self):
        record = {"email": "a@b.c", "age": 42, "active": True, "score": 1.5}
        masked = self.policy.apply(record)
        self.assertEqual(masked["age"], 42)
        self.assertIs(masked["active"], True)
        self.assertEqual(masked["score"], 1.5)

    def test_nested_structure_preserved(self):
        record = {
            "user": {"email": "nested@x.io", "phone": "555-000-1111"},
            "orders": [{"card": "4000 0000 0000 0002"}],
        }
        masked = self.policy.apply(record)
        self.assertTrue(masked["user"]["email"].endswith("@x.io"))
        self.assertTrue(masked["orders"][0]["card"].endswith("0002"))
        # structure intact
        self.assertEqual(set(masked.keys()), {"user", "orders"})

    def test_default_masker(self):
        p = MaskingPolicy({"email": "email"}, default="generic")
        masked = p.apply({"email": "a@b.c", "free_text": "secret value"})
        self.assertNotEqual(masked["free_text"], "secret value")


# ─── DataMasker facade ────────────────────────────────────────────────────────

class TestDataMaskerFacade(unittest.TestCase):
    def test_instance_apply(self):
        masker = DataMasker(MaskingPolicy({"email": "email"}))
        out = masker.apply({"email": "a@b.c", "x": 1})
        self.assertTrue(out["email"].endswith("@b.c"))
        self.assertEqual(out["x"], 1)

    def test_static_apply_policy(self):
        policy = MaskingPolicy({"phone": "phone"})
        out = DataMasker.apply_policy(policy, {"phone": "123-456-7890"})
        self.assertTrue(out["phone"].endswith("7890"))

    def test_requires_policy(self):
        with self.assertRaises(ValueError):
            DataMasker().apply({"a": 1})


# ─── TokenizationEngine ───────────────────────────────────────────────────────

class TestTokenizationEngine(unittest.TestCase):
    def _engine(self, **kw):
        return TokenizationEngine(secret=b"tests-secret-key-001", **kw)

    def test_deterministic_token(self):
        e = self._engine()
        t1 = e.tokenize("alice@example.com")
        t2 = e.tokenize("alice@example.com")
        self.assertEqual(t1, t2)

    def test_distinct_values_distinct_tokens(self):
        e = self._engine()
        self.assertNotEqual(e.tokenize("4111111111111111"),
                            e.tokenize("4222222222222222"))

    def test_reversible_via_vault(self):
        e = self._engine()
        tok = e.tokenize("jane.doe@work.io")
        self.assertEqual(e.detokenize(tok), "jane.doe@work.io")

    def test_format_preserving_shape(self):
        e = self._engine()
        tok = e.tokenize("123-45-6789")
        # shape preserved: 3 digits - 2 digits - 4 digits (may carry "tok_" prefix)
        body = tok
        if body.startswith("tok_"):
            body = body[4:]
        parts = body.split("-")
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(p.isdigit() for p in parts))

    def test_detokenize_unknown_raises(self):
        e = self._engine()
        with self.assertRaises(ValueError):
            e.detokenize("tok_does_not_exist")

    def test_sqlite_vault_persistence(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "vault.db")
            v = SQLiteVault(path)
            e1 = TokenizationEngine(secret=b"key-for-sqlite-test", vault=v)
            tok = e1.tokenize("42")
            v.close()
            # new engine, same db file, same secret -> same token + reversible
            v2 = SQLiteVault(path)
            e2 = TokenizationEngine(secret=b"key-for-sqlite-test", vault=v2)
            self.assertEqual(e2.detokenize(tok), "42")
            v2.close()

    def test_in_memory_vault_lifecycle(self):
        v = InMemoryVault()
        e = TokenizationEngine(secret=b"mem-vault-test-key", vault=v)
        tok = e.tokenize("secret-value-1")
        self.assertIn(tok, v)
        self.assertEqual(len(v), 1)
        self.assertEqual(e.vault_size, 1)
        self.assertEqual(v.reverse("secret-value-1"), tok)

    def test_tokenize_record(self):
        e = self._engine()
        rec = {"card": "4111111111111111", "name": "Alice"}
        out = e.tokenize_record(rec, ["card"])
        self.assertNotEqual(out["card"], rec["card"])
        self.assertEqual(out["name"], "Alice")
        # recoverable
        self.assertEqual(e.detokenize(out["card"]), rec["card"])

    def test_short_secret_rejected(self):
        with self.assertRaises(ValueError):
            TokenizationEngine(secret=b"short")

    def test_reverse_lookup(self):
        e = self._engine()
        tok = e.tokenize("plate-number-ABC123")
        self.assertEqual(e.reverse("plate-number-ABC123"), tok)

    def test_tokenize_none_raises(self):
        e = self._engine()
        with self.assertRaises(ValueError):
            e.tokenize(None)


# ─── Lifecycle / registry ─────────────────────────────────────────────────────

class TestLifecycle(unittest.TestCase):
    def test_registry_has_all_types(self):
        for t in MaskType:
            self.assertIn(t, MASKER_REGISTRY)

    def test_unknown_mask_type_raises(self):
        with self.assertRaises(ValueError):
            MaskingPolicy({"x": "not_a_real_type"})

    def test_masking_is_type_preserving_for_masked_strings(self):
        """Masked sensitive fields stay strings; untouched stay original types."""
        policy = MaskingPolicy({"email": "email"})
        record = {"email": "a@b.c", "count": 7}
        masked = DataMasker.apply_policy(policy, record)
        self.assertIsInstance(masked["email"], str)
        self.assertIsInstance(masked["count"], int)


if __name__ == "__main__":
    unittest.main()
