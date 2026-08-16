# API Key Troubleshooting

## Vapi.ai
- **Public key**: `OQ...` - For embedding in client-side code
- **Private key**: `sk_live_...` - For server-side API calls
- Error: "Invalid Key. Hot tip, you may be using the private key instead of the public key, or vice versa" = key type mismatch

## Twilio
- **Account SID**: Starts with `AC...` (found in Twilio Console > Project Info)
- **Auth Token**: Separate field from API keys
- **Format in Settings**: `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx:your_auth_token_here` (both joined by colon)
- Test endpoint: `POST https://api.twilio.com/2010-04-01/Accounts/{ACCOUNT_SID}/Calls.json`
- Requires Basic Auth: `base64(AccountSID:AuthToken)` in Authorization header

## Resend
- **Restricted key error**: `{"statusCode":401,"message":"This API key is restricted to only send emails"}`
- **Fix**: Create API key with "Full access" or ensure key has "send" permission
- Test: `curl -X POST https://api.resend.com/v1/emails -H "Authorization: Bearer re_..." -d '{}'`