# Realtek RTL8168h (r8169 driver) Ethernet Fixes

## Hardware ID
- **PCI ID:** 10ec:8168 (rev 15 = RTL8168h/8111h)
- **Kernel driver:** r8169
- **Firmware:** rtl_nic/rtl8168h-2.fw (in linux-firmware)

## When to Apply
Use when **both WiFi AND ethernet drop simultaneously** — indicates system-wide PCIe ASPM issue, not just WiFi driver problem.

## Firmware Update (from upstream)

Ubuntu's `linux-firmware` package may have older `rtl8168h-2.fw`. Fetch latest:

```bash
cd /tmp && git clone --depth 1 https://git.kernel.org/pub/scm/linux/kernel/git/firmware/linux-firmware.git
sudo cp linux-firmware/rtl_nic/rtl8168h-2.fw /lib/firmware/rtl_nic/
sudo update-initramfs -u
sudo modprobe -r r8169 && sleep 2 && sudo modprobe r8169
```

## Driver Parameters (Kernel 7.x)

**r8169 does NOT support these module params** (silently ignored):
- `disable_aspm` — does not exist
- `aspm` — does not exist
- `eee_enable` — does not exist

**Check for ignored params:**
```bash
dmesg -T | grep "r8169: unknown parameter"
```

**Fix:** Use kernel cmdline `pcie_aspm=off` in `/etc/default/grub`:
```
GRUB_CMDLINE_LINUX_DEFAULT="quiet splash pcie_aspm=off"
```
Then `sudo update-grub` and reboot.

**Verify:**
```bash
cat /proc/cmdline | grep pcie_aspm
cat /sys/module/pcie_aspm/parameters/policy  # should show "performance" or "off"
```

## Normal Boot Pattern (Good)
```
r8169 0000:05:00.0 eth0: RTL8168h/8111h, a8:5e:45:e6:45:55, XID 541, IRQ 98
r8169 0000:05:00.0 eth0: jumbo features [frames: 9194 bytes, tx checksumming: ko]
r8169 0000:05:00.0 enp5s0: renamed from eth0
Generic FE-GE Realtek PHY r8169-0-500:00: attached PHY driver
r8169 0000:05:00.0 enp5s0: Link is Up - 1Gbps/Full - flow control rx/tx
```

## Problem Patterns

| Pattern | Meaning | Fix |
|---------|---------|-----|
| `Link is Down` repeatedly | ASPM putting link to sleep | `pcie_aspm=off` kernel param |
| `rtl8168h-2.fw` load failed | Missing/old firmware | Update from upstream git |
| `unknown parameter 'disable_aspm'` | Invalid modprobe param | Remove from modprobe.d; use kernel cmdline |

## Verification

```bash
# Link status
ethtool enp5s0 | grep -i -E "speed|duplex|link detected"

# Driver/firmware
ethtool -i enp5s0
# driver: r8169
# firmware-version: rtl8168h-2_0.0.2 02/26/15  (or newer date)

# No ignored params in dmesg
dmesg -T | grep "r8169" | grep -v "unknown parameter"
```

## Notes
- **rtl8168h-1.fw** also exists but `-2.fw` is newer (check git dates)
- When both MT7921E WiFi and RTL8168h ethernet drop together, it's **always** PCIe ASPM
- The `pcie_aspm=off` kernel parameter fixes both simultaneously
- No per-driver modprobe params needed for r8169 on kernel 7.x