# XFCE/nemo desktop-ownership fix — verified session transcript
Date: 2026-07-11 (session: Lumen hijack + icons-vanish-5x)

## Symptom
Desktop icons/folders gone after reboot (user reported 5x). Also Lumen had to be
disabled from startup (it hijacked the PC on boot).

## Diagnosis output (real)
```
$ echo "DISPLAY=$DISPLAY"        -> :0.0   (host X reachable from agent sandbox)
$ pgrep -a xfdesktop             -> 9385 xfdesktop        <-- STEALING the desktop
$ gsettings get org.nemo.desktop ignored-desktop-handlers
                                  -> ['conky', 'csd-background']   <-- NO xfdesktop
$ gsettings get org.nemo.desktop show-desktop-icons      -> true
$ nemo-desktop (foreground test)
  (nemo-desktop:...): Nemo-WARNING **: Desktop already managed by another application,
  skipping desktop setup. To change this, modify org.nemo.desktop 'ignored-desktop-handlers'.
  -> process exited, no icons
```

## Applied fix (all three)
```
gsettings set org.nemo.desktop ignored-desktop-handlers "['conky','csd-background','xfdesktop']"
xfconf-query -c xfce4-desktop -p /desktop-icons/style -s 0
# ~/.config/autostart/xfdesktop.desktop  -> Hidden=true
pkill -x xfdesktop
# ~/.config/autostart/nemo-desktop.desktop -> Exec=nemo-desktop,
#   AutostartCondition=GSettings org.nemo.desktop show-desktop-icons, NO OnlyShowIn
```

## Result (real)
```
$ pgrep -a xfdesktop      -> still KILLED (good)
$ pgrep -a nemo-desktop   -> 24389 nemo-desktop   (running)
$ xdotool search --class nemo | wc -l  -> 5
$ xprop desktop windows  -> 4 DESKTOP windows (one per monitor)
```
Icons appeared across all 4 monitors.

## Platform gotcha
`setsid nemo-desktop >/tmp/x.log 2>&1 &` is REJECTED by Hermes ("shell-level
background wrappers ... use terminal(background=true)"). Launch GUI apps that must
persist with terminal(background=true), not `&`/nohup/setsid/disown. Also note the
agent sandbox reaches the host X display (DISPLAY=:0) so GUI launches actually
render on the user's screens.
