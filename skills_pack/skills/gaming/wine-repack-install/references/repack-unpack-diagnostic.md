# Repack Unpack Diagnostic — Superliminal (FitGirl) + Jackbox (KaOs) session

## Evidence chain (FitGirl Superliminal, Wine 10, Ubuntu 26.04)

Installer: `setup.exe` (Inno Setup 5.x, 32-bit PE). Temp dir
`/home/hunter/.wine/drive_c/users/hunter/AppData/Local/Temp/is-XXXX.tmp/`
contains the decompression stack:
- `ISDone.dll` — Inno Setup decompression plugin (drives the unpack)
- `cls-lollypop_x64.exe`, `cls-lollypop_x86.exe`, `cls-lollypop.dll`
- `cls-magic2*.exe/.dll`, `cls-srep*.exe`, `CLS-srep.dll`
- `arc.ini`, `CLS.ini`, `English.ini`, `facompress.dll`, `mpz.exe`, `FlushFileCache.exe`

### CLS.ini (the smoking gun) — TempPath hardcoded to E:\
```
[Srep]      TempPath=E:\Superliminal
[Precomp]   TempPath=E:\Superliminal\
[mtx]       TmpPath=E:\Superliminal
[magic2l]   ldmfTempPath=E:\Superliminal
```
Every codec writes scratch files to `E:\<Game>`. On LO's box wine `E:` =
`/run/media/hunter/DEMIURGE` (flaky exfat USB, often unmounted). Dead drive ->
decompression thread dies instantly -> `inner.fgpack` stays 0 bytes, only
`_Redist/` + `unins000.*` written.

### arc.ini externals observed (why native 7z/unar fail)
FreeArc external compressors: precomp043, fbz, nco (nz.exe), mpz, precomp,
reflate, msc, pzlib, piggy, lzma2, uharcx, bcm, woohoo, lol4 (cls-lolzx),
pz3, plzo, exenew, rzw, mpzz (oggre_dec), xt/xtool, prelz4, prex (precompx),
fitjpg (jfit), mtxprecomp. These are FitGirl-custom; standard `unar`/`7z` do
not recognize `fg-*.bin`.

### Error transcript tells
- Install reaches "Please wait while Setup installs..." then:
  - `/VERYSILENT` -> exits code 3 (Inno aborts, likely a [Code] post-step or
    prereq check failing headless).
  - interactive/headless -> stalls, fgpack 0 bytes.
- `WINEDEBUG=+loaddll` -> ZERO "module not found". All DLLs load. So it is NOT
  a missing-dependency problem; it is the unpack thread not scheduling.
- Progress signal (install actually got far):
  `menubuilder:InvokeShellLinker failed to extract icon from L"E:\Superliminal\SuperliminalGOG.exe"`
  The icon error is harmless; reaching the shortcut stage = unpack completed.
  Game exe name confirmed: `SuperliminalGOG.exe`.

## What was tried (and result)
| Attempt | Result |
|---|---|
| `innoextract -d` on Install.exe | "Stream error while parsing setup headers" (KaOs Inno header obfuscated) |
| `wine Install.exe /VERYSILENT /DIR=...` | exit 3 |
| `wine Install.exe` interactive (DISPLAY=:0) | launches, LO can click; unpack thread needs live pump |
| winetricks d3dx9 + vcrun2010 | exit 0, but did NOT fix stall (prereqs were not the issue) |
| `apt install wine32` (libwine:i386) | installed; did NOT fix stall alone |
| remap E: -> /home/hunter/Games (live, writable) | still stalled at 0 bytes -> E: path was a red herring; ISDone thread is the real wall |
| DEMIURGE USB mounted (E: live) | one run reached shortcut stage -> confirms E: liveness helps but isn't sufficient alone |

## Conclusion / next attempts for a future session
The unpack stall is environmental (Wine 10 wow64 + ISDone/FreeArc). Most
promising real fixes, in order:
1. Run installer INTERACTIVELY with a real X display (not /VERYSILENT). LO can
   see/click and hears the FitGirl music during unpack.
2. Use Proton (Steam compat) instead of vanilla wine — better ISDone handling.
3. Native `fa` (freearc) against fg-*.bin with the repack's arc.ini.
4. Ensure E: is a live writable path (mount USB or separate prefix) — necessary
   but not sufficient.

## Jackbox (KaOs) specifics
- 5 RAR parts -> `rar x kas-XXX.part1.rar` -> `Install.exe` (10MB) + `KaOs-01.bin` (21.8GB, exact size 21891320209 bytes, intact).
- Same ISDone/7z stall class. exe expected at `/home/hunter/Games/Jackbox Party Pack/JackboxPartyPack.exe` (guessed; verify after unpack).
- KaOs installer also exits 3 under /VERYSILENT for the same reason.
