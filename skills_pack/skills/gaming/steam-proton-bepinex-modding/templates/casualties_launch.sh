#!/usr/bin/env bash
# Steam/Proton + BepInEx multiplayer-mod launcher wrapper.
#
# WHY a wrapper instead of `sh -c '...%command%...'`:
# Steam substitutes %command% in-place with NO quoting. Under Snap Steam, %command%
# expands to a path that contains a space, e.g. ".../Proton - Experimental/proton ...".
# Steam wraps that spaced path in single quotes, which collide with the single quotes
# of `sh -c '...'`, so bash mis-parses the line and the game SILENTLY never launches
# (no error, just nothing happens). Receiving %command% as "$@" preserves the spaces.
#
# Set the game's Steam Launch Options to:
#   /home/<you>/casualties_launch.sh %command% -screen-fullscreen 1 -screen-width 2560 -screen-height 1080
#
# Then edit the three values below to force a different monitor / resolution.
MONITOR="DisplayPort-0"   # from `xrandr --current`
WIDTH=2560
HEIGHT=1080

# Force the chosen monitor to xrandr-primary so fullscreen lands there.
# (A monitor can be the DE's "primary" yet lack the xrandr primary flag — always set it.)
xrandr --output "$MONITOR" --primary 2>/dev/null || true

# Pass the real game command through, with BepInEx's winhttp.dll override applied.
exec env WINEDLLOVERRIDES="winhttp=n,b" "$@"
