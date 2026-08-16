---
name: linux-repack-wine-install
description: Install Windows game repacks (KaOs, FitGirl, and any Inno-Setup or .bin repack) on Linux. PRIMARY fix is to run the installer under Steam's Proton (snap-installed on LO's box) because vanilla Wine 10 stalls the ISDone/FreeArc unpack thread (inner.fgpack stays 0 bytes, KaOs exits 3 under /VERYSILENT). Covers the exact Proton env recipe, the FitGirl=/VERYSILENT vs KaOs=/SILENT flag difference, the wine E drive to flaky-USB trap, missing wine32, innoextract failing on obfuscated KaOs headers, and harness redaction/pkill quirks. Use when LO has a repack in binks brew or Downloads or Desktop and says install it, unpack it, kaOs is broken, fitgirl will not install, or wants a Windows game running on his Linux box.
category: linux-desktop
---

# Install Windows Repacks Under Wine (Linux)

LO collects Windows game repacks (KaOs, FitGirl, etc.) in folders like
`~/Desktop/binks brew/`. They are multi-part RARs or pre-extracted `setup.exe` + `fg-*.bin` /
`KaOs-01.bin` payloads. Goal: get the game running on his Linux desktop via Wine (he does NOT
use Steam for these; "stand alone installs"). There is no native Linux build of WinRAR and no
native Linux build of these games, so Wine is the only path.

## Mental model of a repack installer
- It is almost always **Inno Setup** (`setup.exe` / `Install.exe`, PE32 i386, 8 sections).
- It carries a **compressed payload** (`fg-01.bin`, `KaOs-01.bin`, ~2 to 22 GB) using a FreeArc /
  `ISDone.dll` + `cls-*.dll` (`cls-lollypop`, `cls-magic2`) codec chain.
- It writes a placeholder (`inner.fgpack`, 0 bytes) then the ISDone thread expands the bin
  into real game files. **If `inner.fgpack` stays 0 bytes, the unpack thread never ran.**
