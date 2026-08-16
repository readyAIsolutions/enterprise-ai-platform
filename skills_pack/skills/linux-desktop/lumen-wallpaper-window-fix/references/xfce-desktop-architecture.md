# XFCE desktop architecture on LO's box (reference)

## Diagnosis recipe (run on the host, DISPLAY=:0)
- Which desktop manager owns icons: `pgrep -a xfdesktop`, `pgrep -a nemo-desktop`
- Why nemo won't draw: `nemo-desktop` logs
  "Desktop already managed by another application, skipping desktop setup"
  when xfdesktop is present AND not in ignored-desktop-handlers.
- Workspace check: `xdotool get_num_desktops`; per-window ws:
  `xprop -id $WID _NET_WM_DESKTOP`; nemo desktop windows are type
  `_NET_WM_WINDOW_TYPE_DESKTOP` and report sticky (4294967295) — that is NORMAL,
  not a bug.
- nemo bg capability: `gsettings list-keys org.nemo.desktop` -> only
  `background-fade` (no `picture-uri`/`background-color`). `dconf dump /org/nemo/desktop/`
  confirms no picture-uri. nemo version: `nemo --version` (6.4.5 here).
- xfdesktop style meaning: `xfconf-query -c xfce4-desktop -p /desktop-icons/style`
  (0=none, 1=minimized, 2=FM[older], 3=FM-mode on this build).

## Verified-good state (this run, 2026-07-11)
xfdesktop RUNNING, nemo-desktop RUNNING, gtk-theme Greybird-dark,
desktop-icons/style=3, ignored-desktop-handlers includes xfdesktop,
~/.config/autostart/nemo-desktop.desktop present (NO OnlyShowIn),
NO ~/.config/autostart/xfdesktop.desktop override, lumen autostart ABSENT.

## Fix commands (icons persistent + workspaces + dark desktop)
```
gsettings set org.nemo.desktop ignored-desktop-handlers "['conky','csd-background','xfdesktop']"
xfconf-query -c xfce4-desktop -p /desktop-icons/style -s 3
# ~/.config/autostart/nemo-desktop.desktop:
#   [Desktop Entry]
#   Type=Application
#   Name=Nemo Desktop
#   Exec=nemo-desktop
#   AutostartCondition=GSettings org.nemo.desktop show-desktop-icons
#   X-GNOME-Autostart-Phase=Desktop
#   X-GNOME-Autostart-Delay=2
#   X-GNOME-AutoRestart=true
#   NoDisplay=true
gsettings set org.nemo.desktop show-desktop-icons true
# dark theme (fixes nemo's ugly light bg):
gsettings set org.gnome.desktop.interface gtk-theme 'Greybird-dark'
xfconf-query -c xfwm4 -p /general/theme --create -s 'Greybird-dark'
pkill -x nemo-desktop; nemo-desktop &
```

## What BROKE it (avoid)
- Killing xfdesktop / `style=0` / `Hidden=true` xfdesktop autostart -> workspaces
  misbehave (terms appear to jump workspaces). xfdesktop owns workspaces; keep it.
- `OnlyShowIn=XFCE;` in nemo-desktop.desktop -> silently skipped if session string
  differs -> icons vanish after reboot.
- Trying to set nemo wallpaper via `picture-uri` -> key absent on 6.4.5, no-op.
