# Repack Install Under Wine — Actual Debug Transcripts

Captured during the Jackbox (KaOs) + Superliminal (FitGirl) install session, 2026-07-16/17.
Use these exact strings to recognize each failure mode fast.

## Environment
- Host: Ubuntu 26.04 LTS, Wine 10.0~repack-12ubuntu1, wine32 installed later.
- Wine prefix: `/home/hunter/.wine`. DISPLAY=:0 (real X socket at /tmp/.X11-unix/X0 exists).
- Flaky USB: `/run/media/hunter/DEMIURGE` (exfat, label flips, often unmounted).

## Failure A — E: drive → dead DEMIURGE USB
Installer defaulted to `E:\Games\Superliminal\`. Wine `E:` was:
```
lrwxrwxrwx  e: -> /run/media/hunter/DEMIURGE
```
Symptom: installer wrote only `_Redist/`, `unins000.*`, `inner.fgpack` (0 bytes), sat at 31 MB.
Error line in wine log:
```
menubuilder:InvokeShellLinker failed to extract icon from L"E:\Games\Superliminal\SuperliminalGOG.exe"
```
Fix (run BEFORE launching installer):
```
rm -f ~/.wine/dosdevices/e:
ln -s /home/hunter/Games ~/.wine/dosdevices/e:
```
After fix, `readlink -f ~/.wine/dosdevices/e:` => `/home/hunter/Games`.

## Failure B — ISDone stall under /VERYSILENT (headless)
Silent run reached the install phase but aborted with exit code 3:
```
ShutdownBlockReasonCreate (...): stub
Please wait while Setup installs The.Jackbox...REPACK2-KaOs on your computer.
err:environ:init_peb starting L"...\D3DX9_44.dll" in experimental wow64 mode
... then exit code 3
```
With /DIR forced to a real local path and wine32 present, the installer still stalled at 31 MB
with `inner.fgpack` = 0 bytes when launched silently. Interactive launch (no /VERYSILENT) is
what actually completed the unpack — the FitGirl music plays and the progress bar moves only in
interactive mode.

Harmless UI noise to IGNORE:
```
err:richedit:ReadColorTbl malformed entry
err:trackbar:TRACKBAR_WindowProc unknown msg 064b
err:environ:init_peb starting L"..." in experimental wow64 mode
```

## Failure C — wine32 missing
`apt-get install -y wine` pulled only:
```
wine 10.0~repack-12ubuntu1 (all)
wine64 10.0~repack-12ubuntu1
libwine:amd64
```
`dpkg -l | grep wine32` => empty. Installer is 32-bit (PE32 i386); its `cls-lollypop_x86.exe`
helper could not run. No "module not found" — `WINEDEBUG=+loaddll` showed every DLL loading fine,
so the stall was NOT a missing dependency. Fix:
```
sudo apt-get install -y wine32   # pulls libwine:i386, wine32:i386
```

## Failure D — innoextract on KaOs
```
$ innoextract -d out Install.exe
Stream error while parsing setup headers!
 ├─ detected setup version: 5.3.10 (unicode)
 └─ error reason: basic_ios::clear: iostream error
Done with 1 error.
```
Bin is byte-intact (21891320209 bytes, exact). KaOs's Inno 5.3.10 header is obfuscated;
innoextract 1.9 cannot parse it. Fix: run the real Install.exe under Wine, not innoextract.
(7z also cannot read KaOs-01.bin directly — no 7z signature; the payload is Inno-stream-encoded.)

## Failure E — overlapping instances deadlock
Three installer PIDs alive at once (2x Superliminal silent + 1x Jackbox interactive) all reading
their `.bin` files => none progressed. `kill -15` (pkill) sometimes killed its OWN bash subshell
(exit -15) and missed the targets. Fix:
```
kill -9 3601158 3616792 3616863 3630263 3630333   # explicit PIDs
sleep 3
pgrep -af "setup.exe|Install.exe" | grep -v engrampa | grep -v "bash -c"   # expect empty
```
Then run ONE game solo.

## Working invocation (interactive, after E: remap + wine32)
```
export PATH=/usr/lib/x86_64-linux-gnu/wine:/usr/bin:$PATH
export WINEPREFIX=/home/hunter/.wine DISPLAY=:0
SRC="/home/hunter/Desktop/binks brew/Superliminal [FitGirl Repack]"
DEST="/home/hunter/Games/Superliminal"
rm -rf "$DEST"; mkdir -p "$DEST"; cd "$SRC"
wine "setup.exe" /DIR="$DEST"          # NO /VERYSILENT -> LO clicks through
```

## Desktop shortcut shape (after exe found)
```
[Desktop Entry]
Name=Superliminal
Exec=env WINEPREFIX=/home/hunter/.wine wine "/home/hunter/Games/Superliminal/SuperliminalGOG.exe"
Icon=applications-games
Terminal=false
Type=Application
Categories=Game;
```
(Jackbox exe name not yet confirmed at time of capture — find with
`find /home/hunter/Games/Jackbox -iname "*.exe" | grep -vi redist`.)
