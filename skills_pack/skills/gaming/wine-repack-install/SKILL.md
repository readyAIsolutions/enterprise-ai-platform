---
name: wine-repack-install
description: Install repacked Windows games/apps (FitGirl, KaOs, CODEX, DODI) on Linux via Wine. Covers the unpack failure modes (ISDone/FreeArc/srep/lollypop decompression stall, wine32 missing, hardcoded E drive temp path hitting a dead USB), the safe way to fix the wine E drive without clobbering dosdevices, and the Linux archive-GUI equivalent (Engrampa plus rar/unrar) for the install-WinRAR class of ask. Use when LO says install a repack/game from Downloads or binks brew, or wants Engrampa/WinRAR on Linux.
---

# wine-repack-install

Installing repacked Windows games/apps on Linux is 90% fighting the unpacker, not the game. This skill is the battle-tested path from a pile of .rar/.bin/.exe repack files to a launchable .desktop shortcut.

> **PRIMARY METHOD on this box: use Proton, not vanilla Wine.** Wine 10's wow64 mode stalls the ISDone/FreeArc unpack thread (0-byte inner.fgpack). Steam's Proton unpacks both FitGirl and KaOs repacks cleanly. See sibling skill `linux-repack-wine-install` for the Proton-first recipe, wrapper-script pattern, .desktop trust fix, and all pitfalls. This skill covers the Wine fallback, archive-GUI setup, and Luban/HueForge desktop integration.

## Trigger
- LO says "install <game> from binks brew / Downloads", names a FitGirl/KaOs/CODEX/DODI repack, or "unpack part1-5".
- LO says "install WinRAR / use Engrampa / make archives work on Linux".
- Any task where a Windows setup.exe / Install.exe must run under Wine to produce game files.

## Phase 0 — the archive itself (before Wine)
Repacks ship as multi-part RARs or as setup.exe + fg-*.bin / *.bin next to it.
- Multi-part RAR: `rar x -o+ kas-XXX.part1.rar <outdir>` (use the rar/unrar CLI, NOT `unrar x` for creating; `unrar x` for extracting). Verified: rar 7.23 + unrar-nonfree 7.2.4 both work. `innoextract` FAILS on KaOs/FitGirl installers — their Inno Setup header is obfuscated ("Stream error while parsing setup headers"). Don't waste time on it.
- After extract you get Install.exe/setup.exe + a big .bin (e.g. KaOs-01.bin 21GB, fg-01.bin etc). The .bin is the payload; the .exe is the Inno Setup wrapper that knows how to decode it.

## Phase 1 — Linux archive GUI equivalent ("install WinRAR")
There is NO WinRAR GUI for Linux (Windows-only, no Linux build). The right Linux equivalent:
- `engrampa` (MATE Archive Manager) — registered for application/x-rar, opens .rar/.zip/.7z/.tar. It is the WinRAR-like GUI. Put a .desktop for it on the desktop.
- Backend packages so the GUI can READ/WRITE RAR: `sudo apt-get install -y unrar p7zip-full` (unrar = nonfree 7.2.4, full RAR5 read). Without `unrar` the GUI silently can't open .rar.
- CLI: install rar/unrar tarball to /usr/local/bin for creating RARs.
- Verify: `engrampa <file>.rar` launches clean (headless: timeout 4, exit 124 = stayed open = good).

## Phase 2 — Wine base install
- `sudo apt-get install -y wine` pulls wine64 but on Ubuntu 26.04 does NOT pull the 32-bit runner. Repack installers are 32-bit PE (i386) and their decompression HELPERS (cls-lollypop_x86.exe, srep, etc.) need it.
  - FIX: `sudo apt-get install -y wine32` (also pulls libwine:i386). Without it, 32-bit helper exes die silently and unpack stalls at 0 bytes.
- `winetricks` is NOT preinstalled. Fetch it: `curl -sL -o /tmp/winetricks https://raw.githubusercontent.com/Winetricks/winetricks/master/src/winetricks && chmod +x /tmp/winetricks`. It needs `wineserver` on PATH: `export PATH=/usr/lib/x86_64-linux-gnu/wine:/usr/bin:$PATH`. Prereqs many repacks want: `winetricks -q d3dx9 vcrun2010` (needs `cabextract` installed first: `sudo apt-get install -y cabextract`).
- exe type check: `file Install.exe` -> "PE32 executable ... Intel i386" = 32-bit Inno Setup.

