# Live chatroom: /help command + "broken until refresh" = stale-cached HTML

## ⚠️ OVERLAY "BLURS PAGE BUT PULLS UP NOTHING" — REAL BUG (not always cache)
Owner reporting sounds/effect/edit-profile "blur the page but pull up nothing" was a
REAL root cause, not (only) stale cache. The global `static/style.css` defines
`.modal{display:none; position:fixed; inset:0}` as a generic full-screen mask
(reused elsewhere on the site). But chat.html's Pills/Sounds/Effect overlays name
their inner panel `class="modal"` too, so the global rule hides it / stretches it:
the overlay BACKDROP still shows (that's the blur) but the panel never draws.
FIX: chat.html's `.overlay .modal` rule must explicitly override the global:
  `.overlay .modal{display:block; position:relative; inset:auto; z-index:auto; ...}`
Higher specificity (`.overlay .modal`) beats `.modal`. Verify by clicking the pill
and checking `getComputedStyle(modal).display === "block"` AND the modal has a real
bounding rect (height > 50); add a static regression test that reads both CSS files.

Two techniques from the AC PE$0 nexus-style chatroom (`templates/chat.html`,
`api_chat_send` in server.py). UPGRADE #58 + #59.

## 1. A chat /help command = server returns a role-aware list, NEVER broadcasts

Owner ask: "community needs a /help command for all usable commands." The catch:
`/help` is an interactive menu for the SENDER, not a message to the room. If you
treat it like a normal command you'd save a `"/help"` message everyone sees and
the sender still doesn't get a usable list.

The clean pattern:
- In `api_chat_send`, BEFORE the normal command parsing, special-case the bare
  help tokens (`/help`, `/commands`, `/?`) and `return` a JSON payload instead
  of saving a message:
  ```python
  low = text.lower()
  if low in ("/help", "/help ", "/commands", "/?"):
      cmds = [
          {"cmd": "/me <action>", "desc": "Say a third-person action"},
          {"cmd": "/confess <message>", "desc": "Post an anonymous confession"},
      ]
      if is_admin:
          cmds = [
              {"cmd": "/announce <message>", "desc": "Admin: room announcement"},
              {"cmd": "/highlight <message>", "desc": "Admin: hot highlight"},
          ] + cmds
      cmds.append({"cmd": "/help", "desc": "Show this list"})
      return JSONResponse({"ok": True, "help": cmds, "is_admin": is_admin})
  ```
  Resolve `is_admin` BEFORE this check (it was previously computed inside the
  command branch) so you can legitimately use it for the role-aware list.
- Frontend `send()`: when the response has `j.help`, render it into a modal /
  panel and return WITHOUT clearing-plus-reloading the feed. Every other
  command still does the normal `loadMsgs(true)`.
- Build the help panel as a `.overlay` div (`#helpPanel`) so it reuses the site's
  existing fixed-overlay styling; populate `.innerHTML` from the returned list
  with `esc()` applied to both cmd and desc (they're attacker-typed input).
- Role-aware: admins see /announce + /highlight, normal fans don't. This also
  documents the actual command surface so users stop guessing.
- Register admin commands, /me, /confess even if they were written earlier — the
  /help list is the single source of what's usable.

Tests: fan /help returns /me, /confess, /help and CREATES NO message in the
channel feed; admin /help additionally lists /announce + /highlight.

## 2. "Chat UI broken until I refresh" = stale-cached personalized HTML (no-store)

Owner report: "tap to edit profile and nothing pops up, I have to refresh the
page to fix it." The profile modal click worked AFTER a refresh but not on the
FIRST visit.

Diagnostic reasoning (durable): if you can reproduce the page locally with the
real fan + admin identities and the interaction works with zero console errors,
then the CODE is fine — the difference between "first visit" and "after refresh"
is **which copy of the HTML the browser/proxy served**. First hit got a STALE
cached copy (older inline chat JS without the profile binding / with a broken
one); refresh pulled the current page.

The trap: all the chat UI JS ships INLINE inside the HTML page. A CDN/proxy
(Cloudflare) or browser that caches the HTML can serve an old page whose inline
JS predates the feature — so client-side features appear "dead until refresh."

Root cause concretely: the server's `_render()` returned every dynamic page with
NO cache headers, so nothing stopped a proxy/browser from caching personalized
HTML.

Fix (durable, do it at the `_render()` choke point so ALL pages inherit it):
```python
def _render(name, ctx):
    return HTMLResponse(jinja_env.get_template(name).render(ctx),
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                 "Pragma": "no-cache", "Expires": "0"})
```
- This applies to EVERY personalized page (fan/admin identity, gate state,
  download history) — they are never cacheable. Static CSS/JS keep their
  versioned `?v=` cache-busting, which is the right mechanism for those.
- Verify the header ships: `curl -sI <origin>/login | grep -i cache-control`
  → should show `no-store, ...`.
- The general lesson: any symptom of the form "X is broken but works after a
  refresh" on a site with inline JS + a CDN in front = suspect stale HTML first.
  Check cache headers, reproduce locally to clear the code, then add no-store to
  the page renderer.