- The default install path is often `E:\Games\<Name>\`. Under Wine, `E:` maps to a DOS device
  symlink in `~/.wine/dosdevices/`.

## PRIMARY METHOD — use Steam's Proton, NOT vanilla Wine (2026-07-16 correction)
Vanilla Wine 10 (wow64) on LO's box CANNOT run the repack ISDone/FreeArc unpack thread. Every
Wine attempt — interactive, /VERYSILENT, with wine32 installed, E: remapped, all DLLs loading,
disk space fine — stalled at 0-byte `inner.fgpack` (Jackbox) or exited 3 (KaOs /VERYSILENT).
The decompression simply does not schedule under vanilla Wine here. **Steam's Proton unpacks
both FitGirl and KaOs repacks cleanly.** Steam is installed as a *snap*; Proton ships inside it.

Proton path (verified present):
`/home/hunter/snap/steam/common/.local/share/Steam/steamapps/common/Proton - Experimental/proton`

### STEP-BY-STEP (Proton happy path)
1. **Extract the RAR parts** (if multi-part) with the `unrar` CLI, NOT a GUI click:
   ```plaintext
   cd "<repack dir>"; mkdir -p extracted
   unrar x -o+ kas-*.part1.rar extracted/
   ```
   (Verified: `rar`/`unrar` 7.23 at /usr/local/bin; `unrar` 7.2.4 nonfree via apt both work.
   `7z l` can LIST a RAR5 to confirm integrity.)
2. **Write a launch script** (do NOT inline the env in a one-liner — the harness redacts
   XAUTHORITY-style paths and the `PROTON` path has a space, so a script file is safer). Template:
   `scripts/run_repack_proton.sh`. Key env:
   ```bash
   export STEAM_COMPAT_CLIENT_INSTALL_PATH="/home/hunter/snap/steam/common/.local/share/Steam"
   export STEAM_COMPAT_DATA_PATH="/home/hunter/Games/proton-<name>"   # fresh prefix per game
   export WINEPREFIX="/home/hunter/Games/proton-<name>/pfx"
   export DISPLAY=":0"
   export PROTON_NO_XALIA="1"   # Xalia gamepad shim crashes headless ("No displays available"); harmless to disable
   PROTON="/home/hunter/snap/steam/common/.local/share/Steam/steamapps/common/Proton - Experimental/proton"
   cd "<repack dir>"
   exec python3 "$PROTON" run "setup.exe" /VERYSILENT /SUPPRESSMSGBOXES /DIR="$DEST" /NOCANCEL
   ```
   NOTE: `STEAM_COMPAT_DATA_PATH` dir MUST exist before Proton runs or it throws
   `FileNotFoundError: .../pfx.lock`. `mkdir -p` it in the script BEFORE invoking proton.
3. **Flag choice matters** (this is the subtle part):
   - **FitGirl** (`setup.exe`): `/VERYSILENT` works. Data persists across runs; if the installer
     hangs at the final shortcut/cleanup step (Xalia), the exe is usually written on the 2nd-3rd
     pass. Just re-run; it finalizes.
   - **KaOs** (`Install.exe`): `/VERYSILENT` aborts with **exit 3** every time. Use **`/SILENT`**
     (shows progress UI, auto-proceeds) instead. `/SILENT` unpacked all 27 GB fine.
4. **Run as background process** (`terminal(background=true)`, `notify_on_complete=true`). The
   unpack is 2-27 GB; poll `du -sh $DEST` and `find $DEST -iname "*.exe"`.
5. **Installer hangs at the end** (stuck on Xalia/shortcut, size stable, exes present): safe to
   `kill -9` the `Install.exe`/`proton` PIDs. Game data is complete. Verify exe exists.
6. **Write the Desktop `.desktop`** — do NOT inline the Proton env in the Exec (xfce drops the
   env vars when it launches, so the game silently never starts — see Pitfall J). Instead point
   Exec at a **launch script** that sets all vars itself:
   ```ini
   [Desktop Entry]
   Name=<Game>
   Comment=<Game> (repack) - Proton/Wine
   Exec=/home/hunter/Games/launch_<name>.sh
   Icon=applications-games
   Terminal=false
   Type=Application
   Categories=Game;
   StartupNotify=true
   ```
   `launch_<name>.sh` reuses the `scripts/run_repack_proton.sh` template but with `exec python3
   "$PROTON" run "/home/hunter/Games/<Name>/<Game>.exe"` as the final line, AND sets
   `XAUTHORITY` explicitly (loop over `/run/user/1000/gdm/Xauthority`,
   `/run/user/1000/.Xauthority`, `/home/hunter/.Xauthority` if unset) so the game can open the X
   display even from a stripped click env.
7. **MAKE THE .desktop TRUSTED (critical, easy to miss — see Pitfall J).** After writing/chmod,
   run `gio set "<path>.desktop" "metadata::trusted" true` for EVERY desktop launcher (games AND
   HueForge/Luban). Without this xfce refuses to execute it on double-click.

### Fallback — vanilla Wine (usually FAILS here, keep only if Proton unavailable)
If Proton is somehow missing: install `wine wine32`, remap E: (Pitfall A), launch interactive.
Expect the ISDone stall (Pitfall B); it may work on other boxes but NOT on LO's current AMD
Ubuntu 26.04 Wine 10 build. Treat Proton as the default.

## PITFALLS (each one cost a full debug session, encode them)

### Pitfall A -- E drive points at the flaky DEMIURGE USB
LO's Wine `E:` is symlinked to `/run/media/hunter/DEMIURGE` (exfat, label flips, often
unmounted, see memory). Repack installers DEFAULT to `E:\Games\...`. If DEMIURGE is unmounted
the installer hangs forever writing 0 bytes, or logs
`menubuilder:InvokeShellLinker failed to extract icon from L"E:\Games\..."`.
**Fix:** remap `E:` to `/home/hunter/Games` (always-mounted local path) BEFORE launching.
This alone unblocks most "installer does nothing" cases. Verify with `readlink -f ~/.wine/dosdevices/e:`.

### Pitfall B -- ISDone FreeArc STALLS under vanilla Wine (use Proton instead)
Under Wine 10's wow64 mode on LO's box, the ISDone unpack thread never schedules: `inner.fgpack`
stays 0 bytes, process sits at ~31 MB (redist + uninstaller only) indefinitely, across
interactive, /VERYSILENT, wine32-installed, E:-remapped, and all-DLLs-loading attempts. This is
the number-one "kaOs is broken" symptom and vanilla Wine does NOT fix it here. **The fix is
Proton** (see PRIMARY METHOD). You may also see `err:richedit:ReadColorTbl malformed entry` and
`trackbar` spam under Wine — those are harmless UI noise, not the cause.

### Pitfall J -- the game .desktop launcher won't boot on a real xfce DOUBLE-CLICK (boots fine from a terminal)
Three independent failures, all hit live:
1. **Untrusted .desktop.** A Desktop `.desktop` is NOT executed on click just because it is
   `chmod +x`. xfce/gvfs requires `gio set <file> "metadata::trusted" true`. Without it the
   click opens the file as text / does nothing. Set the flag after writing the launcher and
   verify with `gio info -a "metadata::trusted" <file>`.
2. **Inline `env VAR=... proton run game.exe` Exec line fails under xfce.** The DE launches the
   .desktop in a stripped env and the `env` prefix does NOT reliably pass STEAM_COMPAT_* to
   Proton → game never starts. FIX: point Exec at a wrapper **script** that sets all Proton
   env vars (STEAM_COMPAT_CLIENT_INSTALL_PATH, STEAM_COMPAT_DATA_PATH, WINEPREFIX, DISPLAY,
   XAUTHORITY fallback, PROTON_NO_XALIA=1) itself, then `exec python3 "$PROTON" run <exe>`.
3. **Spaced filename breaks gtk-launch.** `gtk-launch "/home/hunter/Desktop/Jackbox Party Pack.desktop"`
   returns `no such application` and the game silently doesn't launch (a leftover process from
   an earlier test may still be "running", masking the failure). RENAME the .desktop to a
   no-space name (`Jackbox.desktop`). xfce double-click tolerates spaces but gtk-launch does not.
Verify a launcher actually works by simulating the click: `gtk-launch <desktop-file>` in
background, then `pgrep -f <game.exe>` AND `xwininfo -root -children | grep steam_proton`
(a real game window, not just a 1x1 stub). Never declare "fixed" from a terminal launch alone —
the terminal inherits DBUS/XAUTHORITY the click may not.

### Pitfall G -- harness redacts credential-ish paths in commands
The Hermes CLI terminal redacts strings that look like XAUTHORITY (`/run/user/1000/gdm/Xauthority`
becomes `/run/u...rity`) in BOTH terminal output and `write_file` content. Do NOT try to inline
the Proton env in a one-liner — write a launch **script file** (see `scripts/run_repack_proton.sh`)
and avoid embedding literal XAUTHORITY. `DISPLAY=:0` and the Proton path (which contains a space)
work fine inside a script; just don't rely on copy-pasting them through the terminal.

### Pitfall H -- `pkill` self-kills its own bash subshell
`pkill -f "setup.exe"` matches the very command line that launched it, so the shell dies
(exit -15/-9) before/while killing targets. Two safe patterns: (a) `kill -9 <explicit_pids>`
grabbed from a prior `pgrep`; or (b) run pkill as a separate, isolated `terminal()` call and
ignore its exit code, then verify with a follow-up `pgrep`. Do not chain pkill with the
verification in the same line expecting the verification to run.

### Pitfall C -- wine32 is NOT installed by apt install wine
Ubuntu 26.04's `wine` metapackage pulled `wine64` + `libwine:amd64` but NOT the 32-bit runtime.
The installer and its `cls-lollypop_x86.exe` helper are 32-bit (PE32 i386) and silently fail
to run without it. No missing-DLL error appears (everything loads), it just stalls.
**Fix:** `sudo apt-get install -y wine32` (pulls `libwine:i386`). Confirm with
`dpkg -l | grep wine32`.

### Pitfall D -- innoextract fails on KaOs
KaOs uses Inno Setup 5.3.10 with an obfuscated or modified header. `innoextract` reports
`Stream error while parsing setup headers!` even though the bin is byte-intact. Do NOT rely on
innoextract for KaOs, run the real `Install.exe` under Wine. (innoextract 1.9 handles clean
Inno up to 6.0.5; KaOs's header defeats it.)

### Pitfall E -- multiple overlapping installer instances deadlock
Launching Superliminal + Jackbox + retries concurrently makes the instances lock each other's
`.bin` files and never progress. Kill ALL with `kill -9 <pids>` (SIGTERM sometimes self-kills
the bash subshell and misses them), confirm `pgrep -af "setup.exe|Install.exe"` is empty, then
run ONE game at a time, solo.

### Pitfall F -- harness backgrounding
The Hermes CLI terminal rejects `&`, `nohup`, `setsid`, `disown`. Use `terminal(background=true)`
with `notify_on_complete=true` for any long unpack. Do NOT use `wait` with more than 180s
(clamped); poll instead.

### Pitfall J -- untrusted `.desktop` = double-click does NOTHING (game "won't boot")
Even after the game unpacks AND boot-tests clean (process spawns under Proton), LO will report
"none of them actually boot" when he double-clicks the Desktop icon. Root cause: xfce (and most
Linux DEs) refuses to EXECUTE a `.desktop` file on the Desktop unless it carries the gvfs
`metadata::trusted=true` flag. The file can be `-rwxrwxr-x` (executable bit set) and STILL be
treated as untrusted — xfce opens it in a text editor or does nothing on click. This burned a
full debug cycle on 2026-07-16 (Jackbox/Superliminal both "wouldn't boot" from the click, though
`gtk-launch` and the script ran them fine).
SYMPTOM: `.desktop` is executable, `gtk-launch <file>` launches the game, but a real double-click
does nothing. `gio info -a "metadata::trusted" <file>` shows `metadata::trusted: false` (or absent).
FIX (do this for EVERY desktop launcher you create):
  ```bash
  gio set "/home/hunter/Desktop/<Name>.desktop" "metadata::trusted" true
  ```
  Verify with `gio info -a "metadata::trusted" <file>` → `metadata::trusted: true`. Optionally
  force a re-read by relaunching `nemo-desktop` (NOT `pkill -HUP xfdesktop` — that kills the
  panel on this nemo-based box, see skill `xfce-desktop-icon-persistence`). Also: an inline
  `env VAR=...` Exec does NOT reliably pass vars when xfce launches it — wrap the launch in a
  script (step 6/7) so the env is set inside the script, not by the .desktop. Both fixes together
  = clickable game.
SUB-PITFALL: **NO SPACES in the .desktop filename.** A name like `Jackbox Party Pack.desktop`
makes `gtk-launch` and xfce's launcher resolver report `no such application` — the game silently
never launches even when trusted + correct Exec. Rename to `Jackbox.desktop` (no space). This bit
on 2026-07-16: after the trust fix the click STILL failed until the spaced filename was renamed.
When finishing a repack install (or any desktop cleanup pass), do NOT bundle file deletions
(`rm` of dead launchers, old AppImages, `rm -rf` of build dirs) into one big command. LO blocked
every bundled delete this session — including obviously-dead `.cache`/`.lumen_tmp` pytest
`lumen.AppImage` copies — THREE times in a row. He wants to control exactly what gets deleted,
especially anything near his project folders (`~/Commander/`, `~/Desktop/StockBot/`,
`~/Desktop/Demiurge3D/`, `~/Desktop/Lumen/`).
SAFE pattern:
  (a) Surface a CLEANUP LIST (path + reason + keep-or-delete) and let him approve each line, OR
  (b) Delete ONLY when he names the exact path.
Never `rm -rf` a project dir or `rm` a batch of AppImages in one shot. Preview with a read-only
`find ... | head` before any delete, and run the actual `rm` as its own isolated call. Note:
folderize + `mv` (move launchers into `apps/`, docs into `Docs/`) is non-destructive and fine to
do without asking — only DELETES need explicit per-item consent. This is a standing LO preference
that applies to ALL cleanup, not just repacks (see memory: delete-consent).

## VERIFY
- Game exe exists: `find /home/hunter/Games/<Name> -iname "*.exe" | grep -vi redist`
- Desktop shortcut present + executable: `ls -l ~/Desktop/*.desktop`.
- **BOOT TEST (does it actually RUN, not just unpack?)** — launch the game exe under Proton in
  background, then confirm the process spawned clean:
  ```bash
  # in run_repack_proton.sh style env, then:
  python3 "$PROTON" run "<Game>.exe" > /tmp/boot.log 2>&1 &
  sleep 15
  pgrep -af "<Game>.exe" | grep -v "bash -c" && echo "BOOTED" || echo "NOT RUNNING"
  grep -iE "error|exception|fail|cannot|crash|missing" /tmp/boot.log | grep -viE "Xalia|No displays"
  ```
  - A live `<Game>.exe` process after 15s = clean boot. The `Xalia ... No displays available`
    exception in the log is Proton's gamepad shim crashing headless — HARMLESS, ignore it.
  - If `pgrep` shows nothing and the log has a real game error (missing DLL, Unity crash), the
    prefix may need `winetricks` deps (e.g. `vcrun2019`, `d3dx11`) — add to the script's prefix
    and re-run. Verified: SuperliminalGOG.exe and Jackbox Launcher.exe both BOOT clean under
    Proton on LO's box (2026-07-16).
  - Kill the test process after with `kill -9 <pid>` (separate call; see Pitfall H).

## References
- `references/repack-debug-transcripts.md` -- actual error lines seen (E icon error, ISDone
  stall at 31 MB, wine32 absent, innoextract KaOs failure, overlapping-instance lock, and the
  Proton "No displays available" Xalia crash which is harmless).
- `scripts/run_repack_proton.sh` -- COPY-AND-EDIT template that sets the exact Proton env vars
  and launches the installer correctly (handles the pfx.lock dir-exists requirement, the
  FitGirl/KaOs flag difference, and PROTON_NO_XALIA). Use this instead of inlining the command.
- `scripts/launch_repack_game.sh` -- COPY-AND-EDIT launcher for the GAME exe after install.
  Sets XAUTHORITY explicitly (so the game opens a display even from a stripped xfce click env)
  and is the correct Exec target for the Desktop `.desktop` (paired with
  `gio set ... metadata::trusted true`, see Pitfall J).
- Companion skill `linux-archive-tools` covers the WinRAR-equivalent GUI archiver setup that
  precedes repack work (engrampa + `unrar` + `p7zip-full`).
