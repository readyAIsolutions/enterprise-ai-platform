#!/bin/bash
# LAUNCH a repack game exe under Steam Proton (copy + edit).
# Used as the Exec target of a Desktop .desktop so xfce passes the env reliably.
# After creating the .desktop, mark it trusted:
#   gio set "/home/hunter/Desktop/<Name>.desktop" "metadata::trusted" true
set -u
GAME_NAME="<name>"            # e.g. superliminal / jackbox
GAME_EXE="/home/hunter/Games/<Name>/<Game>.exe"   # e.g. SuperliminalGOG.exe / Launcher.exe
DEST_DIR="/home/hunter/Games/<Name>"

export STEAM_COMPAT_CLIENT_INSTALL_PATH="/home/hunter/snap/steam/common/.local/share/Steam"
export STEAM_COMPAT_DATA_PATH="/home/hunter/Games/proton-${GAME_NAME}"
export WINEPREFIX="/home/hunter/Games/proton-${GAME_NAME}/pfx"
export DISPLAY="${DISPLAY:-:0}"
# XAUTHORITY: set explicitly so the game can open the X display even from a stripped click env
if [ -z "${XAUTHORITY:-}" ]; then
  for p in /run/user/1000/gdm/Xauthority /run/user/1000/.Xauthority /home/hunter/.Xauthority; do
    [ -f "$p" ] && export XAUTHORITY=*** && break
  done
fi
export PROTON_NO_XALIA="1"   # Xalia gamepad shim crashes headless ("No displays available"); harmless

PROTON="/home/hunter/snap/steam/common/.local/share/Steam/steamapps/common/Proton - Experimental/proton"
cd "$DEST_DIR"
exec python3 "$PROTON" run "$GAME_EXE"
