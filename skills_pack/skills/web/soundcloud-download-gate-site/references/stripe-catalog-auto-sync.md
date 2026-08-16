# Stripe Product-Catalog Auto-Sync (immutable Prices)

Reusable pattern for keeping a Stripe catalog in sync with site-managed sellable
items (beatpacks, merch, tickets, subscriptions) whenever prices change on the
site side. Upgrade #54 on the AC PE$0 site.

## The core fact
Stripe Prices are IMMUTABLE. You can never do `Price.modify(amount=...)`.
A price change = create a NEW Price at the new amount, archive the old one,
and repoint the Product's `default_price`.

## The idempotent, price-aware helper
Instead of a manual "sync now" button being the only path, run this on EVERY
save of a sellable item (create + edit), wrapped in try/except so a Stripe or
network outage NEVER blocks the admin save:

1. If no `stripe_product_id` stored yet (or product missing), create the Product
   (name/description/image). Persist the id.
2. Reuse the stored `stripe_product_id` if present instead of re-creating.
3. List the product's prices. If an active Price with
   `unit_amount == current_site_cents` already exists, reuse it. Idempotent —
   no duplicate Price spawned on unchanged saves.
4. If none matches (new item, or site price CHANGED): create a NEW one-time
   Price at the current amount, ARCHIVE the older active price(s), set
   `default_price` to the new one.
5. Persist `stripe_price_id` (and product id) back onto the item row.

Checkout uses the stored `stripe_price_id`, so the updated price flows straight
into Stripe Checkout.

## Why this shape
- **Automatic over manual**: price change on the site propagates without anyone
  remembering to hit a sync button. A bulk "re-sync all" button remains for
  backfill and stays consistent (reuse the same helper).
- **Idempotent**: re-saving an unchanged item is a no-op against Stripe.
- **Never blocks the writer**: the try/except guarantees a Stripe outage can't
  prevent saving the item on our side (that row is source-of-truth for price).
- Stripe Product/Price ids are stored per-item so we don't create duplicate
  Products and checkout always points at the right live Price.

## Test technique
Unit-test with a FAKE Stripe object (no network): assert (a) product + price
created at the site amount, (b) unchanged price is idempotent (no new Price),
(c) a site price change spawns a new Price at the new amount and archives the
old one.
