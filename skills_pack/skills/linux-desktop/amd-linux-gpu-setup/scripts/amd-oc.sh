#!/usr/bin/env bash
# AMD Navi10 (RX 5700 XT) undervolt / overclock helper
# Run: sudo bash ~/amd-oc.sh        (dry run, prints OD table)
#     APPLY=1 sudo bash ~/amd-oc.sh  (commits a conservative UV/OC)
# amdgpu.ppfeaturemask already has bit 0x4000 (overdrive) on this box.
set -e
DEV=/sys/class/drm/card0/device
if [ ! -w "$DEV/pp_od_clk_voltage" ]; then
  echo "!! Overdrive sysfs not writable here."
  echo "   Reboot, or add amdgpu.ppfeaturemask=0xffffffff to GRUB cmdline and update-grub."
  exit 1
fi
echo "=== current OD table ==="
cat "$DEV/pp_od_clk_voltage"
echo
CORE_PSTATE=7
CORE_MHZ=2150
CORE_MV=1050
MEM_PSTATE=1
MEM_MHZ=1900
MEM_MV=900
if [ "${APPLY:-0}" != "1" ]; then
  echo "Dry run. Inspect the table above, edit values at top of script,"
  echo "then run: APPLY=1 sudo bash ~/amd-oc.sh"
  exit 0
fi
echo "s $CORE_PSTATE $CORE_MHZ $CORE_MV" > "$DEV/pp_od_clk_voltage"
echo "m $MEM_PSTATE $MEM_MHZ $MEM_MV"   > "$DEV/pp_od_clk_voltage"
echo "committed"                       > "$DEV/pp_od_clk_voltage"
echo "[*] applied. Verify: cat $DEV/pp_od_clk_voltage"
echo "[*] not persistent across reboot — re-run after boot, or wire into amd-perf.service."
