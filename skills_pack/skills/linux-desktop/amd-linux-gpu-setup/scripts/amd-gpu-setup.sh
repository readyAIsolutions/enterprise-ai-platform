#!/usr/bin/env bash
# AMD RX 5700 XT — games + AI setup for Ubuntu 26.04 (X11)
# Run on your REAL desktop: sudo bash ~/amd-gpu-setup.sh
set -e
export DEBIAN_FRONTEND=noninteractive
echo "[*] enabling 32-bit arch (Steam / Proton games need it)"
dpkg --add-architecture i386
apt-get update
echo "[*] installing Vulkan + 32-bit GL + gamemode + monitoring"
apt-get install -y \
  mesa-vulkan-drivers mesa-vulkan-drivers:i386 \
  vulkan-tools libvulkan1 libvulkan1:i386 vulkan-validationlayers \
  libgl1:i386 libegl1:i386 libglu1-mesa:i386 libosmesa6:i386 \
  gamemode libgamemodeauto0 radeontop lm-sensors glslc spirv-headers glslang-tools spirv-tools \
  || echo "[!] some packages failed to install — check the apt output above"
echo "[*] verifying Vulkan now sees the 5700 XT"
vulkaninfo --summary 2>/dev/null | grep -iE 'deviceName|driverName' \
  || echo "!! vulkaninfo missing output — check 'vulkaninfo' manually"
echo "[*] build tools for AI (llama.cpp Vulkan backend)"
apt-get install -y git build-essential cmake curl python3 python3-pip
echo "[*] building llama.cpp (runs LLMs on the 5700 XT via Vulkan)"
if [ ! -d /opt/llama.cpp ]; then
  git clone https://github.com/ggerganov/llama.cpp /opt/llama.cpp
fi
cd /opt/llama.cpp
cmake -B build -DGGML_VULKAN=ON
cmake --build build --jobs "$(nproc)"
echo "[*] llama.cpp ready. Test with:"
echo "      /opt/llama.cpp/build/bin/llama-cli -m <model>.gguf -ngl 99"
echo "[*] installing amdgpu high-performance boot service"
cat >/etc/systemd/system/amd-perf.service <<'UNIT'
[Unit]
Description=AMD GPU performance level = high at boot
After=multi-user.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/sh -c 'for d in /sys/class/drm/card*/device; do [ -w "$d/power_dpm_force_performance_level" ] && echo high > "$d/power_dpm_force_performance_level"; done'
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now amd-perf.service
echo
echo "[*] DONE. Log out / back in (or reboot) so ~/.config/environment.d/99-amd-perf.conf applies."
echo "[*] Optional undervolt / overclock: sudo bash ~/amd-oc.sh (tune to your silicon)"
echo "[*] NOTE on ROCm/PyTorch: Navi10 (gfx1010) dropped from modern ROCm; reliable AI path is"
echo "    Vulkan (llama.cpp above, onnxruntime-Vulkan, stable-diffusion.cpp, ComfyUI-Vulkan)."
echo "    HSA_OVERRIDE_GFX_VERSION is set in case you install a community ROCm build."
