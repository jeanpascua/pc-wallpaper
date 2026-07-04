#!/usr/bin/env python3
"""Entry point: persistent loop — gather stats, render wallpaper, apply it."""

import os
import subprocess
import time

from sensors import collect_all, get_resolution
from render import render, OUT_PATH

INTERVAL = 1.0


def is_overview_active() -> bool:
    """GNOME's Activities overview reblurs the background whenever the wallpaper
    file changes on disk — pausing writes while it's open avoids a visible flicker."""
    result = subprocess.run(
        ["busctl", "--user", "get-property", "org.gnome.Shell", "/org/gnome/Shell",
         "org.gnome.Shell", "OverviewActive"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip() == "b true"


def detect_desktop_environment() -> str:
    return os.environ.get("XDG_CURRENT_DESKTOP", "").upper()


def set_wallpaper() -> None:
    desktop = detect_desktop_environment()
    if "GNOME" in desktop:
        _set_wallpaper_gnome()
    else:
        raise NotImplementedError(
            f"Desktop environment '{desktop or 'unknown'}' detected — only GNOME's wallpaper-set "
            "command (gsettings) is implemented/tested. KDE/XFCE/other DEs use different mechanisms "
            "(e.g. plasma-apply-wallpaperimage, xfconf-query) that haven't been verified here."
        )


def _set_wallpaper_gnome() -> None:
    uri = f"file://{OUT_PATH}"
    subprocess.run(
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
        check=True,
    )
    subprocess.run(
        ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri],
        check=True,
    )


def main() -> None:
    width, height = get_resolution()  # detected once, not every frame
    while True:
        start = time.monotonic()

        stats = collect_all()
        if not is_overview_active():
            render(stats, width, height)
            set_wallpaper()

        elapsed = time.monotonic() - start
        print(f"CPU {stats['cpu_temp']:.1f}C, GPU {stats['gpu']['temp']:.0f}C  ({elapsed:.2f}s/cycle)")
        time.sleep(max(0.0, INTERVAL - elapsed))


if __name__ == "__main__":
    main()
