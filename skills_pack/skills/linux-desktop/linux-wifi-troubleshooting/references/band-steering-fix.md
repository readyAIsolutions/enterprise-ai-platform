# Band Steering Fix Procedure

## Problem
Router broadcasts same SSID on 2.4 GHz and 5 GHz. Client roams between bands, causing:
- Periodic disconnects (30s - 5min intervals)
- "authenticate/associate" cycles in dmesg
- Latency spikes during roam
- IPv6 address flapping

## Detection

```bash
# Scan shows same SSID on multiple channels/frequencies
nmcli -f ssid,bssid,chan,freq,signal dev wifi list | grep -i <SSID>

# Example output:
# Wii Fii    9C:1E:95:8B:3B:22  11   2462 MHz  87  WPA2   (2.4 GHz ch 11)
# Wii Fii    9C:1E:95:8B:3B:26  149  5745 MHz  70  WPA2   (5 GHz ch 149)

# Connection has no BSSID lock
nmcli connection show "<SSID>" | grep -E "bssid|band|channel"
# 802-11-wireless.bssid:                  --
# 802-11-wireless.band:                   --
# 802-11-wireless.channel:                0
```

## Fix: Lock to 5 GHz BSSID

```bash
# 1. Identify 5 GHz BSSID (higher channel number, 5xxx MHz)
nmcli -f ssid,bssid,chan,freq,signal dev wifi list | grep -i <SSID>

# 2. Lock connection
nmcli connection modify "<SSID>" \
  802-11-wireless.bssid <5GHZ_BSSID> \
  802-11-wireless.band a \
  802-11-wireless.channel <5GHZ_CHANNEL>

# 3. Reconnect
nmcli connection up "<SSID>"

# 4. Verify
nmcli device show <interface> | grep -E "STATE|IP4|IP6"
nmcli connection show "<SSID>" | grep -E "bssid|band|channel"
```

## Better Fix: Separate SSIDs on Router

**Router configuration (preferred):**
- 2.4 GHz SSID: "Home-2.4G" (or "Home-IoT")
- 5 GHz SSID: "Home-5G" (or just "Home")

**Benefits:**
- Client never roams between bands
- Explicit control over which band devices use
- IoT devices on 2.4 GHz, laptops/phones on 5 GHz
- No driver/firmware roaming bugs

## Verification After Fix

```bash
# Monitor for 10+ minutes
watch -n 10 'nmcli device show wlp4s0 | grep STATE; ip -s link show wlp4s0'

# Check kernel log for roaming
dmesg -T -w | grep -i wlp4s0

# Should see ZERO authenticate/associate cycles after initial connect
```

## When NOT to Lock BSSID

- Mesh systems with multiple APs (same BSSID across nodes = seamless roam)
- Enterprise 802.11r/k/v roaming environments
- Mobile devices that move through the house

**For stationary desktop:** Always lock to 5 GHz BSSID or use separate SSIDs.