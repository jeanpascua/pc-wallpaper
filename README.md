# pc-wallpaper

Live hacker-terminal-themed desktop wallpaper. Renders real-time CPU/GPU/RAM/storage stats to a PNG and sets it as your actual desktop wallpaper (~1s refresh), with color-coded thresholds (green/amber/red) so you can read system health at a glance.

## Compatibility (limited — read before installing)

This is a personal project built for a couple specific machines and is **not** broadly portable yet.

| Component | Supported | Not supported |
|---|---|---|
| CPU | AMD (`k10temp`) or Intel (`coretemp`) | anything without a Linux hwmon driver |
| GPU | NVIDIA (`nvidia-smi`) | AMD — detected but raises `NotImplementedError` (untested, no hardware to verify against) |
| Desktop | GNOME (Wayland or X11, via `gsettings`), KDE Plasma (via `plasma-apply-wallpaperimage`) | XFCE/other — raises `NotImplementedError` |
| OS | Linux only | Windows, macOS, Steam Deck |

If your hardware doesn't match, the script will fail loudly with a clear error rather than silently doing the wrong thing.

## Requirements

- Python 3
- `psutil`, `Pillow`, `PyGObject`
- `fontconfig` (for `fc-match`) with a monospace font installed
- `nvidia-smi` on PATH (NVIDIA GPU)

## Install

```bash
git clone https://github.com/jeanpascua/pc-wallpaper.git
cd pc-wallpaper
pip install psutil Pillow PyGObject

cp systemd/pc-wallpaper.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now pc-wallpaper.service
```

## How it works

- `sensors.py` — reads hardware stats from `/sys/class/hwmon` (looked up by chip name, not fixed index) and `nvidia-smi`
- `render.py` — draws the stats onto a PNG (PIL), monochrome-green terminal aesthetic
- `main.py` — persistent loop: collect stats → render → set as wallpaper via `gsettings` (GNOME) or `plasma-apply-wallpaperimage` (KDE), once per second

Runs as a systemd user service so it survives login/logout and restarts on failure.
