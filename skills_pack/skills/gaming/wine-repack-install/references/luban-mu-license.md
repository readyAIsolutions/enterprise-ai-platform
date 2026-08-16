# Luban (Snapmaker Luban) — MU full-version license + libtbb fix

LO's Luban is the Snapmaker "MU" edition (multi-function, full license). It
ships the license under a non-obvious filename and needs an old TBB lib that
Ubuntu 26.04 renamed.

## Full-version license
- Luban's binary looks for `MU_License.dat` in its working directory.
- The provided/downloaded license file is named `MU_EG_VTO.dat` (same content,
  wrong name).
- Fix: `cp MU_EG_VTO.dat MU_License.dat` next to the Luban binary.
- Verification: before fix, launch logs `[ReadLicense] No license file ...`;
  after fix, that line is absent and full features (MU toolpaths) are active.

## libtbb.so.2 missing (Ubuntu 26.04)
- Symptom: Luban fails to start / errors about `libtbb.so.2` not found.
- Cause: Ubuntu 26.04 ships `libtbb12` / `libtbb.so.12`; the binary wants the
  legacy `libtbb.so.2` (oneTBB 2020.3).
- Fix:
  ```
  curl -sL -o /tmp/libtbb2.deb "https://launchpad.net/ubuntu/+archive/primary/+files/libtbb2_2020.3-1ubuntu3_amd64.deb"
  mkdir -p /tmp/tbb && dpkg-deb -x /tmp/libtbb2.deb /tmp/tbb
  cp /tmp/tbb/usr/lib/x86_64-linux-gnu/libtbb.so.2 /usr/local/lib/
  ldconfig
  ```
- After: `ldconfig -p | grep libtbb.so.2` should list it.

## Launchers
- AppImage or extracted build under `~/Apps/`; symlink to `~/Desktop/apps/luban.desktop`.
- `cp ~/Desktop/apps/luban.desktop ~/Desktop/ && chmod +x ~/Desktop/luban.desktop`
