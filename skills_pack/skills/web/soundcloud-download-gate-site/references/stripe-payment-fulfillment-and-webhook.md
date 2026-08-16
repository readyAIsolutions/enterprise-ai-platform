# Stripe payment fulfillment, webhook, and digital-delivery — gotchas

All lessons below are from real production failures on the acpeso live site. Each one
cost a debugging session; trust them.

## 1. Newer `stripe` lib StripeObjects have NO `.get()` — the #1 silent killer

The installed `stripe` package (v15.x in this environment, and now into the future)
returns `_stripe_object.StripeObject` for API reads. That object supports:

- `obj["key"]` (subscripting) — OK
- `obj.to_dict()`  (NOT `to_dict_recursive`) — OK
- `obj.attr`  — OK
- `obj.get("key")`  — **AttributeError**, it does NOT exist

So any legacy code path that does `sess.get("payment_status")`, `event["data"]["object"].get(...)`,
`Price.list(...).get("data")` crashes. Worse: it happens *inside* try/except or inside
`stripe_webhook`, so:

- The Stripe webhook returns **500** to every post → orders never flip to `paid`.
- Payment confirmation is skipped → no fan purchase recorded, no email, no "My purchases".
- Product auto-sync silently fails → the beatpack product never links into the Stripe catalog.

**Diagnosis:** if a buyer "paid but never got their download", check `journalctl --user -u acpeso`
for `POST /stripe/webhook ... 500 Internal Server Error` and a traceback ending in
`AttributeError: get` / `KeyError: 'get'` from `_stripe_object.py`.

**Fix (the `_sd` normalizer):** convert every Stripe object to a plain dict at the edge of
every read, then keep using `.get()` as normal:

```python
def _sd(obj):
    if isinstance(obj, dict):
        return {k: _sd(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sd(v) for v in obj]
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):          # real v15 lib uses .to_dict()
        return _sd(obj.to_dict())
    return obj
```

Use it on: `checkout.Session.retrieve(...)`, `event["data"]["object"]` in the webhook, and
`Price.list(...)` in the catalog auto-sync. A unit test that mirrors the real lib —
an object with `__getitem__` + `to_dict()` but NO `.get()` — proves the path stays fixed.

## 2. Post-payment side effects belong in ONE idempotent "fulfill" function

Order confirmation happens on two independent paths (the webhook AND the
return-to-merchant success URL `_confirm_stripe_payment`). Both must trigger: mark paid,
record the fan purchase, add the subscriber, email the buyer. Duplicate them and they
drift. Instead centralize:

```
_fulfill_paid_order(order):
    mark_fan_purchase(fan_id, beatpack_id, order_id)
    add_subscriber(email, "beatpack")
    _email_beatpack_to_buyer(order)   # always best-effort, never raises
```

and call it from the webhook handler and `_confirm_stripe_payment` (and the free-pack path).

## 3. Digital-delivery email: Gmail caps attachments ~25MB

Gmail API rejects messages with attachments over ~25MB. Beatpacks are frequently 50MB+.
Rule: attach the file ONLY when `len(data) <= 24*1024*1024`, and ALWAYS include a personal
download link as the primary delivery. The link is the order's unguessable
`/beatpack/order/{download_token}` (see gotcha 4). Body copy must tell the buyer whether
the file is attached or waiting behind the link.

