"""Master-class masking & tokenization engine tests."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "/home/hunter/Desktop/Enterprise Builder")

import pytest
from enterprise.modules.privacy_data.masking import (
    MASKER_REGISTRY,
    CreditCardMasker,
    DataMasker,
    EmailMasker,
    GenericMasker,
    InMemoryVault,
    MaskingPolicy,
    MaskType,
    NameMasker,
    PhoneMasker,
    SQLiteVault,
    SsnMasker,
    TokenizationEngine,
)

# ─── Masker format tests ──────────────────────────────────────────────────────


class TestEmailMasker(unittest.TestCase):
    def test_keeps_domain_masks_local(self) -> None:
        out = EmailMasker().mask("alice.smith@example.com")
        assert out.endswith("@example.com")
        assert out != "alice.smith@example.com"
        assert "alice" not in out.split("@")[0].lower()

    def test_deterministic(self) -> None:
        m = EmailMasker()
        assert m.mask("bob@corp.io") == m.mask("bob@corp.io")

    def test_idempotent(self) -> None:
        m = EmailMasker()
        once = m.mask("carol@x.com")
        assert m.mask(once) == once

    def test_non_email_falls_back(self) -> None:
        out = EmailMasker().mask("notanemail")
        assert out != "notanemail"


class TestPhoneMasker(unittest.TestCase):
    def test_keeps_last_four(self) -> None:
        out = PhoneMasker().mask("+1 (555) 123-4567")
        assert out.endswith("4567")
        assert "555" not in out.replace("4567", "")

    def test_format_preserved(self) -> None:
        out = PhoneMasker().mask("555-123-4567")
        assert out.count("-") == 2

    def test_deterministic_and_idempotent(self) -> None:
        m = PhoneMasker()
        v = "415-867-5309"
        assert m.mask(v) == m.mask(v)
        assert m.mask(m.mask(v)) == m.mask(v)


class TestSsnMasker(unittest.TestCase):
    def test_ssn_xxx_xx_last4(self) -> None:
        assert SsnMasker().mask("123-45-6789") == "XXX-XX-6789"

    def test_ssn_bare_digits(self) -> None:
        assert SsnMasker().mask("123456789") == "XXX-XX-6789"

    def test_deterministic(self) -> None:
        m = SsnMasker()
        assert m.mask("111-22-3333") == m.mask("111-22-3333")


class TestCreditCardMasker(unittest.TestCase):
    def test_keeps_last_four(self) -> None:
        out = CreditCardMasker().mask("4111 1111 1111 1111")
        assert out.endswith("1111")
        assert out != "4111 1111 1111 1111"

    def test_grouping_preserved(self) -> None:
        out = CreditCardMasker().mask("4111-1111-1111-1111")
        assert out.count("-") == 3

    def test_deterministic(self) -> None:
        m = CreditCardMasker()
        assert m.mask("4000 0000 0000 0002") == m.mask("4000 0000 0000 0002")


class TestNameMasker(unittest.TestCase):
    def test_keeps_initials(self) -> None:
        out = NameMasker().mask("John Albert Smith")
        # first word keeps initial J, middle fully masked, last word keeps initial S
        assert out.startswith("J")
        assert out.endswith("S****") or out.endswith("h")
        assert len(out) == len("John Albert Smith")

    def test_deterministic(self) -> None:
        m = NameMasker()
        assert m.mask("Jane Doe") == m.mask("Jane Doe")


class TestGenericMasker(unittest.TestCase):
    def test_length_preserved(self) -> None:
        out = GenericMasker().mask("hello123")
        assert len(out) == len("hello123")
        assert out == "*****" + "***"

    def test_punctuation_kept(self) -> None:
        out = GenericMasker().mask("a-b.c")
        assert out == "*-*.*"


# ─── MaskingPolicy field-level tests ──────────────────────────────────────────


class TestMaskingPolicy(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = MaskingPolicy(
            {
                "email": MaskType.EMAIL,
                "phone": MaskType.PHONE,
                "ssn": MaskType.SSN,
                "card": MaskType.CREDIT_CARD,
                "name": MaskType.NAME,
                "notes": MaskType.GENERIC,
            }
        )

    def test_applies_field_level(self) -> None:
        record = {
            "name": "Alice Wonder",
            "email": "alice@example.com",
            "phone": "555-123-4567",
            "ssn": "123-45-6789",
            "card": "4111 1111 1111 1111",
            "notes": "hello world",
        }
        masked = self.policy.apply(record)
        assert masked["name"] == "A**** W*****"
        assert masked["email"].endswith("@example.com")
        assert masked["ssn"] == "XXX-XX-6789"
        assert masked["card"].endswith("1111")
        assert masked["notes"] != "hello world"

    def test_field_str_coerced(self) -> None:
        p = MaskingPolicy({"email": "email", "phone": "phone"})
        masked = p.apply({"email": "x@y.z", "phone": "1234567890"})
        assert masked["email"].endswith("@y.z")

    def test_unknown_field_left_untouched(self) -> None:
        masked = self.policy.apply({"other": "keep me", "email": "a@b.c"})
        assert masked["other"] == "keep me"

    def test_non_string_types_preserved(self) -> None:
        record = {"email": "a@b.c", "age": 42, "active": True, "score": 1.5}
        masked = self.policy.apply(record)
        assert masked["age"] == 42
        assert masked["active"] is True
        assert masked["score"] == 1.5

    def test_nested_structure_preserved(self) -> None:
        record = {
            "user": {"email": "nested@x.io", "phone": "555-000-1111"},
            "orders": [{"card": "4000 0000 0000 0002"}],
        }
        masked = self.policy.apply(record)
        assert masked["user"]["email"].endswith("@x.io")
        assert masked["orders"][0]["card"].endswith("0002")
        # structure intact
        assert set(masked.keys()) == {"user", "orders"}

    def test_default_masker(self) -> None:
        p = MaskingPolicy({"email": "email"}, default="generic")
        masked = p.apply({"email": "a@b.c", "free_text": "secret value"})
        assert masked["free_text"] != "secret value"


# ─── DataMasker facade ────────────────────────────────────────────────────────


class TestDataMaskerFacade(unittest.TestCase):
    def test_instance_apply(self) -> None:
        masker = DataMasker(MaskingPolicy({"email": "email"}))
        out = masker.apply({"email": "a@b.c", "x": 1})
        assert out["email"].endswith("@b.c")
        assert out["x"] == 1

    def test_static_apply_policy(self) -> None:
        policy = MaskingPolicy({"phone": "phone"})
        out = DataMasker.apply_policy(policy, {"phone": "123-456-7890"})
        assert out["phone"].endswith("7890")

    def test_requires_policy(self) -> None:
        with pytest.raises(ValueError, match="No MaskingPolicy"):
            DataMasker().apply({"a": 1})


# ─── TokenizationEngine ───────────────────────────────────────────────────────


class TestTokenizationEngine(unittest.TestCase):
    def _engine(self, **kw: object) -> TokenizationEngine:
        return TokenizationEngine(secret=b"tests-secret-key-001", **kw)

    def test_deterministic_token(self) -> None:
        e = self._engine()
        t1 = e.tokenize("alice@example.com")
        t2 = e.tokenize("alice@example.com")
        assert t1 == t2

    def test_distinct_values_distinct_tokens(self) -> None:
        e = self._engine()
        assert e.tokenize("4111111111111111") != e.tokenize("4222222222222222")

    def test_reversible_via_vault(self) -> None:
        e = self._engine()
        tok = e.tokenize("jane.doe@work.io")
        assert e.detokenize(tok) == "jane.doe@work.io"

    def test_format_preserving_shape(self) -> None:
        e = self._engine()
        tok = e.tokenize("123-45-6789")
        # shape preserved: 3 digits - 2 digits - 4 digits (may carry "tok_" prefix)
        body = tok
        if body.startswith("tok_"):
            body = body[4:]
        parts = body.split("-")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_detokenize_unknown_raises(self) -> None:
        e = self._engine()
        with pytest.raises(ValueError, match="Unknown token"):
            e.detokenize("tok_does_not_exist")

    def test_sqlite_vault_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / "vault.db")
            v = SQLiteVault(path)
            e1 = TokenizationEngine(secret=b"key-for-sqlite-test", vault=v)
            tok = e1.tokenize("42")
            v.close()
            # new engine, same db file, same secret -> same token + reversible
            v2 = SQLiteVault(path)
            e2 = TokenizationEngine(secret=b"key-for-sqlite-test", vault=v2)
            assert e2.detokenize(tok) == "42"
            v2.close()

    def test_in_memory_vault_lifecycle(self) -> None:
        v = InMemoryVault()
        e = TokenizationEngine(secret=b"mem-vault-test-key", vault=v)
        tok = e.tokenize("secret-value-1")
        assert tok in v
        assert len(v) == 1
        assert e.vault_size == 1
        assert v.reverse("secret-value-1") == tok

    def test_tokenize_record(self) -> None:
        e = self._engine()
        rec = {"card": "4111111111111111", "name": "Alice"}
        out = e.tokenize_record(rec, ["card"])
        assert out["card"] != rec["card"]
        assert out["name"] == "Alice"
        # recoverable
        assert e.detokenize(out["card"]) == rec["card"]

    def test_short_secret_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 16 bytes"):
            TokenizationEngine(secret=b"short")

    def test_reverse_lookup(self) -> None:
        e = self._engine()
        tok = e.tokenize("plate-number-ABC123")
        assert e.reverse("plate-number-ABC123") == tok

    def test_tokenize_none_raises(self) -> None:
        e = self._engine()
        with pytest.raises(ValueError, match="Cannot tokenize None"):
            e.tokenize(None)


# ─── Lifecycle / registry ─────────────────────────────────────────────────────


class TestLifecycle(unittest.TestCase):
    def test_registry_has_all_types(self) -> None:
        for t in MaskType:
            assert t in MASKER_REGISTRY

    def test_unknown_mask_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown mask type"):
            MaskingPolicy({"x": "not_a_real_type"})

    def test_masking_is_type_preserving_for_masked_strings(self) -> None:
        """Masked sensitive fields stay strings; untouched stay original types."""
        policy = MaskingPolicy({"email": "email"})
        record = {"email": "a@b.c", "count": 7}
        masked = DataMasker.apply_policy(policy, record)
        assert isinstance(masked["email"], str)
        assert isinstance(masked["count"], int)


if __name__ == "__main__":
    unittest.main()
