# Casualties: Unknown — "Casualties Together" (KrokMP) co-op mod

Verified instance the skill was built on. Reusable as a concrete worked example.

## Game
- Name: "Casualties: Unknown" (installed as "Casualties: Unknown Demo"), Steam appid **4576510**.
- Engine: Unity/Mono — has `CasualtiesUnknown.exe`, `UnityPlayer.dll`, `MonoBleedingEdge/`, `CasualtiesUnknown_Data/`.
- Install path (Snap Steam): `~/snap/steam/common/.local/share/Steam/steamapps/common/Casualties Unknown Demo/`

## Mod
- Name: "Casualties Together" by Krokosha666 (KrokMP). Loader = BepInEx 5.4.23.5 win_x64.
- Download (login-gated, user must fetch): https://www.nexusmods.com/scavprototype/mods/67  (Files tab; latest KrokMP zip)
- Docs/source: https://github.com/creaturefeaturelarry/casualties-together  (built mod is Nexus-only; GitHub has no release assets)

## Install layout (what ends up in game root)
- `winhttp.dll` + `doorstop_config.ini`  <- BepInEx loader
- `BepInEx/core/`  <- loader runtime
- `BepInEx/plugins/KrokMP/`  <- KrokoshaCasualtiesMP.dll, LiteNetLib.dll, OpusSharp.Core.dll, Steamworks.NET.dll, opus.dll, steam_api64.dll, Multiupdater.dll
- `BepInEx/patchers/KrokMP/`  <- autoupdater_patcher.dll
- `steam_appid.txt` (=4576510)  <- from mod zip, must be at root

## Verified launch option (middle ultrawide DisplayPort-0, 2560x1080)
The inline `sh -c '...'` form is BROKEN in this setup: Snap Steam's `%command%` expands to a path containing a space ("Proton - Experimental"), which Steam wraps in single quotes that collide with the script's own single quotes — bash mis-parses and the game silently never launches (no error). Use the wrapper-script pattern instead.
1. Save `casualties_launch.sh` (from the skill's `templates/`) next to the game; edit `MONITOR`/`WIDTH`/`HEIGHT`; `chmod +x`.
2. Steam -> right-click game -> Properties -> Launch Options, paste:
   `/home/hunter/casualties_launch.sh %command% -screen-fullscreen 1 -screen-width 2560 -screen-height 1080`

## Caveats
- Demo build: mod loads (appid matches) but content is limited. Max 4 players recommended (poor optimization).
- Launch ONLY through Steam (Steam lobbies need it).
- To revert to singleplayer in-game: Settings > General > "Deactivate MP Mod".
- If MP button missing: check `<game>/BepInEx/LogOutput.log` (BepInEx 5 — NOT `BepInEx/logs/`); confirm launch option saved and game launched via Steam.
