# Follow gate step — user-scoped verification pattern

Adding a "follow the artist on SoundCloud" gate requirement is NOT a drop-in
clone of the like/repost/comment steps, because follow is a **USER-scoped**
action (fan → owner account) while like/comment/repost are **TRACK-scoped**
(fan → a specific track id). The dormant scaffold already in the codebase
looked like it worked but was silently broken. Below is what actually needs to
happen, learned the hard way (UPGRADE #55).

## Core conceptual split
- like / repost / comment: verify against `track_id`. `verify_step(step, token,
  track_id, ...)` makes sense.
- follow: verify against the OWNER's numeric SC user id, NOT a track id. It is
  "does fan X follow user Y", where Y = the acpeso owner.

## Steps to wire follow correctly (with real API verification)

1. **Real live check in soundcloud.py** — the stock `verify_step("follow")`
   returned `(step, str(track_id)) in recorded` (the mock-only registry), so in
   LIVE mode it ALWAYS returned False and the step could never pass. Add a real
   `user_follows(token, target_user_id)`:
   - LIVE: `_api_get(f"/me/followings/{quote(target)}", token)` — a 200 means
     following, a `{'error': True, 'status': 404}` dict means NOT following.
   - MOCK: check `("follow", str(target)) in _MOCK_DONE.get(token, set())`.
   - Guard: reject empty/`"0"`/`"None"` targets up front (return False) so a
     missing owner uid never accidentally passes.

2. **Fix `verify_step` for follow** — both the mock branch AND the live branch
   must key on `kw.get("owner_uid")`, not `track_id`. Live:
   ```python
   if step == "follow":
       return user_follows(token, kw.get("owner_uid") or "")
   ```

3. **Resolve the owner uid** in server.py — `_owner_sc_uid()`: prefer the saved
   `admin_sc_user_id` setting, else resolve live via `sc.me(owner_token)["id"]`.
   CRITICAL: persist `admin_sc_user_id`/`admin_sc_username`/`admin_sc_email` at
   admin connect time (in the OAuth callback when `_is_admin_fan(fan)`), else the
   setting is empty and every follow lookup does a live /me call.

4. **Serve a fast one-click follow** mirroring the fast-repost flow:
   `POST /api/follow` with the fan's own token, `sc.follow_user(token, owner_uid)`;
   a 2xx (or "already following") is instant proof. Return a clean
   `owner_unknown` error when `_owner_sc_uid()` is empty so the UI can tell the
   fan "owner not configured" instead of a silent generic failure. Register it
   next to `/api/repost`.

5. **Pass owner_uid through every verify call site** — unlock handler AND
   `gate_live_recheck` must forward `owner_uid=_owner_sc_uid()` when the step is
   follow, else live re-check silently keys on track_id and mis-verifies.

6. **Toggle + template + frontend**
   - Add a "Follow" checkbox to `gate_requires` in BOTH admin release forms
     (edit + create) — the two forms drift if you only patch one.
   - gate.html: follow step gets its own `step-follow-fast` button and its
     "Open SoundCloud" should open the OWNER profile (`data-open-url`), not the
     track — set a per-step `data-open-url` and have app.js use it.
   - app.js: grab `data-follow-action`, handle `owner_unknown` + expired-token
     branches like the repost handler.

## Add follow to live recheck
A fan who UNFOLLOWS after completing should re-lock the gate, same as
unlike/delete-comment. Add `"follow"` to the `live_checkable` whitelist in
`gate_live_recheck` and forward owner_uid in that loop.

## TEST PITFALL — module-level mock state leaks across tests
`soundcloud._MOCK_DONE` and `_MOCK_BUY_LINKS` are module-level dicts that PERSIST
between tests in the same process. A previous test recording `("follow","7777777")`
leaks into a later test's `verify_step` and makes it pass when it should fail.
ALWAYS `sc._MOCK_DONE.clear()` at the start of any follow/verify test that
asserts a negative ("not followed yet → False").
Also: in MOCK mode `/unlock/{sid}/{step}` performs the action AND verifies it in
one call, so you CANNOT write "unlock fails before doing the step" assertions
against the route in mock — assert on `sc.verify_step(...)` directly instead.

## Verification
- 3 tests: instant follow marks step + records against the real owner uid;
  bad sid → 404; follow step renders with owner profile URL and
  `verify_step("follow")` is keyed to owner uid (following a DIFFERENT user
  does NOT satisfy it).
- Bump CSS/JS cache-bust versions in base.html when templates/app.js change.
- Restart the systemd user unit, confirm `systemctl --user is-active` + new
  cache versions return 200.
