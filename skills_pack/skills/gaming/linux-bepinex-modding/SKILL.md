---
name: linux-bepinex-modding
description: Install, enable, and troubleshoot BepInEx-based Unity game mods (co-op/multiplayer injectors like KrokMP/"Casualties Together", and any BepInEx plugin) on Linux Steam/Proton. Covers the loader install, the critical WINEDLLOVERRIDES launch option, Snap Steam paths, Nexus login-gating, and researching install steps when sources block scraping.
---

# When to use this skill
- User wants to install/enable/fix a mod for a Steam game on Linux, especially a Unity game.
- Mentions "multiplayer mod", "co-op mod", "BepInEx", "KrokMP", a mod that "doesn't come with MP", or a game whose MP buttons never appear.
- Game is launched via Steam/Proton (including Snap-installed Steam) and mods silently fail to load.

# How BepInEx modding works on Linux/Proton (mental model)
BepInEx is a Unity mod loader. For Unity *Mono* games you use the **win_x64 5.4.x** build. It works by dropping `winhttp.dll` (the "doorstop" chainloader) into the game root; the game's normal `winhttp.dll` call is intercepted and redirected to BepInEx's preloader, which then loads plugins from `BepInEx/plugins/`.

On Windows this just works. On Linux/Steam-Proton it does NOT auto-load — Wine must be told to prefer the shipped `winhttp.dll` over the built-in one. That is the single most common reason mods "do nothing" on Linux, and most Windows-centric guides omit it.

# Install procedure (general)
1. **Identify the game + appid.** Steam appid is in the store URL or the desktop shortcut (`Exec=steam steam://rungameid/<id>`). Confirm the installed build (Demo vs full) — a mod built for the full game may still load on a same-appid Demo, but content can be limited.
2. **Locate the install dir** (see Paths below). Browse local files via Steam: Manage > Browse local files.
3. **Download BepInEx 5.4.23.5 win_x64** (public GitHub release — agent CAN fetch this):
   `https://github.com/BepInEx/BepInEx/releases/download/v5.4.23.5/BepInEx_win_x64_5.4.23.5.zip`
   Unzip and copy `BepInEx/`, `winhttp.dll`, `doorstop_config.ini`, `changelog.txt` into the game root. Verify `doorstop_config.ini` has `enabled = true` and `target_assembly=BepInEx\core\BepInEx.Preloader.dll`.
4. **Get the mod itself.** Many co-op mods (e.g. KrokMP) are hosted on **Nexus Mods, which requires a login and is NOT fetchable by the agent** (returns 403). Tell the user to download it, drop the zip at `~/Downloads/`, and you extract + merge it. The usual shape: unzip, open the inner `mod` folder, move its contents into the game root (the mod's own `BepInEx/plugins/...` merges with the loader you installed).
5. **CRITICAL — set the Linux launch option** (see below). Without it BepInEx never loads.
6. **Launch via Steam** (not by double-clicking the .exe). Steam-lobby mods need Steam running.
7. **Verify.** Multiplayer/menu buttons should appear. If not, read `BepInEx/logs/` for loader/plugin errors.

# The Linux-critical launch option
In Steam: right-click game > Properties > Launch Options, paste exactly:
```
WINEDLLOVERRIDES="winhttp=n,b" %command%
```
- `n,b` = native (our dll) then builtin; `winhttp` = the doorstop dll name.
- Set it via the GUI. Do NOT hand-edit `localconfig.vdf` while Steam is running — Steam overwrites it on exit, and the inner quotes are fiddly in VDF text. (If Steam is fully closed you may patch `userdata/<id>/config/localconfig.vdf`, but GUI is safer.)

# Locating the game (paths)
- Normal Steam: `~/.local/share/Steam/steamapps/common/<Game>/` (or `~/.steam/steam/steamapps/common/`).
- **Snap Steam** (common on Ubuntu): `~/snap/steam/common/.local/share/Steam/steamapps/common/<Game>/`. The `appmanifest_<appid>.acf` lives in `.../steamapps/` and lists `installdir`. User config (launch options) is at `~/snap/steam/common/.local/share/Steam/userdata/<steamid>/config/localconfig.vdf`.
- Find the game dir quickly:
  `find ~/snap/steam ~/.local/share/Steam -maxdepth 4 -iname "appmanifest_<appid>.acf"`

# Pitfalls
- Forgetting the launch option = silent no-op. Always set it on Linux.
- Wrong BepInEx flavor: use **win_x64** 5.4.x for Unity *Mono* (has `MonoBleedingEdge/` in game dir). IL2CPP games need a different BepInEx build — check the game's `GameAssembly.dll` / `UnityPlayer.dll` presence; if unsure, inspect the game folder.
- Nexus login-gating: never promise to auto-download a Nexus mod file; have the user supply it.
- Demo vs full: appid match is the real test, but limited demo content can make MP seem broken.
- Rolling back: delete `BepInEx/`, `winhttp.dll`, `doorstop_config.ini` (and merged mod files) and clear the launch option.
- Don't edit `localconfig.vdf` while Steam runs.

# Researching install steps when sources block scraping
Mod install guides live on GitHub (readable), Nexus (403 to bots), and Steam Discussions (JS-rendered, won't scrape). A reliable fallback when `x_search` is unavailable/creditless and `html.duckduckgo.com/html/` returns nothing:
- Use `https://lite.duckduckgo.com/lite/` with an HTTP POST of `q=<urlencoded query>` and a desktop User-Agent. This returned usable result links when the plain HTML endpoint was empty.
- Fetch the mod's GitHub README via raw: `https://raw.githubusercontent.com/<owner>/<repo>/<branch>/README.md` (try `main` then `master`).
- For the co-op mod's exact download, link the user to Nexus rather than trying to scrape it.

# Verification & rollback
- After launch, check `<game root>/BepInEx/logs/` for `BepInEx` preloader output and any plugin errors.
- Menu should show mod-added buttons (e.g. multiplayer). If absent, re-check launch option + that mod files landed in `BepInEx/plugins/`.
- Deactivate (not uninstall) via the mod's in-game setting when you want singleplayer back.

# References
- `references/casualties-unknown.md` — the specific Casualties: Unknown / "Casualties Together" (KrokMP) case worked in-session: appid, paths, and what was already installed.
