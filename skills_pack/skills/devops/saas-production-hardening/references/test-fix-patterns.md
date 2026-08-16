# Test Fix Patterns — Post-Hardening Regression

Catalog of test failures that predictably appear after production hardening, with fixes.

---

## Configuration Tests

### VoiceConfig / EmailConfig / CrmConfig Defaults Changed
**Symptom**: `assert cfg.provider == "vapi"` fails (now "fonoster")
**Cause**: Provider stack swapped. Dataclass defaults updated.
**Fix**: Update `conftest.py` fixtures to use new provider fields + update test assertions.
```python
# conftest.py
@pytest.fixture
def voice_config():
    return VoiceConfig(
        provider="fonoster",
        fonoster_api_key="test-key",
        fonoster_base_url="http://localhost:50051",
        # ... new fields
    )
```

### Environment Variable Prefix Changed
**Symptom**: `DEMIURGE_MKT_` env vars not picked up (was `MASTERCHIEF_`)
**Fix**: Update `_env_override` prefix logic + all test `monkeypatch.setenv` calls.

---

## Agent / Campaign Logic Tests

### Channel Logic Bug
**Symptom**: `"voice" in (channels, "both")` always True
**Cause**: Tuple membership check vs string equality
```python
# WRONG
if "voice" in (target_spec.channels, "both"):

# CORRECT
if target_spec.channels in ("voice", "both"):
```

### Fit Score Scale Mismatch
**Symptom**: `minimum_fit_score=0.80` excludes 90-score prospects
**Cause**: Prospect scores are 0-100, spec threshold was 0-1
**Fix**: Test uses `minimum_fit_score=80.0` (or normalize in code)

### RBAC Permission Denied
**Symptom**: `PermissionError: Role 'OPERATOR' not permitted 'CAMPAIGN_CREATE'`
**Cause**: Permission matrix requires MANAGER+ for campaign create
**Fix**: Test assigns `Role.MANAGER` not `Role.OPERATOR`

---

## Email Tests

### CTA Detection Double-Counts
**Symptom**: "worth a reply?" scores 0.7 (expected 1.0)
**Cause**: Two regex patterns match: "worth a reply" + general "reply"
**Fix**: Order patterns by specificity. Put "worth a reply" BEFORE general "reply" pattern. Use negative lookbehind if needed.

### Email Syntax Rejects Valid Domain
**Symptom**: `ai@demiurge_mkt.ai` rejected
**Cause**: RFC 5322 allows underscore in domain labels; regex didn't
**Fix**: Update `_EMAIL_RE` domain label from `[a-zA-Z0-9-]` to `[a-zA-Z0-9_-]`

### ThreadMemory Mock Returns None
**Symptom**: `AttributeError: 'NoneType' object has no attribute 'id'`
**Cause**: `MessageRepo.create` mocked to return `None`
**Fix**: Mock returns the input message:
```python
mock_message_repo.create = AsyncMock(side_effect=lambda msg: msg)
```

### BaseRepository Missing Helper Methods
**Symptom**: `AttributeError: 'MessageRepo' object has no attribute '_fetch_one'`
**Cause**: Repos call `self._fetch_one()` but BaseRepository only had `_exists()`
**Fix**: Add to `BaseRepository`:
```python
@staticmethod
async def _fetch_one(query: str, params: tuple = ()):
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchone()

@staticmethod
async def _fetch_all(query: str, params: tuple = ()):
    pool = await get_pool()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            return await cur.fetchall()
```

---

## Model / Pricing Tests

### Provider Prefix Stripping Mismatch
**Symptom**: `_resolve_pricing("xai/grok-3")` returns default (1.0, 5.0)
**Cause**: Pricing dict key is `"grok-3"` but router passes `"xai/grok-3"`; prefix stripping only handles `"xai/"` not `"xai/"` → `"grok-3"` works BUT test expected 3.0/15.0 from default
**Root**: Test assertion wrong OR pricing dict missing entry
**Fix**: Ensure `_MODEL_PRICING` has `"grok-3": (3.0, 15.0)` and prefix stripping handles `"xai/"`

---

## Security Tests

### Encryption Key Cache Stale
**Symptom**: `RuntimeError: Encryption key not configured` after `os.environ["KEY"] = "..."`
**Cause**: `_KEY_CACHE` module global loaded before env var set
**Fix**: Add cache clear function + call in test:
```python
# encryption.py
def clear_key_cache():
    global _KEY_CACHE
    _KEY_CACHE = None

# test
os.environ["DEMIURGE_MKT_ENCRYPTION_KEY"] = "a"*64
clear_key_cache()
cipher = encrypt(plain)
clear_key_cache()  # cleanup
```

### Invalid Base64 Error Message Changed
**Symptom**: `pytest.raises(ValueError, match="Invalid base64")` fails
**Cause**: Underlying crypto lib throws "Ciphertext too short..."
**Fix**: Update match regex: `match="Ciphertext too short|Invalid base64"`

### GDPR Country List Incomplete
**Symptom**: `assert is_gdpr_country("GB") is True` fails
**Cause**: UK (GB) not in EU country list post-Brexit but still GDPR-equivalent
**Fix**: Add `"GB"` to GDPR country set in compliance module.

---

## Compliance Tests

### TCPA DNC Scrubbing Not Tested
**Symptom**: No test for DNC list checking
**Fix**: Add test that mocks `check_suppression` and verifies call blocked.

### Opt-Out Propagation
**Symptom**: Email unsubscribe doesn't suppress future sends
**Fix**: Test that `suppression` table write blocks subsequent `send_email`.

### Consent Verification Before Send
**Symptom**: No test that consent checked before every call/email
**Fix**: Integration test mocking `check_consent()` returning False → send rejected.

---

## General Pattern: Fixture Drift

**Rule**: After any config/provider/schema change, **update `conftest.py` fixtures FIRST** before fixing tests.

**Checklist per fixture:**
- [ ] All required fields present
- [ ] Types match dataclass (int vs str, list vs dict)
- [ ] Provider-specific fields populated
- [ ] No deprecated fields (vapi_api_key, etc.)
- [ ] Related fixtures consistent (voice_config + email_config + model_config)

---

## Debugging Workflow

1. **Run single failing test with `-v --tb=short`**
2. **Read error: is it AssertionError (logic) or AttributeError/TypeError (mock/config)?**
3. **If mock/config: check conftest.py fixture vs dataclass**
4. **If logic: trace code path, add debug log, run again**
5. **Fix at source (code or test), not workaround**
6. **Run full test suite to catch regressions**

---

*Compiled from Demiurge Marketing OS v2.0 hardening — 353 tests passing, 8 fixed in this session.*