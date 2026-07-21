#!/usr/bin/env python3
"""voice-term tray indicator (runs under the *system* python3).

A small, colour-coded status icon in the GNOME top-bar indicator area (where
Telegram / mozc / Wi-Fi live). The artwork (white mic on a coloured badge,
sonar ripples while recording) lives in icon_art.py, shared with the Windows
tray (tray_win.py). Colour and motion convey the state:

    loading        grey
    idle / ready   green  (running, waiting for the hotkey)
    recording      red with sonar ripples that pulse to your voice
    transcribing   yellow (processing)

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
import subprocess
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

# icon_art sits next to this script; sys.path[0] is the script dir, so this
# works even though we run under the *system* python, outside the venv.
from icon_art import (COLORS, RIPPLE_MIN, RIPPLE_MAX,  # noqa: E402
                      make_static_image, make_recording_image)

FPS_MS = 60                  # ~16 fps

# Human-readable, colour-matched labels for the status menu item.
STATE_LABELS = {
    "loading": "読込中 (grey)",
    "idle": "待機中 (green)",
    "recording": "録音中 (red)",
    "transcribing": "処理中 (yellow)",
    "input-error": "ホットキーエラー (purple)",
    "audio-error": "マイクエラー (purple)",
    "model-error": "モデルエラー (purple)",
}


def _log_path():
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.join(
        os.path.expanduser("~"), ".cache")
    return os.path.join(cache, "voice-term.log")


def _config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(base, "voice-term", "config.toml")


def _open(path):
    """Open a file in the user's default app (best-effort)."""
    try:
        subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


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
            make_static_image(col).save(os.path.join(icon_dir, base + ".png"))
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

        # Live status line (updated each tick) — at a glance, what the app is
        # doing right now. Insensitive so it reads as a label, not a button.
        self.status_item = Gtk.MenuItem(label="状態: 読込中")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Diagnostics: when something looks wrong, open the log or the config.
        log_item = Gtk.MenuItem(label="ログを開く (Open log)")
        log_item.connect("activate", lambda *_: _open(_log_path()))
        menu.append(log_item)

        cfg_item = Gtk.MenuItem(label="設定を開く (Open config)")
        cfg_item.connect("activate", lambda *_: _open(_config_path()))
        menu.append(cfg_item)

        menu.append(Gtk.SeparatorMenuItem())

        quit_item = Gtk.MenuItem(label="終了 (Quit)")
        quit_item.connect("activate", self._quit)
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _update_status_label(self):
        label = STATE_LABELS.get(self.state, self.state)
        self.status_item.set_label(f"状態: {label}")

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
        make_recording_image(lvl, self.ripples).save(
            os.path.join(self.icon_dir, base + ".png"))
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

        prev = self.state
        self._read_state()
        if self.state != prev:
            self._update_status_label()
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
