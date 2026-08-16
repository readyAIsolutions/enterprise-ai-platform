# Stripe v15 StripeObject + payment fulfillment & email (durable patterns)

## THE #1 PITFALL: Stripe Python v15.x returns StripeObject, NOT dict — no `.get()`

From stripe >= ~9 and definitely at v15.4.0, **every API READ** (Product.list,
Price.list, checkout.Session.retrieve, Webhook event objects, Account.retrieve,
PaymentIntent.list, ...) returns a `stripe._stripe_object.StripeObject`. That
object supports `obj["key"]` and `.to_dict()`, but **NOT `.get()`** — calling
`.get()` raises `AttributeError` (it falls through to `__getattr__` → AttributeError).

Consequence: any legacy code that does `sess.get("payment_status")`,
`existing.get("data", [])`, `prod.get("name")` etc. **crashes with a 500**, and the
crash is often INSIDE a try/except that swallows it or an exception handler that
returns a 400/500. The killer symptom set (all from one bug):

- Stripe webhook fires (dashboard shows the endpoint enabled + `checkout.session.completed`
  subscribed) but the server logs `POST /stripe/webhook → 500 Internal Server Error`.
- Orders stay `pending` forever even though the Stripe checkout is `status: complete,
  payment_status: paid`.
- No fan purchase recorded, no buyer email, product auto-sync never persists
  `stripe_product_id`/`stripe_price_id`.

### The fix: normalize at the edge of every Stripe read

```python
def _sd(obj):
    """Convert a StripeObject (nested StripeObjects/lists) into plain dicts/lists
    so legacy `.get()` access works. Real lib (v15) exposes `.to_dict()` (older
    had `.to_dict_recursive()`). Normalize once at the edge of every Stripe read."""
    if isinstance(obj, dict):
        return {k: _sd(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sd(v) for v in obj]
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return _sd(obj.to_dict())
    return obj
```

Apply it to EVERY read: `sess = _sd(stripe_pay.checkout.Session.retrieve(id))`,
`existing = _sd(stripe_pay.Price.list(product=pid, limit=100))` (then
`existing.get("data", [])` works), `sess = _sd(event["data"]["object"])` in the webhook.

### Regression test that mirrors the REAL lib (so it can't lie)

Plain dicts passed by a naive `_FakeStripe` will NOT reproduce the bug. Build a fake
StripeObject that supports `[]` and `to_dict()` but raises AttributeError on `.get()`:

```python
class _RealLikeStripeObj:
    def __init__(self, data): self._data = data
    def __getitem__(self, k): return self._data[k]
    def to_dict(self):
        return {k:(v.to_dict() if hasattr(v,'to_dict') else v) for k,v in self._data.items()}
    def __getattr__(self, k): raise AttributeError(f"'{k}' — StripeObject has no .get()")
```

Assert that calling `.get()` on the raw object raises AttributeError (proving `_sd`
is what made the code work), and that `_confirm_stripe_payment` flips the order to
`paid` + records the fan purchase.

## Payment fulfillment — ONE idempotent function, 3 call sites

Before shipping, verify the POST-payment side effects actually fire (they won't if
the webhook 500s from the `.get()` bug). Keep them in a single best-effort helper:

```python
def _fulfill_paid_order(order):
    # record fan purchase -> mark_fan_purchase(fan_id, beatpack_id, order_id)
    # add subscriber -> add_subscriber(email, source)
    # email the buyer -> _email_beatpack_to_buyer(order)
    pass  # wrap each in try/except; NEVER let an email outage break the download
```

Call it from: (1) the `checkout.session.completed` webhook, (2)
`_confirm_stripe_payment` (the return-to-merchant path), and (3) the free-pack
checkout path. It must be idempotent (orders already paid return early).

## Stripe receipts — make Stripe email the buyer

On Checkout `Session.create`, set `payment_intent_data={"receipt_email": email}`
(both the `price_id` and `price_data` branches). That populates the PaymentIntent's
`receipt_email` so Stripe emails a receipt on success. Note: the master "send
receipts" toggle is in **Stripe Dashboard → Settings → Emails** — API cannot
reliably flip it; mention it to the user. The site's own delivery email still goes
out on every confirmed purchase regardless.

## Emailing a delivered file (beatpack/download) — email-client-safe

- **Gmail attachment cap ~25MB.** Only attach the file when `len(data) <= 24*1024*1024`.
  When too big, DON'T drop delivery — always include a personal download link.
  Use the unguessable order-token URL (whitelisted public; the token is the
  credential) as the download button href.
- **Button must be `display:block` with a SHORT label.** An inline `<a>` with
  padding whose label is the full long product title renders as a giant wrapping
  red blob that overlaps surrounding text in Gmail/Outlook. Put the long title in
  a heading, and make the CTA a full-width `display:block; text-align:center`
  anchor labeled e.g. "DOWNLOAD YOUR PACK". Separate paragraphs get their own
  margins (no zero-margin stacking). Email-safe: inline styles only, no web fonts.
- **Ownership copy:** for PAID packs, do NOT say "free for profit / tag @acpeso" —
  the buyer owns it. Say "You own this pack outright. Use it however you want."
  Keep the "tag @artist" line only for the free/gated downloads.

## Owned-state on the storefront page (don't re-ask for payment)

A storefront page shows the buy button unless the handler checks for a **confirmed
PAID order** for the current fan. Add a helper that returns (owns, download_url)
only for a paid order matched by fan_id OR email, and pass it to the template so it
renders "✓ You already own this. Stripe confirmed." + a Download button instead of
checkout. It must key off `status == "paid"` (flipped by the webhook) so it only
appears AFTER Stripe confirms.

## Login / gate nuances

- Whitelist the order-token consumer path (`/beatpack/order/`) as PUBLIC even on a
  members-only site — the unguessable token is the credential and post-payment
  return would otherwise bounce to /login.
- "Mostly members-only" sites: the home/landing page can be public while the actual
  functions (store, analyzer, community chat, history, downloads) force login.
  Keep the gate off `/` and on the functional prefixes.

## UI font/readability pitfall (this project)

A decorative/blackletter/"brand" font is fine for large decorative elements (brand
wordmark, hero splash) but **destroy legibility on small nav buttons** — especially
uppercase + letter-spacing + a blurry text-shadow glow. Keep nav/CTA buttons in a
readable sans (Space Grotesk / Inter / Anton for a bold wordmark). Let the user tell
you which elements keep the fancy font and which must be readable.
