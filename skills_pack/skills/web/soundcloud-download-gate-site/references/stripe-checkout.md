# Real Stripe checkout in Starlette (no fake "paid" orders)

The user's hard rule: an order is only ever `paid` when Stripe itself confirms
it. Never mark paid inline just to "demo" the flow.

## Key prefix sanity-check FIRST
If Stripe returns **401 "Invalid API Key"** on any call, almost always the secret
key prefix is wrong before you chase endpoint bugs:
- **Secret** key = `sk_live_...` / `sk_test_...` → `stripe.api_key`.
- **`mk_...`** is a merchant/restricted key — NOT a valid `api_key`; returns 401 on
`stripe.Account.retrieve()`.
- Publishable key = `pk_live_...`/`pk_test_...` (frontend, non-secret).
- Webhook signing secret = `whsec_...` (only for `Webhook.construct_event`).
Ask the user for the `sk_live_...`/`sk_test_...` secret — do not burn time on
config/endpoint debugging when the prefix is wrong.

## Config
Keep keys in DB settings via the config loader, then a thin helper module:
```python
# stripepay.py
import stripe
def enabled(db):  return bool((db.get_setting("stripe_secret_key") or "").strip())
def configure(db):
    stripe.api_key = db.get_setting("stripe_secret_key").strip()
    return stripe
def cents(amount): return int(round(float(amount) * 100))
def currency(db):  return (db.get_setting("stripe_currency") or "USD").lower()
```

## Checkout (create the session, hand off to Stripe)
```python
order = db.create_order(bp_id, email, price, currency, "pending", fan_id)
sess = strip.configure_sess(db).checkout.Session.create(
    mode="payment", customer_email=email, client_reference_id=order["id"],
    line_items=[{"price_data": {"currency": currency,
        "unit_amount": cents(price),
        "product_data": {"name": title, "images": [cover]}},"quantity": 1}],
    success_url=f"{site}/beatpack/order/{token}?session_id={{CHECKOUT_SESSION_ID}}",
    cancel_url=f"{site}/beatpack/{slug}",
    metadata={"order_id": order["id"], "beatpack_id": bp_id})
db.set_order_stripe(order["id"], sess["id"])   # stores stripe_session_id
return JSONResponse({"ok": True, "checkout_url": sess["url"]})
```
If `stripepay.enabled(db)` is False → return 400 "payments aren't connected yet",
NEVER fake a sale.

## Free packs (price 0)
Bypass Stripe entirely — create the order as `paid` and return a `download_url`.
That is genuinely free, and it is the one place a `paid` order is created without
Stripe (correctly).

## Confirm payment in two places
1) On the success redirect (fan returns from Stripe) — `beatpack_download` calls
`_confirm_stripe_payment(order)` which does `Session.retrieve(stripe_session_id)`
and flips to paid only if `payment_status=="paid"`.
2) Server-side via webhook:
```python
async def stripe_webhook(request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")  # or ""
    event = stripe.Webhook.construct_event(payload, sig, whsec)
    if event["type"] == "checkout.session.completed":
        sess = event["data"]["object"]
        order = db.get_order(metadata.order_id) or db.get_order_by_stripe_session(sess["id"])
        db.set_order_status(order["id"], "paid")
        db.set_order_stripe(order["id"], sess["id"], sess.get("payment_intent"))
        db.mark_fan_purchase(order["fan_id"], order["beatpack_id"], order["id"])
```
On any confirmation that flips to paid, also record `fan_purchases(fan_id, beatpack_id)`
so the client "What I've bought" library is correct.

## "Not a valid URL" — Stripe rejects RELATIVE image URLs (UPGRADE #57)
Beatpack covers are stored in the DB as RELATIVE paths (`/media/cover-<id>.jpg`).
If you pass one raw into `line_items[].price_data.product_data.images`, Stripe
fails the whole Checkout.Session.create with the unhelpful message:
```
Couldn't start checkout: Not a valid URL
```
Normalize every image URL to absolute before handing it to Stripe:
```python
def _absolute_url(url, site_url):
    url = (url or "").strip()
    if not url: return ""
    if str(url).startswith(("http://","https://","//")): return url
    if str(url).startswith("/"):
        base = (site_url or "").rstrip("/")
        return base + url if base else url
    return url
images = [_absolute_url(bp["cover_url"], site) for u in [bp["cover_url"]] if _absolute_url(u, site)]
```
- Apply it in BOTH places that hand images to Stripe: `beatpack_checkout` (the
  inline `price_data` branch) AND `_auto_sync_beatpack_stripe` (catalog sync),
  or the two paths drift and only one is fixed.
- Regression test: `test_checkout_images_normalized_to_absolute_url` asserts a
  relative `/media/...` path becomes `https://acpeso.shop/media/...`, absolute
  http(s) and protocol-relative URLs pass through unchanged, empty stays empty.
- Even when a `stripe_price_id` exists (catalog path), the checkout inline path
  is still reachable, so guard both.

## Tests
- Assert a paid beatpack is NOT marked paid when Stripe is unconfigured (400,
  and `db.all_orders()` unchanged).
- Assert a free beatpack returns a `download_url` immediately.
