# Newsletter / Email-Send Pitfalls (admin single-send & bulk-send)

Session-derived lessons for the AC PE$0 newsletter / curator email-send UI
(`/admin/newsletter-send` and the curator blast path). These bites apply to
ANY admin "send a message to subscribers" form.

## PITFALL: default-checked "Preview mode (dry run)" silently swallows real sends

Symptom (user report): "single sends for the newsletter don't seem to go
through, we tried sending one to hunter didn't come through yet."

Root cause: the admin newsletter form had **"Preview mode (dry run — no email
sent)" checked by default**. When an operator typed a single test address into
`Send to (to_override)` and clicked Send without unchecking it, the server took
the dry_run branch:

```python
if dry_run:
    queued += 1
    db.log_email("subscriber", email, subject, "queued", "dry_run")
    continue
```

So it logged `queued / dry_run` and **never emailed anyone** — no error, no
delivery, silent success. The operator believed it sent.

### How to diagnose (the fast path)
1. Read the DB email log, not the UI:
   `select * from email_log order by rowid desc limit 12;`
   A row with `status='queued'` and `error='dry_run'` means the message was
   deliberately NOT sent — it's the smoking gun.
2. Verify the backend actually works by sending ONE real test end-to-end
   through the live backend (Gmail-API / SMTP) to the recipient. `SEND OK`
   with no exception = the pipe is healthy, so the problem is UI/logic, not
   credentials.
3. Note the settings table (`settings` key/value, not `union`-style) holds the
   send config (smtp_*, gc_*, email_*). Watch that `$0`/spaces in the project
   dir (`~/Desktop/ac pe$0`) break naive shell `cd` — use single quotes or
   escape the `$`.

### The fix (frontend-only, no backend change)
When a single test address is typed into `Send to`, an inline script:
- auto-unchecks **and disables** the dry-run checkbox (operator cannot
  accidentally preview a single send),
- shows a red hint: "Single test address detected — this is a LIVE send
  (preview auto-disabled). It will really go out."
- leaves empty `Send to` defaulting to preview (checked) for bulk, where
  preview is the responsible safe default.

```html
<script>
(function () {
  var toIn = document.getElementById("nl-to-override");
  var dry = document.getElementById("nl-dry-run");
  var hint = document.getElementById("nl-single-hint");
  if (!toIn || !dry || !hint) return;
  function sync() {
    var isSingle = (toIn.value || "").trim().length > 0;
    if (isSingle) { dry.checked = false; dry.disabled = true; hint.style.display = "block"; }
    else { dry.checked = true; dry.disabled = false; hint.style.display = "none"; }
  }
  toIn.addEventListener("input", sync); toIn.addEventListener("change", sync); sync();
})();
</script>
```

## General rule for send/publish UIs
Destructive/side-effecting actions (actually emailing N people, publishing,
sending DMs) should default to a SAFE state and make the LIVE state explicit
and un-mis-toggable for the small/single case. A silent "queued" that never
delivers is worse than a loud error. If a form has a dry-run/preview default,
make the live path visually distinct and (for the one-off test case) force it.

## Send backend precedence (curator.py send_email)
- Prefers Gmail-API (Google Cloud OAuth) when `gc_client_id/secret/refresh_token`
  present (`gmail_enabled`).
- Else falls back to SMTP (smtp_*); authenticated SMTP needs BOTH user+password.
- Append the `email_signature` setting to every outgoing message.
- After a config edit, confirm `curator.sender_enabled(settings)` is True and
  do a real one-off send to prove it before trusting the UI.