## Phase 3 — THE UNPACK FAILURE (the real fight)
Symptom: installer launches, reaches "Please wait while Setup installs...", then either (a) exits code 3 in /VERYSILENT mode, or (b) stalls forever with inner.fgpack at 0 bytes and only _Redist/ + unins000.* written.

Root causes, in order of likelihood:

1. Hardcoded E drive temp/output path in the repack's CLS.ini. FitGirl/KaOs installers decompress via ISDone.dll -> srep/precomp/lollypop/magic2 codecs whose TempPath is hardcoded to E:\<Game> (confirmed: CLS.ini shows [Srep] TempPath=E:\Superliminal, [magic2l] ldmfTempPath=E:\Superliminal). On LO's box wine E: = /run/media/hunter/DEMIURGE (flaky exfat USB, often unmounted) -> helper writes temp to a dead drive -> thread dies -> 0-byte fgpack.
   - SAFE FIX (do NOT `rm` the dosdevices symlink blindly — LO blocked that; it can clobber his USB mapping):
     - Preferred: ensure the USB is mounted (`mount | grep DEMIURGE`) so E: is live, OR
     - Create a SEPARATE wine prefix for games: `export WINEPREFIX=/home/hunter/.wine-games` and set its E: cleanly, leaving main .wine untouched, OR
     - Symlink E: to a real local dir ONLY after confirming the target — `ln -s /home/hunter/Games /home/hunter/.wine/dosdevices/e:` — and tell LO you did it so he can revert.
   - When E: resolves to a live writable folder, the installer progresses to the shortcut stage (proof: `menubuilder:InvokeShellLinker failed to extract icon from L"E:\<Game>\<Game>GOG.exe"` = it got that far; the icon error is harmless).