**Email button / layout formatting (LO: "the formatting is fucking ass, buttons cutting
over each other").** Do NOT render the CTA as an inline `<a>` with padding whose label
crams in the long product title (e.g. "DOWNLOAD AC PE$0 BEATPACK 1 [SLAYR, ...]") — in many
clients it wraps into a giant red blob that mashes into the surrounding text. Instead:
put the product title in a heading, use a **single short label** ("DOWNLOAD YOUR PACK"), and
style it as **`display:block; text-align:center;` with its own padding** (a full-width row
that structurally cannot collide with neighboring paragraphs). Keep text in separate
spaced `<p>` blocks. All styling inline (email-safe) — no web fonts, no external CSS. A
quick build-and-parse check (base64-decode the raw, parse with EmailParser, assert exactly
one `display:block` button and the long title NOT inside it) verifies before sending.

## 4. Login / members-only gate must whitelist post-payment order URLs

A members-only middleware redirects anonymous users to `/login` for content pages. But a
Stripe checkout needs no site login — so after paying, the buyer's browser returns to the
success URL `.../beatpack/order/{token}` with NO fan cookie and gets bounced to `/login`
instead of their download. Fix: whitelist `/beatpack/order/` as a PUBLIC path prefix
(check it BEFORE the protected `/beatpack/` prefix). The unguessable `download_token` IS
the credential, and payment is still re-verified server-side before serving, so leaving it
public doesn't leak anything.

## 5. Verify the product is actually linked in the Stripe catalog

"Product not in the Stripe catalog" usually means the DB beatpack row has an empty
`stripe_product_id`/`stripe_price_id` — the auto-sync crashed (often due to gotcha 1, or it
predates the sync). Re-run `_auto_sync_beatpack_stripe` for the pack, confirm the DB now
holds both IDs and Stripe shows one ACTIVE product with a `default_price` at the current site
price. Deactivate orphan/duplicate products left over from earlier broken syncs so the
catalog stays clean.

## 6. Stripe's own receipt email is separate from your delivery email

A "no email from Stripe" complaint can be two different things: (a) our delivery email
(we control it), and (b) Stripe's receipt email (controlled in Stripe Dashboard →
Settings → Emails). Don't claim the site controls Stripe receipts. You CAN still nudge
Stripe to email one by setting the receipt address on the underlying PaymentIntent at
checkout creation — add `payment_intent_data={"receipt_email": email}` to **both**
`checkout.Session.create(...)` branches (the stored-price branch AND the inline
`price_data` branch). That sets `payment_intent.receipt_email` so Stripe sends a receipt
to the buyer whenever the account's receipt toggle is enabled. (A bare `customer_email`
does NOT set it; real runs showed `payment_intent.receipt_email = None` without this.)

## 7. Product page must show an "owned" state once paid (not re-offer purchase)

After a Stripe-confirmed purchase, LO revisits the product's own page and expects to see
he owns it — if the page still shows the checkout/buy button he reports "it still asks me
to purchase downloads I've already bought." The bug was simply that the page handler never
checked ownership, so the template always rendered the buy form.

On each paid product page compute ownership from the fan's PAID order (match by `fan_id`
OR the order email), never from anything weaker:

```
def _fan_owns_beatpack(fan, beatpack_id) -> (owns: bool, dl_url: str):
    if not fan or not beatpack_id: return False, ""
    for o in all_orders():
        if o.beatpack_id != bid or o.status != "paid": continue
        if (o.fan_id and o.fan_id == fan.id) or (o.email.lower() == fan.email.lower()):
            return True, f"/beatpack/order/{o.download_token}"
    return False, ""
```

Pass `owns`/`dl_url` into the template and render an owned block ("✓ You already own this
pack — Stripe confirmed your purchase" + a **Download** button pointing at the order's
secret-token URL) INSTEAD of the buy form. Only a Stripe-CONFIRMED `paid` order counts —
`pending` / guest-open sessions must NOT grant the state (this is the "should popup after
I've purchased and Stripe has confirmed it" requirement). Free/"get it" packs also create a
`paid` order, so the same detection covers them. Add a regression test: same fan sees the
buy form with no order, then sees the owned block (and no buy button) after a paid order is
inserted.

## Front-page text ownership (user preference — acpeso)

LO owns the front-page text (tagline, hero_kicker, hero_desc, newsletter, OG). It is set
via Admin → "Save front page text" and is PERMANENT until he changes it. NEVER auto-edit,
regenerate, or rewrite it. The admin save handler must honor "blank = keep current" so a
blank box never resets his copy (only a newly-typed value updates it). Also: keep the
## Font preference nuance (acpeso — LO clarified this)

LO's font rule for the top bar, stated precisely: **he LIKES the blackletter/ornate
`UnifrakturCook` (--display-brand) font on the corner brand wordmark ("AC PE$0")** and the
decorative hero splash — that's the "cool" look he wants to keep. What he flagged as
unreadable was the **synth nav BUTTONS** (`.site-nav > a`), which an earlier upgrade had
accidentally set to the same blackletter font + uppercase + tight letter-spacing + a blurry
red text-glow. On phone and desktop those buttons were illegible.

So: keep `--display-brand` on `.wordmark` and `.hero-line`; make sure the primary nav
buttons use a **readable sans** (e.g. `'Space Grotesk','Inter'`, weight 600, normal case,
no text-shadow blur) while keeping their cool synth-key visual (red gradient, neon border,
scanline sweep). When a user says "top buttons unreadable with this font change," inspect
BOTH the wordmark AND every `.site-nav`/`.nav-*` rule before assuming which one is at fault —
the wordmark and nav buttons can carry different fonts.