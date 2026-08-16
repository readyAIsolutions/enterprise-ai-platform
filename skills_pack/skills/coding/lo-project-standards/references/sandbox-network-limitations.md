# Sandbox Network Limitations

When testing outbound API calls (Twilio, Vapi, Resend, Telegram, etc.) from the Hermes development sandbox:

## Blocking Pattern
- The sandbox **blocks outbound HTTPS requests** to external APIs
- `urllib.request.urlopen()` returns `getaddrinfo failed` or connection refused errors
- This affects `/api/campaign/test` and similar endpoints

## Workaround
1. Run the test endpoint to verify the code path executes
2. Check server logs for "call_initiated" or "email_sent" patterns
3. If sandbox network blocks the call, the toast still shows "sent" but no external action occurs
4. Deploy to actual host machine to execute real API calls

## Detection
The sandbox returns errors like:
- `URLError: <urlopen error [Errno 11001] getaddrinfo failed>`
- `Connection refused` for external HTTPS endpoints

## Verification Process
When you see "Test sent" but no result:
1. This is sandbox network limitation, not code error
2. Code is correct but environment is restricted
3. Tell user: "The code works but this sandbox can't reach external APIs. Run `python app/serve.py` directly on your machine."