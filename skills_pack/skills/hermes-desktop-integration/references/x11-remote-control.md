# Driving the User's Local X11 Desktop from the Sandbox

When the user says "use my PC / you have perms," the bridge is often REAL, not hypothetical.
Verified working setup (2026 session, host = hunter's Xfce multi-monitor box, sandbox = Hermes runtime):

## Probe first (confirm the bridge exists)
- Same LAN: sandbox `ip route` shows `192.168.1.0/24`, host gateway `192.168.1.254`.
- `DISPLAY=:0.0` is exported in the sandbox env, host X server reachable.
- `which xdotool` on host returns a path (preinstalled on Xfce).
- Enumerate windows: `xdotool search "."` lists WIDs + names. If the user's browser
  window appears (e.g. `75497730 | Chip Lake - Google Maps - Brave`), you CAN drive it.

## Working sequence (this actually took input)
1. `xdotool windowfocus --sync $WID`  <-- CRITICAL: Brave/Chrome ignore synthetic events
   without a real focus first. This was the missing piece that made input register.
2. `xdotool windowactivate --sync $WID`
3. `sleep 1`
4. Click target UI: `xdotool mousemove --sync <x> <y>; xdotool click 1`
5. Text: `xdotool key --delay 50 "Ctrl+a"` -> `Delete` -> `xdotool type --delay 60 "..."`
   -> `xdotool key --delay 50 "Return"`

## Verify, never assert (user WILL screenshot to prove you wrong)
- Screenshot: `scrot -u -o /home/hunter/Desktop/shot.png` (install `sudo apt-get install -y scrot xclip` if missing; both installed clean in-session).
- Read pixels to prove a click landed right: Pillow `Image.getpixel((x,y))`.
  Map terrain = green ~(206,240,220); water = blue (b>r,b>g); sidebar = light cyan.
- Read app state: `xdotool key ctrl+l` -> `Ctrl+c` -> `xclip -selection clipboard -o`
  to pull a browser URL and confirm coordinates flipped.

## HARD WALL -- Brave/Chrome reject synthetic map-pin input
- `xdotool click` on map canvas MOVES cursor onto terrain (pixel-read proves it) but NO pin
  drops and URL never flips. Synthetic `type` into Maps search bar is also flaky.
- Why: browsers filter programmatic pointer/keyboard events for map interactions.
- Fallback when input won't take:
  (a) Hand user no-snap link `https://www.google.com/maps/search/?api=1&query=LAT,LON`
      for their ONE real click. (b) Write a `.desktop`/script on their machine opening
      those exact coords in Brave via double-click -- bypasses flaky in-tab typing.
- NEVER say "pinned!" without URL/coord confirmation.

## Google Maps coordinate hygiene (any pin task)
- VERIFY lat/long vs real geo source before emitting: `curl "https://nominatim.openstreetmap.org/search?q=<Lake>+<Province>&format=json&limit=5"` -> read `lat`/`lon`/`boundingbox`. Do NOT trust memory (agent gave Chip Lake coords ~29 km south of reality 3x from memory).
- Use `https://www.google.com/maps/search/?api=1&query=LAT,LON` (clean pin at exact decimals). Avoid `maps/place/...` or bare `maps?q=` (Google snaps to nearest named feature, viewport drifts to wrong lake).
- For on-water precision: derive camp points OFF real OSM bbox, then pixel-check the dropped pin sits on blue not terrain. Nudge east/south ~0.01 deg if off.
