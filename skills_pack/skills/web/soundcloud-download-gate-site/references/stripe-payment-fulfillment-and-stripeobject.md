# Stripe payment fulfillment, StripeObject `.get()` crash, and beatpack email

Everything learned keeping the Stripe beatpack store actually paying out. Written
2026-08-02 (upgrade #64/#65 on acpeso.shop).

## The big one: installed stripe lib returns objects WITHOUT `.get()`

The `stripe` Python lib (as of v15.4.x) returns `_stripe_object.StripeObject`
instances from ALL API reads (Product/Price/Checkout.Session/PaymentIntent
listing & retrieve). These objects:
- support `obj["key"]` and `obj.method` attribute access,
- expose `.to_dict()` (and `.to_dict_recursive()` in some versions),
- do **NOT** have `.get()` — calling `sess.get("payment_status")` raises
  `AttributeError`, which if unhandled becomes a 500.

### Symptom signature (very misleading)
Payments look like they "work" (Stripe Checkout session created, user paid on
Stripe, payment_status=paid) but the site order stays `pending` forever, no
email goes out, nothing shows in the buyer's purchase history, and the
Stripe-backed product never links into the catalog. If you check the server log
you see Stripe's webhook POST arriving but returning `500 Internal Server
Error` (via uvicorn `POST /stripe/webhook HTTP/1.1" 500`). THE WEBHOOK FIRES —
the handler is crashing.

### Fix: one `_sd()` normalizer used at every Stripe read edge
```python
def _sd(obj):
    if isinstance(obj, dict):
        return {k: _sd(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sd(v) for v in obj]
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):      # stripe v15 uses to_dict()
        return _sd(obj.to_dict())
    return obj
```
Every place you receive a Stripe object, wrap immediately: `sess = _sd(
stripe_pay.checkout.Session.retrieve(id))` then read with `.get(...)`. Do this
in: payment-confirmation, the webhook handler (`event["data"]["object"]` →
`_sd(...)`), and the Product auto-sync (`Price.list(...)` → `_sd(...)` then
`.get("data", [])`).

`Product.create/modify` return objects you read with `prod["id"]` — that `[]`
access works, so only `.get()` calls crash. Let existing non-`.get()` stripe
reads (e.g. `sess["id"]`, `sess["url"]`) stay as `[]`.

### Testing it (so it doesn't regress)
The site's `_FakeStripe` returns plain dicts, so `.get()` works in tests and the
bug hides. Add a fake that mirrors the REAL lib — supports `[]` + `to_dict()`
but raises `AttributeError` on `.get()` — and assert the confirm path still
flips the order to paid. See `test_confirm_stripe_payment_handles_stripeobject`.

## Post-payment fulfillment should be one idempotent helper
Once an order is confirmed paid, do all side effects in one best-effort,
never-raising function so the download can never be blocked by a failed email:
```python
def _fulfill_paid_order(order):
    try:
        if order.get("fan_id"):
            db.mark_fan_purchase(order["fan_id"], order.get("beatpack_id"), order["id"])
        if order.get("email"):
            db.add_subscriber(order["email"], "beatpack")
        _email_beatpack_to_buyer(order)
    except Exception:
        pass
```
Call it from exactly three places: (1) `_confirm_stripe_payment` after flipping
to paid, (2) the `checkout.session.completed` webhook, (3) the free-beatpack
checkout path (free = already "paid", no Stripe). Never duplicate the fan-
purchase/email logic inline.

## Gmail attachment cap (25MB) → always give a download link too
The beatpack zip was 60MB; Gmail rejects attachments over ~25MB, so
`send_with_attachment` would 500 and the buyer gets nothing. Rule:
- attach the file only when `len(data) <= 24 * 1024 * 1024`,
- ALWAYS embed a personal download button/link in the body pointing at
  `/beatpack/order/{download_token}` (unguessable token = the credential; it
  only serves after the order is paid).
- Buyer-email body should say "attached, but use the link if your provider
  blocked it" vs "too big to attach, grab it from the secure link."

`gmailapi.build_message`/`send` gained an `attachments=[(filename, bytes)]`
param; build a `MIMEMultipart("mixed")` with a nested `alternative` body part
plus `MIMEApplication` parts (one per file). Plain `MIMEMultipart("alternative")`
can't carry attachments.

## Members-only login gate vs. post-checkout success URLs
If the site is behind a members-only gate (anonymous → `/login`) and a guest
can pay via Stripe (Stripe needs NO site login), the Stripe success_url must be
whitelisted or the returning guest gets bounced to `/login` and never receives
their file/order.
- The success URL `/beatpack/order/{token}` fell under the protected
  `/beatpack/` prefix. Whitelist the specific `/beatpack/order/` in the public
  prefixes BEFORE the protected check. Safe because it's keyed by the
  unguessable download_token and re-verifies payment server-side.
- General rule: any "public URL that is its own credential" (order/download
  token URLs) must be whitelisted; a plain content path will be gated.

## Reconcile already-paid orders after fixing the bug
After the crash fix, don't just let future purchases work — backfill the stuck
ones. Iterate `all_orders()` where `status != 'paid'` and
`stripe_session_id.startswith('cs_live_')`, call `_confirm_stripe_payment(order)`
(now fixed), which flips to paid + fulfills. Leave genuinely-`open`/`unpaid`
sessions as pending (correct).

## Stripe product catalog orphan cleanup
Duplicate/orphan products in Stripe accumulate when syncs crash midway (there
were 3 products for one beatpack: one active with no default_price, one
inactive, one freshly created). Re-running the idempotent auto-sync with the
`_sd` fix creates ONE clean active product + default_price and persists
`stripe_product_id`/`stripe_price_id` on the beatpack; then `Product.modify(id,
active=False)` the orphan/leftover ids.

## Don't port third-party API keys / external services from reference code
When importing a "cool reference" front-end (chat, soundboard, effects), the
reference often carries its OWN third-party API keys, AI-service credentials, or
external avatar/CDN calls that are NOT ours and must not leak in. Audit before
shipping:
- grep the whole app for `sk-`, `AIza`, `pk_live/test_`, `api[_-]?key`, known
  provider hostnames — must come back clean.
- Replace any external service dependency with a local equivalent (e.g. avatar
  generator: an inline deterministic SVG data-URL from the user id instead of
  `api.dicebear.com`). Zero external calls keeps the app self-contained and
  avoids vendoring someone else's key/service.
