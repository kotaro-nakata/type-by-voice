#!/usr/bin/env python3
"""voice-term tray indicator (runs under the *system* python3).

A small, colour-coded status icon in the GNOME top-bar indicator area (where
Telegram / mozc / Wi-Fi live). It carries no text — colour and motion convey the
state:

    loading       grey dot
    idle / ready   blue dot   (running, waiting for the hotkey)
    recording      green dot with sonar ripples that pulse to your voice
    transcribing   amber dot

It is deliberately decoupled from the main app (which lives in a venv with
faster-whisper): the main app writes "<state> [level]" to a small file; this
helper polls it and renders the icon. While recording, the second token is the
live mic level (0..1) and drives how fast / bright the ripples emanate.

Requires: PyGObject + AyatanaAppIndicator3 typelib + PIL — all present on Ubuntu
GNOME once `gir1.2-ayatanaappindicator3-0.1` is installed.
"""
import argparse
import os
import signal
import time

import gi

gi.require_version("Gtk", "3.0")
try:
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except (ValueError, ImportError):
    gi.require_version("AppIndicator3", "0.1")
    from gi.repository import AppIndicator3 as AppIndicator
from gi.repository import Gtk, GLib  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402


SIZE = 64
C = SIZE / 2                 # center
DOT_BASE = (108, 140, 255)   # idle blue
COLORS = {
    "loading": (150, 157, 170),
    "idle": (108, 140, 255),
    "transcribing": (251, 191, 36),
}
GREEN = (52, 211, 153)
RIPPLE_MIN = 9.0             # ripples start at the dot edge
RIPPLE_MAX = 30.0           # and fade out by here
FPS_MS = 60                  # ~16 fps


def _dot(draw, r, color, alpha=255):
    draw.ellipse([C - r, C - r, C + r, C + r], fill=color + (alpha,))


def make_static_icon(path, color):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # a calm, clearly-visible dot with a soft two-layer halo
    d.ellipse([C - 22, C - 22, C + 22, C + 22], fill=color + (45,))
    d.ellipse([C - 16, C - 16, C + 16, C + 16], fill=color + (85,))
    _dot(d, 13, color)
    img.save(path)


def make_recording_frame(path, level, ripples):
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # outermost (faintest) first, so inner rings paint over them
    for r in sorted(ripples, reverse=True):
        t = (r - RIPPLE_MIN) / (RIPPLE_MAX - RIPPLE_MIN)
        t = max(0.0, min(1.0, t))
        # Stay clearly visible even when you're quiet; brighten with the voice.
        alpha = int((1.0 - t) * (140 + 115 * level))
        if alpha <= 0:
            continue
        d.ellipse([C - r, C - r, C + r, C + r],
                  outline=GREEN + (alpha,), width=5)
    _dot(d, 8 + 3 * level, GREEN)
    img.save(path)


class Tray:
    def __init__(self, state_file, pid, icon_dir):
        self.state_file = state_file
        self.pid = pid
        self.icon_dir = icon_dir

        self.state = "loading"
        self.level = 0.0
        self.smooth = 0.0
        self.ripples = []          # active ring radii
        self.spawn_acc = 0.0
        self.last = time.monotonic()
        self.frame = 0
        self.shown_static = None

        # Pre-render the static state icons once.
        self.static_names = {}
        for name, col in COLORS.items():
            base = f"vt-{name}"
            make_static_icon(os.path.join(icon_dir, base + ".png"), col)
            self.static_names[name] = base

        self.ind = AppIndicator.Indicator.new_with_path(
            "voice-term",
            self.static_names["loading"],
            AppIndicator.IndicatorCategory.APPLICATION_STATUS,
            icon_dir,
        )
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_title("voice-term")
        self.ind.set_menu(self._menu())

        GLib.timeout_add(FPS_MS, self._tick)

    def _menu(self):
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label="終了 (Quit)")
        item.connect("activate", self._quit)
        menu.append(item)
        menu.show_all()
        return menu

    def _read_state(self):
        try:
            with open(self.state_file) as f:
                parts = f.read().split()
        except OSError:
            return
        if not parts:
            return
        self.state = parts[0]
        if len(parts) > 1:
            try:
                self.level = max(0.0, min(1.0, float(parts[1])))
            except ValueError:
                self.level = 0.0
        else:
            self.level = 0.0

    def _show_static(self, state):
        name = self.static_names.get(state, self.static_names["idle"])
        if self.shown_static == name:
            return
        self.shown_static = name
        self.ripples.clear()
        self.smooth = 0.0
        self.ind.set_icon_full(name, state)

    def _animate(self, dt):
        self.shown_static = None
        # ease the level so the ripples breathe instead of jitter
        self.smooth += (self.level - self.smooth) * min(1.0, dt * 12.0)
        lvl = self.smooth

        period = 0.8 - 0.58 * lvl          # louder -> rings more often
        self.spawn_acc += dt
        if self.spawn_acc >= period:
            self.spawn_acc = 0.0
            self.ripples.append(RIPPLE_MIN)

        speed = 26.0                        # px/sec outward
        self.ripples = [r + speed * dt for r in self.ripples if r < RIPPLE_MAX]

        self.frame = (self.frame + 1) % 8
        base = f"vt-rec{self.frame}"
        make_recording_frame(os.path.join(self.icon_dir, base + ".png"), lvl, self.ripples)
        self.ind.set_icon_full(base, "recording")

    def _tick(self):
        try:
            os.kill(self.pid, 0)
        except OSError:
            Gtk.main_quit()
            return False

        now = time.monotonic()
        dt = now - self.last
        self.last = now

        self._read_state()
        if self.state == "recording":
            self._animate(dt)
        else:
            self._show_static(self.state)
        return True

    def _quit(self, *_):
        try:
            os.kill(self.pid, signal.SIGTERM)
        except OSError:
            pass
        Gtk.main_quit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--pid", type=int, required=True)
    ap.add_argument("--icon-dir", required=True)
    args = ap.parse_args()

    Tray(args.state_file, args.pid, args.icon_dir)
    signal.signal(signal.SIGTERM, lambda *_: Gtk.main_quit())
    Gtk.main()


if __name__ == "__main__":
    main()
