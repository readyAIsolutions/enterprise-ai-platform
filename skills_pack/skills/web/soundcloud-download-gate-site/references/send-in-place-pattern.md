# Send-in-place: making AI artifacts actionable AND sendable (honest safety rails)

Extension of the "close-the-loop" pattern. Every AI artifact must not only be
openable/copiable in the admin panel — when it is a message meant for a real person
(reward note / thank-you, follow-up nudge, pitch), give the admin a real primary action
to deliver it, plus honest rails so the system never fakes a delivery.

## The pattern (close-the-loop + send)
`aiwriter` fn (AI f(x) + deterministic fallback) → auth-gated route that, in addition to
`{ok, subject, body}` returned to the JS, also returns the delivery metadata the UI needs
to know whether a real send is even possible:
- `email` (the target's address on file, or null)
- `can_send` (is a sender configured? e.g. Gmail-API/SMTP enabled)

Then a separate POST route does the actual delivery (e.g. `/admin/<x>-send`), taking the
target id + subject + body. The JS only shows the "Send" button when the route said it is
possible.

## Honest safety rails (NEVER fabricate a send)
1. **dry_run=1** (preview) path that works BEFORE any sender is configured — so the loop
   is testable in a clean env. Real send requires a configured sender.
2. **Refuse loudly, not silently.** If the target has no email on file, or no sender is
   configured, return a clear `{ok:false, reason}` and surface it in the UI ("add an email
   first", "email sending not configured") — no fake success, no dead click.
3. **Provide the email-input/save path** inline so the admin can fill the missing target
   (e.g. a per-fan "Save email" form in the Community/CRM tab, db helper `update_fan_email`).
   The note popup then flips to a real "✉ Send to {email}" button once both target+email
   and sender exist.
4. **Log every real send** (email_log) so the panel carries a record and the admin can
   audit who was actually contacted.
5. Only ever send via the ONE configured email stack (Gmail-API via Google Cloud OAuth /
   SMTP) — never invent a transport, never mark "sent" when nothing went out.

## UI state machine for the send button
- no email on record  → show the save-email input + hint
- email present, no sender → show "email exists but sender not configured" hint
- email present + sender → show "✉ Send to {email}" → on click confirm → "✓ Sent to {email}"

## Verified example (AC PE$0 Community tab, 2026-08)
Reward note ("💬 Reward note" per fan) got a "✉ Send to {email}" action backed by
`/admin/fan-note-send` (fan_id + subject + body, dry_run flag) + `/admin/fan-email`
(set/clear target email, db `update_fan_email`). Tests: report email/can_send, set+clear
email, refuse-send-without-email, dry-run. 55/55 pass. JS cache-bumped, server restarted.
