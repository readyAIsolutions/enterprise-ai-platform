---
name: crown-land-camping-fishing
description: Help users find Crown / public land in Canada to camp for FREE (dispersed/random camping, no campsite fee) and fish, with good eating fish and cool sights nearby. Covers the Canada-wide framework (free random camping vs. paid campgrounds, fishing-licence requirement, annual Free Fishing weekends), province-specific rules, and how to research it when the web tool hangs. Use when the user asks where to camp/fish for free on Crown land, public land, backcountry, or "without paying campsite fees" in Canada.
---

# Crown Land Camping & Fishing (Canada)

## When this skill applies
User wants to camp and/or fish on Crown / public land in Canada without paying campsite fees. They may name a province, or ask broadly. They care about: (a) FREE camping, (b) good-tasting fish, (c) cool sights. They are often on a budget and want dispersed/backcountry spots, not serviced campgrounds.

## The core mental model (true across Canada)
- **"Crown land" = public land.** Every province has it. Dispersed "random camping" on vacant Crown/public land is generally **FREE** — no campsite fee, no reservation. What costs money are *designated/serviced campgrounds* (provincial parks, PRAs, recreation areas) and, in some provinces, *pass zones* along the mountains.
- **Fishing is NOT free year-round.** Every province requires a fishing licence (and usually a WIN-style ID number). The practical way to fish without paying is during the province's annual **Free Fishing weekend(s)/days**. Other licence-free routes: children under a set age (accompanied), and Indigenous treaty rights. Always state the licence caveat honestly — do NOT claim year-round free fishing.
- **"No campsite fee" means dispersed camping on vacant Crown land**, not established campgrounds. Be explicit about this distinction or you'll mislead the user.

## Answer shape (steps)
1. **Pin the province.** Rules and free-fishing dates are per-province.
2. **Find the random-camping rule for that province:** Is dispersed camping free everywhere, or only outside a paid pass zone? (e.g. Alberta: free everywhere EXCEPT the Eastern Slopes pass zone + Porcupine Hills PLUZ + Willmore Wilderness — those need a Public Lands Camping Pass.)
3. **Get that province's Free Fishing dates for the target year** from the official source. Present them as the licence-free window.
4. **Recommend 3-5 concrete lakes/regions** on Crown land *outside* any paid/pass zone, each with: eating fish species + a nearby cool sight. Favor boreal/parkland belts (free Crown land is plentiful there) over mountain foothills (often pass-zoned).
5. **State the licence caveat + key rules** (pack out garbage, no services, don't camp on agricultural lease land without permission, check regs for slot limits/bait bans).

## Good-eating fish to name (by region)
- Boreal/northern lakes: **walleye (pickerel), northern pike, yellow perch, lake whitefish** — all easy shore/small-boat catches, good eating.
- Foothill/mountain lakes & streams: **rainbow, brook, cutthroat trout**.
- Rivers (e.g. North Saskatchewan, Athabasca): **goldeye, walleye**.

## PITFALLS
- **VERIFY COORDINATES AGAINST A REAL GEO SOURCE BEFORE EMITTING PINS.** This is the #1 failure mode. Do NOT trust memory for lat/long — in the 2026 session the agent gave Chip Lake Alberta coords ~29 km south of the real lake (53.39 vs actual 53.658) THREE times because it guessed from memory. The user screenshots Google Maps and WILL catch wrong pins. ALWAYS verify: `curl "https://nominatim.openstreetmap.org/search?q=<Lake>+<Province>&format=json&limit=5"` and read `lat`/`lon`/`boundingbox` from the JSON. Derive camp points OFF that real bbox. If the web/curl is blocked, say so and ask the user to confirm — never fire unverified decimals.
- **Use the no-snap Google Maps link format.** `https://www.google.com/maps/search/?api=1&query=LAT,LON` drops a clean pin at EXACT decimals. Do NOT use `google.com/maps/place/...` or bare `maps?q=` — Google snaps those to the nearest named feature and the viewport drifts, putting the pin on the wrong lake (seen live: pin landed 35 km west at the Pembina River).
- **User verifies coords himself.** Expect the user to open your pin and call out "this isn't on the lake." When that happens, re-pull from OSM — do not re-assert the wrong number. Precision (on-the-water, not "near") is a hard requirement for this user.
- **delegate_task web tool HANGS.** In this session, `delegate_task` with the `web` toolset hung/interrupted/timed out 3× on browse. Fall back to **terminal `curl` + Python HTML parsing** of authoritative provincial pages (see `references/research-technique.md`). Direct `.gov`/`.ca` page fetches worked reliably; Bing/Mojeek HTML scraping returned blocked/empty results.
- **Driving the user's PC to drop a pin (X11) — bridge is real, but verify.** When the user says "use my PC, you have perms," PROBE FIRST: same-LAN + `DISPLAY=:0.0` + `xdotool` present + window enumerable means you CAN reach their desktop. Working: enumerate windows (`xdotool search "."`), raise (`windowactivate`), screenshot (`scrot -u -o`), read pixels (Pillow `getpixel`) to prove click landed on map terrain, read URL (`ctrl+l`→`Ctrl+c`→`xclip`) to confirm coords. HARD WALL: Brave/Chrome **rejects synthetic `xdotool click`/`type` for map pin drops** — cursor moves onto the map (pixel-read proves it) but no pin registers and URL never flips. Never claim "pinned!" without URL/coord confirmation. Fallback: hand the verified no-snap link `https://www.google.com/maps/search/?api=1&query=LAT,LON` for the user's one real click, or drop a `.desktop`/script on their machine. Full technique + pixel-math in `references/x11-remote-pin-technique.md`.
- **Provincial URLs 404 constantly** (sites reorganize). If a slug 404s, try sibling slugs or the parent section — the content often still loads. Confirm key facts (free-fishing dates, pass rules) on the official site before presenting.
- **Don't conflate "free camping" with "free fishing."** Camping free ≠ fishing free. Lead with the Free Fishing dates.
- **Eastern Slopes / mountain foothills are usually pass-zoned** even where the rest of the province is free. Steer free-camping seekers to boreal/parkland Crown land unless they'll buy the pass.

## Reference files (this skill's knowledge bank)
- `references/alberta.md` — verified Alberta facts from the 2026 session (random-camping rules, Public Lands Camping Pass, Free Fishing July 6-8 2026, specific lake picks).
- `references/alberta-chip-lake.md` — VERIFIED Chip Lake coords (center 53.6583,-115.3811; north-shore Crown land camp points A/B/C; no-snap Maps link format). Use this, never memory, for Chip Lake pins.
- `references/research-technique.md` — the terminal-curl research fallback when the web/delegate tool is unavailable or hanging.
- `references/x11-remote-pin-technique.md` — driving the user's local PC via X11/xdotool to drop a Maps pin: working steps, pixel-math, and the Brave synthetic-input wall.

## Expansion
When the user asks about a new province (ON, MB, SK, BC, etc.), research it the same way and **add a `references/<province>.md`** with the verified rules + lake picks. Keep the Canada-wide framework in this SKILL.md; province specifics belong in references.
