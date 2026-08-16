#!/usr/bin/env bash
# amd-ultimate-tune.sh — RX 5700 XT tuned for GAMING + AI MODELING + 3D PRINTING
# Run on the REAL desktop: sudo bash ~/amd-ultimate-tune.sh
# Applies LIVE. No reboot forced — a boot service re-applies on next restart.
set -e
export DEBIAN_FRONTEND=noninteractive

echo "[*] installing low-latency gaming extra: gamescope (optional)"
apt-get install -y gamescope 2>/dev/null || echo "[!] gamescope not in repos here — install via flatpak if wanted"

echo "[*] writing /usr/local/bin/amd-perf-apply.sh (the boot-time tuner)"
cat >/usr/local/bin/amd-perf-apply.sh <<'APPLY'
#!/usr/bin/env bash
shopt -s nullglob
# Applied at boot by amd-perf.service — also runnable live.
for d in /sys/class/drm/card*/device; do
  [ -w "$d/power_dpm_force_performance_level" ] && echo high > "$d/power_dpm_force_performance_level"
  [ -w "$d/power_dpm_state" ] && echo performance > "$d/power_dpm_state"
done
D=/sys/class/drm/card0/device
if [ -w "$D/pp_od_clk_voltage" ]; then
  echo "s 7 2150 1050" > "$D/pp_od_clk_voltage"
  echo "m 1 1900 900"   > "$D/pp_od_clk_voltage"
  echo "committed"      > "$D/pp_od_clk_voltage"
fi
for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do echo performance > "$g" 2>/dev/null; done
for p in /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference; do echo performance > "$p" 2>/dev/null; done
for b in /sys/block/nvme*; do
  [ -w "$b/queue/scheduler" ]     && echo mq-deadline > "$b/queue/scheduler" 2>/dev/null
  [ -w "$b/queue/read_ahead_kb" ] && echo 2048        > "$b/queue/read_ahead_kb" 2>/dev/null
done
APPLY
chmod +x /usr/local/bin/amd-perf-apply.sh

echo "[*] applying live (this session)"
/usr/local/bin/amd-perf-apply.sh

echo "[*] installing boot service"
cat >/etc/systemd/system/amd-perf.service <<'UNIT'
[Unit]
Description=AMD GPU + CPU performance tuning (gaming / AI / 3D print)
After=multi-user.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/amd-perf-apply.sh
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now amd-perf.service

echo "[*] gaming snappiness: disable GNOME animations for hunter"
sudo -u hunter gsettings set org.gnome.desktop.interface enable-animations false 2>/dev/null || true
sudo -u hunter gsettings set org.gnome.desktop.interface gtk-enable-animations false 2>/dev/null || true

echo "[*] OpenCL via rusticl (so OpenCL AI / Blender / print tools use the GPU, not CPU)"
add-apt-repository -y universe >/dev/null 2>&1 || true
for pkg in mesa-opencl-rt rusticl-opencl-icd ocl-icd-libopencl1 clinfo; do
  if apt-get install -y "$pkg" >/dev/null 2>&1; then echo "  + $pkg"; else echo "  - $pkg (n/a)"; fi
done
echo "    OpenCL devices seen:"; clinfo 2>/dev/null | grep -iE 'radeon|navi|device' | head

echo "[*] shell helper: llama() defaults to FULL GPU offload (-ngl 99)"
grep -q 'llama()' /home/hunter/.bashrc || printf '\n# ENI: default llama.cpp to the 5700 XT (full GPU offload)\nllama() { /opt/llama.cpp/build/bin/llama-cli -ngl 99 -m "$1" "${@:2}"; }\n' >> /home/hunter/.bashrc
grep -q 'HOME/bin' /home/hunter/.bashrc || printf '\n# ENI: ~/bin on PATH (game / gpu-check)\nexport PATH="$HOME/bin:$PATH"\n' >> /home/hunter/.bashrc

echo
echo "[*] DONE. No reboot needed — everything above applied LIVE and will also"
echo "    reapply at boot via amd-perf.service. Reboot whenever you're ready."
echo "    GPU watch :  radeontop   (or CoreCtrl)"
echo "    AI test   :  /opt/llama.cpp/build/bin/llama-cli -m <model>.gguf -ngl 99"
echo "    Revert UV :  echo r > /sys/class/drm/card0/device/pp_od_clk_voltage"
echo "    Steam tip :  launch option ->  gamescope -f -- %command%"
