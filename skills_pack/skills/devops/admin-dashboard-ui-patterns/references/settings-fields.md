# Demiurge Marketing Settings Fields

User settings stored in `data/users/{google-sub}.json`:

| Field | Description |
|-------|-------------|
| voice_provider | Provider name (twilio) |
| voice_api_key | Vapi.ai API key OR Twilio `AccountSID:AuthToken` format |
| voice_from_number | Twilio caller ID (E.164) |
| voice_max_concurrent | Max parallel calls |
| email_provider | resend / sendgrid / smtp |
| email_api_key | Resend API key |
| email_from | From address (verified) |
| email_daily_limit | Rate limit |
| crm_provider | pipedrive / salesforce / hubspot |
| crm_api_key | Provider API token |
| crm_sync_interval | Minutes between sync |
| telegram_bot_token | Bot token (XXX:YYY) |
| openrouter_api_key | OpenRouter key |
| model_task | Preferred model |
| test_phone | Dev recipient for calls |
| test_email | Dev recipient for emails |