2. ISDone/FreeArc decompression thread won't schedule under Wine 10's wow64 mode. Even with E: live + wine32 installed + all DLLs loading (confirmed via `WINEDEBUG=+loaddll` — zero "module not found"), the srep/lollypop chain can still stall. This is environmental. Workarounds that actually help:
   - Run the installer INTERACTIVELY (no /VERYSILENT), with a real X display (DISPLAY=:0, X0 socket present on LO's box). The unpack thread gets scheduled when there's a live message pump; /VERYSILENT headless often deadlocks it. LO can see/click the window and hear the FitGirl music during unpack.
   - Prefer Proton (Steam's Wine fork) over vanilla Wine — Proton's ISDone handling is far better for repacks. Steam is installed on LO's box; use `proton run setup.exe` from a Steam compat prefix.
   - Try native FreeArc (`fa`) to unpack the .bin directly, bypassing the installer: install freearc if available, point it at fg-*.bin with the repack's arc.ini. The codec helpers are Windows but freearc-linux sometimes reads the stream.

3. Multiple overlapping installer instances lock each other's .bin and deadlock. Always `pkill -9 -f "setup.tmp"` / `pkill -9 -f "extracted/Install.exe"` and run ONE game at a time. (Note: `pkill ... ; sleep` in one line can self-kill the shell with -15; run the verify as a separate command.)

## Phase 4 — run + monitor
- Launch with `terminal(background=true)` + `notify_on_complete=true`. The harness BLOCKS `&`, `nohup`, `setsid`, `disown` in foreground commands — use background=true, never shell backgrounding.
- Poll for the game exe: `find /home/hunter/Games -iname "*.exe" | grep -viE "redist|unins|vc_redist|QuickSFV|dxweb"`. The real exe is often <Game>GOG.exe (Superliminal -> SuperliminalGOG.exe).
- Verify unpack completed: dir size grows past the ~31MB redist stub; inner.fgpack should DISAPPEAR (converted to real files) or the game folder should contain the game's own subdirs.

## Phase 5 — desktop shortcuts (LO wants these on ~/Desktop)
CRITICAL: do NOT put an inline env VAR=... proton run game.exe Exec in the .desktop.
When xfce launches a .desktop it does NOT reliably pass inline env vars, so Proton can't
find its Steam client path and the game silently never starts. Two bugs bit in a live session:
  (a) The .desktop needs metadata::trusted=true or xfce opens it in a text editor / does
      nothing on double-click. After writing ANY Desktop .desktop:
      gio set "/home/hunter/Desktop/<Name>.desktop" "metadata::trusted" true
      Verify: gio info -a "metadata::trusted" <file> -> metadata::trusted: true.
  (b) A SPACE in the .desktop filename breaks gtk-launch ("no such application"). Name it
      Jackbox.desktop, NOT "Jackbox Party Pack.desktop". The icon label stays "Jackbox Party
      Pack" via the Name= field (independent of filename).

The reliable pattern — point Exec at a wrapper script that sets the env itself:
Write /home/hunter/Games/launch_<game>.sh:
  #!/bin/bash
  export STEAM_COMPAT_CLIENT_INSTALL_PATH="/home/hunter/snap/steam/common/.local/share/Steam"
  export STEAM_COMPAT_DATA_PATH="/home/hunter/Games/proton-<game>"
  export WINEPREFIX="/home/hunter/Games/proton-<game>/pfx"
  export DISPLAY="${DISPLAY:-:0}"
  if [ -z "$XAUTHORITY" ]; then
    for p in /run/user/1000/gdm/Xauthority /run/user/1000/.Xauthority /home/hunter/.Xauthority; do
      [ -f "$p" ] && export XAUTHORITY=*** && break
    done
  fi
  export PROTON_NO_XALIA="1"
  PROTON="/home/hunter/snap/steam/common/.local/share/Steam/steamapps/common/Proton - Experimental/proton"
  cd /home/hunter/Games/<Game>
  exec python3 "$PROTON" run "/home/hunter/Games/<Game>/<Game>exe"
Then the .desktop:
  [Desktop Entry]
  Name=<Game> Party Pack
  Comment=<Game> (Repack) - Proton/Wine
  Exec=/home/hunter/Games/launch_<game>.sh
  Icon=applications-games
  Terminal=false
  Type=Application
  Categories=Game;
  StartupNotify=true
chmod +x BOTH the script and the .desktop, set metadata::trusted, then
update-desktop-database /home/hunter/.local/share/applications.
Test the click path with: gtk-launch /home/hunter/Desktop/<game>.desktop (background=true)
and confirm the game process + a real steam_proton X window appear.

- Luban/HueForge already have .desktop in ~/Desktop/apps/ — just cp + chmod to ~/Desktop/.
- Luban MU full-version quirk: binary expects MU_License.dat in its working dir; the provided file is named MU_EG_VTO.dat. Copy it: cp MU_EG_VTO.dat MU_License.dat next to the binary. See references/luban-mu-license.md.
- Luban also needs libtbb.so.2 (Ubuntu 26.04 renamed it to libtbb12). Fetch the jammy deb: `curl -sL -o /tmp/libtbb2.deb "https://launchpad.net/ubuntu/+archive/primary/+files/libtbb2_2020.3-1ubuntu3_amd64.deb"` then `dpkg-deb -x` and `cp usr/lib/x86_64-linux-gnu/libtbb.so.2 /usr/local/lib/ && ldconfig`.

## Pitfalls (embedded from this session)
- NEVER `rm` a wine dosdevices/<drive> symlink without LO's OK — it can clobber his external-USB drive mapping. Offer mount-USB / separate-prefix / tell-him-first instead.
- `wine` alone != 32-bit capable on Ubuntu 26.04. Always `apt-get install -y wine32` for repacks.
- `innoextract` is useless on KaOs/FitGirl (obfuscated Inno header). Don't loop on it.
- Headless /VERYSILENT often deadlocks the unpack thread — use interactive + real display.
- Harness blocks shell backgrounding (`&`/`nohup`/`setsid`/`disown`) — use `terminal(background=true)`.
- `pkill` + `sleep` in one foreground command can self-terminate (-15); split the verify into a second call.
- Desktop .desktop launchers for the game MUST (1) set `metadata::trusted=true` via gio or
  xfce won't run them, and (2) have NO SPACE in the filename or `gtk-launch` fails. Point
  Exec at a wrapper script (not inline env) so Proton gets its env vars. See Phase 5.
- SIDE EFFECT: running the game under Proton/Steam can leave `GAMESCOPE_*` properties on the
  X root window and may KILL xfwm4's compositor (`_NET_WM_CM_S0` unowned -> black windows,
  no background). xfwm4 restarts alone do NOT recover it; a session restart is the reliable
  fix. Capture detail + recovery in skill `xfce-desktop-icon-persistence` (compositor PITFALL).
  Prefer launching via a wrapper that doesn't leave Steam's display layer hooked, or warn LO
  a session restart may be needed after a gaming session.

## References
- `references/repack-unpack-diagnostic.md` — the full CLS.ini/arc.ini/error-transcript evidence chain from the Superliminal/KaOs session.
- `references/luban-mu-license.md` — Luban MU full-version license rename fix + libtbb2 recovery.
- `references/linux-archive-gui.md` — Engrampa + unrar + rar CLI setup for the install-WinRAR-on-Linux ask.
