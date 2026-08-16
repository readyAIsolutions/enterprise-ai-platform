#!/bin/bash
# Template: run a Windows repack installer under Steam's Proton (bypasses vanilla Wine ISDone stall).
# Copy this file, set NAME / SRC / INSTALLER, then:  bash run_repack_proton.sh
# IMPORTANT: STEAM_COMPAT_DATA_PATH dir must exist before proton runs (proton creates pfx.lock there).
# Do NOT inline these env vars in a terminal one-liner — the harness redacts XAUTHORITY-like paths.

NAME="superliminal"          # used for prefix dir + dest dir; lowercase, no spaces
SRC="/home/hunter/Desktop/binks brew/Superliminal [FitGirl Repack]"   # repack folder with setup.exe
INSTALLER="setup.exe"        # setup.exe (FitGirl) or Install.exe (KaOs)
# FLAG: FitGirl => /VERYSILENT ;  KaOs => /SILENT  (KaOs /VERYSILENT aborts exit 3)
FLAG="/VERYSILENT /SUPPRESSMSGBOXES /NOCANCEL"

export STEAM_COMPAT_CLIENT_INSTALL_PATH="/home/hunter/snap/steam/common/.local/share/Steam"
export STEAM_COMPAT_DATA_PATH="/home/hunter/Games/proton-${NAME}"
export WINEPREFIX="/home/hunter/Games/proton-${NAME}/pfx"
export DISPLAY=":0"
export PROTON_NO_XALIA="1"   # Xalia gamepad shim crashes headless ("No displays available"); harmless off

PROTON="/home/hunter/snap/steam/common/.local/share/Steam/steamapps/common/Proton - Experimental/proton"
DEST="/home/hunter/Games/${NAME}"

mkdir -p "$STEAM_COMPAT_DATA_PATH"
# For a clean re-unpack, rm -rf "$DEST" here. For a retry that should reuse partial data, skip the rm.
mkdir -p "$DEST"
cd "$SRC"
exec python3 "$PROTON" run "$INSTALLER" $FLAG /DIR="$DEST"
