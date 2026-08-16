# Stripe payment completion + beatpack delivery (gotchas)

Covers the paid-beatpack flow on this artist-gate site: confirming Stripe
payments server-side, marking orders paid, and emailing the buyer their pack.

## PITFALL: stripe lib v15 returns StripeObject, not dict — `.get()` crashes (CRITICAL)
The installed `stripe` lib (>= v15) returns `_stripe_object.StripeObject` for
API reads. That object supports `obj["key"]` and `obj.to_dict()` but **NOT**
`.get()`. Calling `.get()` raises `AttributeError`.

Why this is nasty: the crash happens inside `try/except Exception` blocks
(`_confirm_stripe_payment`, `stripe_webhook`, `_auto_sync_beatpack_stripe`), so
it fails SILENTLY — the function just bails and returns early.

Real-world symptom chain when this bites:
- `POST /stripe/webhook` returns **500** (Stripe keeps retrying; check
  `journalctl --user -u <svc>` for `POST /stripe/webhook ... 500`).
- Orders that were REAL paid Stripe sessions stay stuck at `status = pending`
  in the DB even though `payment_status == "paid"` on Stripe.
- Fan purchase never recorded → empty "My purchases".
- Beatpack email never sent.
- `_auto_sync_beatpack_stripe` crashes → beatpack never gets
  `stripe_product_id` / `stripe_price_id` → product not linked in Stripe catalog.

### Fix: normalize with a `_sd()` helper at every Stripe read
```python
def _sd(obj):
    if isinstance(obj, dict):
        return {k: _sd(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sd(v) for v in obj]
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):          # real stripe v15 uses .to_dict()
        return _sd(obj.to_dict())
    return obj
```
Then `sess = _sd(stripe_pay.checkout.Session.retrieve(id))` before any `.get()`.
In v15 the object has `.to_dict()` (NOT `to_dict_recursive`); older/other libs use
`to_dict_recursive`, so `_sd` checks both. Cover with a unit test that feeds a
fake object exposing `[]` + `to_dict()` but raising `AttributeError` on `.get()`
(that is exactly the real-lib shape).

### Debugging recipe
1. If a Stripe purchase "went through" but the site order is still pending,
   query Stripe directly to separate the layers:
   `stripe.checkout.Session.list` → is `payment_status == paid`? If yes, the
   SITE failed to confirm (code bug / webhook), not the payment.
2. Check the server log for `POST /stripe/webhook ... 500` — a 500 on the
   webhook IS the payment-confirmation path failing.
3. Corroborate by checking DB orders: `status='pending'` rows WITH a
   `cs_live_...` stripe_session_id are the smoking gun.
When migrating to a new major version of any SDK, grep for `.get(` on returned
API objects — a `.get()` that used to work silently becomes an error.

## PITFALL: Gmail attachment limit ~25MB — give a download link, not just the file
Gmail API rejects attachments over ~25MB. A beatpack zip (e.g. 60MB) will FAIL
to send as an attachment. Always:
- Send the email with the file **attached only if `len(data) <= ~24MB`**.
- ALWAYS include a personal download link: `/beatpack/order/{order_token}`.
  That route is cryptographically keyed by the unguessable `download_token` and
  serves the file once the order is `paid` — so it is a safe, self-contained
  delivery channel. Make it a big red button in the email.
- Pattern: `_email_beatpack_to_buyer(order, bp)` is best-effort, catches all
  exceptions, never breaks the download flow. It also notifies the admin email
  (`admin_sc_email`) with a lightweight "new sale" line.

`gmailapi.build_message`/`send` gained an `attachments=[(filename, bytes)]`
param (uses `MIMEApplication`, outer `multipart/mixed` with an inner
`multipart/alternative` body).

## Pitfall: guest Stripe return must NOT hit the members-only login gate
The Stripe success_url returns the buyer to `/beatpack/order/{token}?...`. If
that path is under a protected page prefix, an anonymous guest (Stripe checkout
needs no site login) gets 303-bounced to `/login` instead of their download.
Whitelist `/beatpack/order/` as a PUBLIC prefix — the unguessable token is the
credential, and payment is re-confirmed server-side before serving.

## Editorial / ownership preferences (site owner LO)
- **Front-page text is OWNER-OWNED and permanent.** tagline, hero_kicker,
  hero_desc (and newsletter/OG text) are set ONLY via Admin → "Save front page
  text". NEVER auto-edit, regenerate, or rewrite them. Persist values verbatim;
  honor "blank = keep current" in the save handler (a blank submitted box must
  leave the stored value untouched, not clear it to a template fallback).
- **No third-party services/API keys "not ours".** Do not pull in third-party
  avatar/AI/soundboard services or paste the reference file's external API keys
  into our code. Any browser-side fallback (e.g. avatar) should be generated
  locally (deterministic SVG data-URL), keep zero external network calls.
