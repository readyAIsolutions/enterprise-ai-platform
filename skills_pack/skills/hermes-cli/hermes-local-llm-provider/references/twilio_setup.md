# Twilio Provider Integration Pattern

Reusable pattern for adding Twilio voice/SMS providers to Hermes-compatible applications.

## Credential Setup

### Required Configuration Fields
```yaml
# config/defaults.yaml
twilio_account_sid: ""      # Classic auth: Account SID (starts with AC)
twilio_auth_token: ""        # Classic auth: Auth Token (or API Key secret)
twilio_phone_number: ""      # E.164 format: +17808932704
```

### Environment Variables
```bash
MASTERCHIEF_VOICE__TWILIO_ACCOUNT_SID=AC...
MASTERCHIEF_VOICE__TWILIO_AUTH_TOKEN=...
MASTERCHIEF_VOICE__TWILIO_PHONE_NUMBER=+1...
```

## Provider Implementation Pattern

### 1. Add to secret_map in config.py
```python
secret_map = {
    'twilio_account_sid': self.twilio_account_sid,
    'twilio_auth_token': self.twilio_auth_token,
    'twilio_api_key': getattr(self, 'twilio_api_key', None),
    'twilio_api_secret': getattr(self, 'twilio_api_secret', None),
}
```

### 2. Provider Factory Registration
```python
# In get_voice_provider()
if provider == 'twilio-cr':
    return TwilioProvider(config.provider_config)
if provider == 'twilto':
    return TwilioProvider(config.provider_config)
```

### 3. TwilioProvider Class Skeleton
```python
class TwilioProvider(VoiceProvider):
    def __init__(self, config: VoiceConfig):
        self.account_sid = config.twilio_account_sid
        self.auth_token = config.twilio_auth_token
        # Support both classic auth and API key auth
        if hasattr(config, 'twilio_api_key') and config.twilio_api_key:
            from twilio.base.client import TwilioClient
            self.client = TwilioClient(
                username=config.twilio_api_key,
                password=config.twilio_api_secret,
                account_sid=config.twilio_account_sid
            )
        else:
            from twilio.rest import Client
            self.client = Client(self.account_sid, self.auth_token)
    
    def create_outbound_call(self, to: str, from_: str) -> str:
        call = self.client.calls.create(
            to=to,
            from_=from_,
            url="http://demo.twilio.com/docs/voice.xml"
        )
        return call.sid
```

## Live Verification Commands

### Verify Credentials
```bash
# Check account is active
curl -X GET "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID.json" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN"

# List phone numbers on account
curl -X GET "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/IncomingPhoneNumbers.json" \
  -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN"
```

## Common Pitfalls

1. **Account SID vs API Key**: Both work. Account SID starts with `AC`, API Key is shorter.
   - Classic auth (SID + Auth Token) is simpler
   - API Key auth allows scoped permissions but needs `username=f"{api_key}" password="{api_secret}"`

2. **Phone number format**: Must be E.164 format in config (`+17808932704`), but Twilio expects
   `+17808932704` or `17808932704` in API calls

3. **API drift**: The `twilio` library changed. Use `Client(account_sid, auth_token)` for classic
   auth, not `TwilioClient` which is for API key auth

4. **Import ordering**: Import `twilio.rest.Client` inside `__init__` or at function scope
   to avoid import errors when Twilio is not installed

## Dependencies

Add to `pyproject.toml`:
```toml
dependencies = [
    "twilio>=9.0.0",
]
```

## Testing

After setup, verify the factory works:
```python
from masterchief.config import VoiceConfig
from masterchief.voice.provider import get_voice_provider

config = VoiceConfig(provider='twilio-cr', ...)
provider = get_voice_provider(config)
# Should return TwilioProvider instance without error
```