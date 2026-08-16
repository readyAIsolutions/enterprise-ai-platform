# Boot Persistence & WirePlumber Defaults

Why both a PipeWire drop-in AND the boot service are needed, and how the
"all audio breaks / default sink is silent" failure mode is fully closed.

## The failure mode (one-sentence version)

If the GLOBAL default sink is a virtual-only null sink (e.g. `MicPlusDesktop`),
every app plays into a sink with no physical output -> word-wide silence.
Diagnose with `pactl get-default-sink`. If it returns a virtual/null sink, that's
the root cause of "audio is fucked in everything", NOT the streaming feature.

## The 3-layer boot persistence stack (2026-08, proven on LO's box)

1. PERSISTENT SINKS via PipeWire drop-in, so virtual sinks exist at EVERY boot
   before any service runs, eliminating the null-sink creation race.
   `~/.config/pipewire/pipewire.conf.d/98-desktop-audio-share.conf`:

       context.objects = [
           { factory = adapter args = {
                 factory.name = support.null-audio-sink
                 node.name = DesktopAudioShare
                 node.description = "Desktop_Audio_Share"
                 media.class = Audio/Sink
                 audio.channels = 2
                 audio.position = [ FL FR ] } }
           { factory = adapter args = {
                 factory.name = support.null-audio-sink
                 node.name = MicPlusDesktop
                 node.description = "Mic_Plus_Desktop_Audio_SELECT_THIS"  # underscore! spaces break args
                 media.class = Audio/Sink
                 audio.channels = 2
                 audio.position = [ FL FR ] } }
       ]

   Reload: `systemctl --user restart pipewire pipewire-pulse`, then
   `pactl list short sinks` to confirm. CAUTION: node.description with SPACES
   breaks `pactl load-module` arg parsing — use underscores in device.description.

2. SAFE BOOT FALLBACK — WirePlumber persists default sink/source at
   `~/.local/state/wireplumber/default-nodes` and restores them at startup.
   If the combined sink isn't created yet (service not run), WP falls back
   through the configuredsink list. Pin a REAL physical sink as a fallback:

       [default-nodes]
       default.configured.audio.sink=HearLocallyPlusStream
       default.configured.audio.sink.0=alsa_output.usb-...-HiFi__Line__sink   # PHYSICAL
       default.configured.audio.source=MicPlusDesktopSource

   DANGER: watch for ghost fallback entries pointing at virtual-only sinks
   (`MicPlusDesktop`, `combined-sink`). If the combined sink disappears at boot,
   WP would reroute audio into the void again. Prune them to physical sinks only.

3. BOOT SERVICE — `audio-sharing-setup.service` (Type=oneshot, RemainAfterExit,
   `After=pipewire.service pipewire-pulse.service wireplumber.service`,
   `WantedBy=default.target`, enabled). Runs `/home/hunter/setup-audio-share.sh`
   which: waits up to 30s for `pactl info`, resolves real mic (never literal
   `@DEFAULT_SOURCE@`), unloads stale modules, loads loopbacks with retry,
   `module-remap-source` for the app-visible mic, `module-combine-sink` for
   "Hear locally + stream", then promotes default sink to the combined sink.

Boot ordering that makes it safe: WP brings up the physical sink fallback first,
then the service upgrades the default to the combined sink later. If anything
fails, audio still lands on a real device (never silence).

## Always-on at boot checklist

- `systemctl --user is-enabled audio-sharing-setup.service` -> enabled
- drop-in file exists under pipewire.conf.d
- WP default-nodes file has no virtual-only fallbacks
- `pactl get-default-sink` -> combined/real (NOT a bare null sink)

## Boot-behavior verification (the "did it actually survive reboot" test)

```
systemctl --user restart wireplumber pipewire pipewire-pulse
sleep 5
pactl get-default-sink   # should be physical (proves safe fallback)
systemctl --user restart audio-sharing-setup.service
sleep 2
pactl get-default-sink   # should now be the combined sink
```

See Verify script below for the functional (not config) end-to-end test.