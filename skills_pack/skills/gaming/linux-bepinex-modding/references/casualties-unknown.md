# Casualties: Unknown — "Casualties Together" (KrokMP) multiplayer mod

Worked case, 2026-07-08. User on Linux (Snap Steam), 3-monitor desktop.

## What the game/mod is
- Game: "Casualties: Unknown" (installed as the **Demo**, Steam **appid 4576510**).
  - Unity/Mono game: `CasualtiesUnknown.exe` + `UnityPlayer.dll` + `MonoBleedingEdge/` in game root.
  - Desktop shortcut: `~/.local/share/applications/Casualties Unknown Demo.desktop` -> `steam steam://rungameid/4576510`.
- Multiplayer is NOT built in. Mod = "Casualties Together" by creaturefeaturelarry (repo `creaturefeaturelarry/casualties-together`).
- The co-op payload is **KrokMP**, distributed on Nexus (login-gated): `https://www.nexusmods.com/scavprototype/mods/67` (Files tab). No GitHub mirror of the built mod.
- Loader: BepInEx 5.4.23.5 win_x64.

## Install state at end of session
- BepInEx loader ALREADY installed into game root (by the agent):
  `/home/hunter/snap/steam/common/.local/share/Steam/steamapps/common/Casualties Unknown Demo/`
  Contains `BepInEx/`, `winhttp.dll`, `doorstop_config.ini` (enabled=true).
- KrokMP NOT yet installed — requires the user to download from Nexus and drop `~/Downloads/KrokMP.zip`; agent then extracts and merges the inner `mod/` folder contents into the game root.
- Launch option NOT yet set (Steam was running, so GUI step deferred to user): `WINEDLLOVERRIDES="winhttp=n,b" %command%` in Properties > Launch Options.

## Exact commands that worked
- Find game dir:
  `find ~/snap/steam -maxdepth 4 -iname "appmanifest_4576510.acf"`
- BepInEx fetch + lay-down (agent-run):
  `curl -sL -o /tmp/bepinex.zip https://github.com/BepInEx/BepInEx/releases/download/v5.4.23.5/BepInEx_win_x64_5.4.23.5.zip`
  then `unzip` (or `python3 -c "import zipfile;zipfile.ZipFile('bepinex.zip').extractall('bepx')"`) and `cp -r BepInEx winhttp.dll doorstop_config.ini changelog.txt <game root>/`.

## Caveats
- Demo build: appid matches the mod's target (README points at store/app/4576510), so it should load; demo content is limited.
- Must launch via Steam (Steam lobbies). Max ~4 players recommended.
- In-game "Deactivate MP Mod" (Settings > General) returns to singleplayer without uninstalling.
- If no MP buttons: check `BepInEx/logs/`; most likely the launch option wasn't applied or KrokMP files aren't in `BepInEx/plugins/`.
