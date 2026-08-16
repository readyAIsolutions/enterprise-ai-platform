# Real Stripe Checkout + "Real site, no fake data" recipe (AC PE$0 download-gate site)

Concrete pattern proven on the AC PE$0 artist site (`~/Desktop/ac pe$0`, Starlette :8533).
Applies to any artist/music site with a SoundCloud download gate + a paid beatpack store.

## The core rule LO enforced
A site that's going live ("it's a real site") must NEVER carry demo data that
looks like real activity: fake `status='paid'` orders, fake subscribers,
placeholder products with fake cover URLs (`artworks-0000000004`), seeded
curator rosters with `@example.com` emails. He will catch it. Purge rows AND the
seeders.

## stripepay.py (small helper)
```python
import stripe
def enabled(db):   return bool((db.get_setting("stripe_secret_key") or "").strip())
def configure(db):
    sk = (db.get_setting("stripe_secret_key") or "").strip()
    if not sk: raise RuntimeError("Stripe secret key is not configured.")
    stripe.api_key = sk; return stripe
def currency(db):  return ((db.get_setting("stripe_currency") or "USD").strip() or "USD").lower()
def cents(a):      return int(round(float(a) * 100))
```
Config keys (config.py MAPPING → db settings): STRIPE_SECRET_KEY / PUBLISHABLE /
WEBHOOK_SECRET / CURRENCY. Admin settings form writes them.

## Checkout (hosted session — never fake the payment)
```python
order = db.create_order(bp_id, email, float(price), currency, "pending")
site = (db.get_setting("site_url") or SITE_URL).rstrip("/")
sess = stripe_pay.checkout.Session.create(
    mode="payment",
    customer_email=email,
    client_reference_id=order["id"],
    line_items=[{"price_data": {"currency": currency,
                 "unit_amount": stripepay.cents(price),
                 "product_data": {"name": bp["title"], "images": [cover] if cover else []}},
                 "quantity": 1}],
    success_url=f"{site}/beatpack/order/{order['download_token']}?session_id={{CHECKOUT_SESSION_ID}}",
    cancel_url=f"{site}/beatpack/{bp['slug']}",
    metadata={"order_id": order["id"], "beatpack_id": bp_id})
db.set_order_stripe(order["id"], sess["id"])          # store stripe_session_id
return JSONResponse({"ok": True, "checkout_url": sess["url"]})
```
FREE packs (`price<=0`): create order `status='paid'`, return `download_url`
directly (genuinely free). If `not stripepay.enabled(db)`: return 400
"Payments aren't connected yet" — never fabricate a sale.

## Confirming payment (two paths, both needed)
- **Webhook** `/stripe/webhook` (POST): `event = stripe.Webhook.construct_event(
  payload, request.headers["stripe-signature"], whsec)`; on
  `checkout.session.completed` mark order `paid` (match by metadata.order_id /
  client_reference_id, else lookup `stripe_session_id`). store `payment_intent`.
- **On-return**: helper queries `Session.retrieve(sess_id)`; if
  `payment_status == "paid"` mark paid before serving the download file. The
  download endpoint 402s unless order status is `paid`.

## Order columns to add (SQLite migration)
`ALTER TABLE orders ADD COLUMN stripe_session_id TEXT DEFAULT '';`
`ALTER TABLE orders ADD COLUMN stripe_payment_id TEXT DEFAULT '';`
Plus `free_for_profit INTEGER DEFAULT 0` on releases for the FFP tab.
Migration must be idempotent (`PRAGMA table_info(...)` check before ALTER).

## Auto-sync "[FREE FOR PROFIT]" tab from SoundCloud
- `sc.user_tracks(token)`: `GET /me/tracks?limit=200` → list of
  {id, title, permalink_url, artwork_url (`-large.`→`-t500x500.`)}; **mock mode
  returns []** so tests never fabricate a catalog.
- Filter: `sc.is_free_for_profit_title = "free for profit" in (title or '').lower()`.
- Admin-only `POST /api/sync-ffp`: find the owner fan by `admin_sc_username`/
  `admin_sc_email`, use its stored `sc_access_token`; upsert each match as a
  release keyed by `soundcloud_track_id` (keep `lossless_file` on updates);
  return `{scanned, free_for_profit, added, updated}`.
- A `free_for_profit_page` route renders a `free_for_profit.html` template;
  nav link `[FREE FOR PROFIT]` (cyan); card shows a `FREE FOR PROFIT` badge and
  "Like · Repost · Comment to unlock" CTA.

## Regression tests that held the contract
- `test_no_fake_stripe_orders_when_not_configured` — checkout with Stripe off
  must 400 and create NO order (or none `paid`).
- `test_free_beatpack_downloads_without_payment` — price 0 → 200 + download_url.
- `test_beatpacks_page_renders` — ALSO asserts the removed `/api/seed` now
  404s (this only passes after the 404 handler returns `status_code=404`).
- `test_free_for_profit_*` — FFP page renders, flagged release appears, nav
  links to it.

## Gotchas hit
- `/releases` upsert UPDATE path must include the new col AND a `?` per binding;
  missing a binding silently breaks only the UPDATE path. Count both sides.
- 404 handler must `status_code=404` or removed routes still 200 (see SKILL.md).
- Paths with `$` (dir `ac pe$0`): single-quote in shell.
- stale `__pycache__` + old process holding the port → `fuser -k 8533/tcp`.
