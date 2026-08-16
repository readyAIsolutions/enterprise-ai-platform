# Combined Sink + Loopback Pattern

The canonical pattern for a "mic + desktop audio" combined sink that apps like Signal, Discord, and OBS can use as a single input device.

## Architecture

```
Real Mic (Volt 2 / webcam) ──→┐
Desktop Audio Share .monitor ─→├──→ CombinedSink ──→ RemapSource ──→ "Mic+Desktop" (app input)
Signal Virtual Sink .monitor ─→┘
```

## The Bug (July 2026)

**Symptom**: User can't be heard in Signal calls. Mics test fine individually. All loopbacks appear loaded.

**Root cause**: The startup script used `DEFAULT_MIC=$(pactl get-default-source)` to find the real mic. At boot time, PipeWire returned `signal-sink.monitor` — a virtual monitor source — as the default. The loopback silently routed empty virtual audio instead of real mic input. The systemd journal confirmed: `Using mic: signal-sink.monitor`.

**Why it happens**: PipeWire initializes virtual devices (from `pipewire.conf.d/`) before enumerating real ALSA hardware. If a virtual source happens to be the "default" when the script runs, it gets picked instead of a real mic.

**Fix**: Never use `pactl get-default-source` in scripts. Enumerate real hardware sources explicitly:

```bash
# WRONG — can return monitors or virtual sources
DEFAULT_MIC=$(pactl get-default-source)

# RIGHT — explicit device names, monitor-filtered
for mic in \
    "alsa_input.usb-Universal_Audio_Volt_2_22232037058502-00.HiFi__Mic1__source" \
    "alsa_input.usb-Sunplus_IT_Co_Live_Streamer_CAM_313_20200529002-02.mono-fallback"; do
    if pactl list short sources | grep -q "$mic"; then
        REAL_MIC="$mic"
        break
    fi
done
```

## Idempotent Module Loading

All `pactl load-module` calls must check for existing modules first. Duplicate modules break routing:

```bash
# Check before loading
if ! pactl list short modules | grep "loopback" | grep -q "RealMic.*CombinedSink"; then
    pactl load-module module-loopback source="$REAL_MIC" sink=MicPlusDesktop latency_msec=20
fi
```

## Verification Checklist

After startup, verify with:

```bash
# 1. All expected loopbacks loaded
pactl list short modules | grep loopback
# Should show: DesktopAudioShare→Combined, RealMic→Combined, signal-sink→Combined

# 2. Combined sink is RUNNING (has active inputs)
pactl list short sinks | grep -E "MicPlusDesktop|Combined"

# 3. Remap source exists
pactl list short sources | grep -v monitor | grep MicPlusDesktopSource

# 4. Check systemd journal for "Using mic:" line
journalctl --user -u audio-sharing-setup --no-pager | grep "Using mic:"
# Must show a real ALSA device, NOT *.monitor
```

## Signal Flatpak Specifics

Signal as a Flatpak connects via `pipewire-pulse` with `pipewire.access: flatpak`. Permissions needed:

```bash
flatpak permission-set pulseaudio pulseaudio org.signal.Signal yes
```

After any PipeWire routing change, Signal MUST be restarted — it caches the device list on startup.

## Complete Script Reference

The canonical idempotent setup script lives at `~/setup-audio-share.sh` on LO's system. Key properties:
- Idempotent: checks for existing modules before loading
- Explicit mic enumeration: never trusts `get-default-source`
- Multiple real mic fallbacks: Volt 2 Mic1 → webcam mic → Volt 2 Mic2
- Launched via systemd oneshot: `~/.config/systemd/user/audio-sharing-setup.service`