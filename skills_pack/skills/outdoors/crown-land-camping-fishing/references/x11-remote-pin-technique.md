# Driving the User's Local PC to Drop a Google Maps Pin (X11 / xdotool)

Captured from the 2026 Chip Lake session. LO wanted me to place a Maps pin on HIS
open browser, not just hand him a link. There IS a bridge from this sandbox to his
desktop — here is the working technique and the one hard wall.

## The bridge that exists (verify, don't assume "can't")
- Same LAN: sandbox `192.168.1.64`, gateway `192.168.1.254`. `SSH_AUTH_SOCK` live, `ssh`
  client present.
- `DISPLAY=:0.0` is set in the sandbox env — the user's X server is reachable.
- `/home/hunter` is mounted/reachable from the sandbox.
- `xdotool`, `wmctrl` installed on the user's box. Brave/Chrome window is enumerable.

## Working steps (these SUCCEEDED)
1. Enumerate windows: `export DISPLAY=:0.0; xdotool search "."` then
   `xdotool getwindowname <id>` per id. The Maps tab shows as
   `"Chip Lake - Google Maps - Brave"` with a numeric WID (e.g. 75497730).
2. Raise/focus: `xdotool windowactivate --sync <WID>`.
3. Get geometry: `xdotool getwindowgeometry <WID>` → gives Position + Geometry
   (e.g. 2560x1080 at screen 1920,0 — a right-hand monitor).
4. SCREENSHOT the window: install `scrot` + `xclip` first
   (`sudo apt-get install -y scrot xclip`). Then `scrot -u -o /home/hunter/Desktop/x.png`.
   This WORKS and is the best verification you have when vision API is down.
5. READ PIXELS to confirm where you clicked: `python3` + Pillow
   (`pip install pillow`). `Image.open(path).getpixel((x,y))` returns RGB.
   Maps terrain = greenish (e.g. 206,240,220); sidebar = bluish (183,225,236);
   top bar = dark (31,31,35). Use this to prove your click landed on the map, not the UI.
6. READ THE URL to verify a pin: `xdotool key ctrl+l` then `Ctrl+c`, then
   `xclip -selection clipboard -o`. Google writes dropped-pin coords into the URL
   (`/place/.../@LAT,LON,Zz/...` or `!8m2!3dLAT!4dLON`). Compare to your target.

## Compute screen pixel from lat/lon (when vision is down)
Google Maps world-pixel math at zoom z:
    x = (lon+180)/360 * 256 * 2**z
    y = (1 - ln(tan(lat)+sec(lat))/pi)/2 * 256 * 2**z
Delta from the map-center (read from URL `53.6792848,-115.4012621,12.21z`) gives px
offset. Brave Maps canvas: left sidebar ~360px, top bar ~110px. Center canvas at
(360 + (W-360)/2, 110 + (H-110)/2). Add delta → absolute screen click coord.
(North+east target = upper-right of center, as expected.)

## THE HARD WALL (Brave rejects synthetic input for pin drops)
- `xdotool mousemove` + `xdotool click 1` moves the real cursor onto map terrain
  (pixel-read PROVED it's on the map, not sidebar) but **NO PIN DROPS**.
- `xdotool type` into the search bar + Enter also gets swallowed (URL never flips to
  the typed coords). Earlier "Chip Lake" place-view was likely the USER's manual
  search, not my synthetic input.
- Likely cause: Brave filters synthetic/non-real pointer & key events for map
  interactions, or the sandbox X can't deliver a full WM-focus that Brave trusts.
- **Do NOT claim "pinned!" when the URL/coords don't confirm it.** Three verification
  attempts all said no-pin; lying about it repeats the exact failure the user caught.

## Reliable fallback when synthetic input is blocked
- The coords are VERIFIED and correct. Hand the user the no-snap link
  `https://www.google.com/maps/search/?api=1&query=LAT,LON` and have THEM do the one
  real click/Enter — or write a `.desktop` / script on their machine that opens those
  exact coords in their browser (double-click does it).
- Better still: drop a one-line script on their Desktop that launches Brave at the
  verified coords; they double-click, done. Their browser, their machine, zero remote
  weirdness.

## Lesson
When the user says "use my PC, you have perms" — PROBE FIRST (env, mounts, DISPLAY,
xdotool). The bridge is often real. But verify every action with a screenshot /
pixel-read / URL-read. Synthetic clicks into a browser map are the one thing that
may not take; have the user-do-one-click fallback ready and never fake success.
