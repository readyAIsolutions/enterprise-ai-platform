# X visibility diagnostic + launch recipe (Hermes container -> host display)

## 1. Prove the container can reach the host X server
Run these; if `xdpyinfo` prints the display name, X IS reachable and you CAN
paint windows. Do this BEFORE telling the user "the container can't show windows".

```bash
echo "DISPLAY=$DISPLAY  XAUTHORITY=*** -la /tmp/.X11-unix/            # expect: srwxrwxrwx ... X0
xauth list                        # expect: MIT-MAGIC-COOKIE-1 <hex>
xdpyinfo 2>&1 | head -3           # expect: "name of display:    :0.0"
which xterm uxterm                # xterm is the direct-X client we want
```

Expected good output (this box):
```
DISPLAY=:0.0 XAUTHORITY=/run/u...nix:  MIT-MAGIC-COOKIE-1  18f2...
name of display:    :0.0
version number:    11.0
/usr/bin/xterm
/usr/bin/uxterm
```

## 2. Launch a visible B&W xterm (via terminal(background=true))
```bash
xterm -bg black -fg white -geometry 95x30+5+56 \
  -T "TITLE" -hold -e bash -c 'cd <dir> && <cmd>; echo DONE; exec bash'
```
- `-bg black -fg white` => black & white terminal.
- `-hold` keeps the window open after the command; `exec bash` drops to a shell.
- Geometry is absolute X-screen coords. Left monitor x=0; primary middle
  ultrawide x=1920. A 2x2 grid: +5+56, +765+56, +5+499, +765+499.

## 3. VERIFY the windows actually mapped (reliable method)
`xdotool search --class XTerm` returns 0 even when windows ARE mapped — do NOT
trust it. Use `xwininfo -root -tree` and grep the titles:
```bash
xwininfo -root -tree 2>&1 | grep -iE "GPU|LUMEN|DEMIURGE|xterm"
```
Confirmed mapped example from this session (4 windows, 2x2):
```
0x540000e "DEMIURGE-3D :: estimator": ("xterm" "XTerm")  +765+499
0x520000e "DEMIURGE :: stock bot build": ("xterm")        +5+499
0x4c0000e "LUMEN :: wallpaper engine": ("xterm")          +765+56
0x4a0000e "GPU TUNE :: sudo on host": ("xterm")           +5+56
```

## 4. Why gnome-terminal fails (and xterm works)
gnome-terminal is a D-Bus client: it sends an activation request to a running
`gnome-terminal-server`. From the sandbox there is no reachable server, so the
parent exits 0 with NO window. xterm links libX11 directly and talks to the X
socket itself — no D-Bus, no server needed. Use xterm for any visible terminal
you launch from the container.

## 5. Fallback (only if user wants the gnome-terminal saved profile)
Write `~/Desktop/launch_*.sh` for the HOST and tell the user to run it from a
real host terminal:
```bash
#!/usr/bin/env bash
BW=b1dcc9dd-5262-4d8d-a863-c897e6d979b9   # #000 bg / #fff fg
gnome-terminal --profile=$BW --title="NAME" -- bash -c 'cd <dir> && <cmd>; exec bash' &
wait
```
The container cannot do this itself — it is purely a hand-off script.
