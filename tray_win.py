"""voice-term tray icon for Windows (pystray, in-process).

The artwork (white mic on a coloured badge, sonar ripples while recording)
lives in icon_art.py, shared with the Linux GTK indicator (tray_indicator.py).

Unlike Linux — where the tray must run under the system python (GTK) in a
separate process — pystray works inside the venv, so this runs as a daemon
thread in the main app process. Quit calls App.shutdown() directly; no
signals involved.
"""
from __future__ import annotations

import threading
import time

from PIL import Image

import platform_backend as pb
from icon_art import (COLORS, RIPPLE_MIN, RIPPLE_MAX,
                      make_static_image, make_recording_image)


FRAME_S = 0.08               # ~12 fps while recording

STATE_LABELS = {
    "loading": "読込中",
    "idle": "待機中",
    "recording": "録音中",
    "transcribing": "処理中",
}


class WinTray:
    """Renders the app state as a tray icon. Reads the App object directly."""

    def __init__(self, app):
        self.app = app
        self._icon = None
        self._thread = None
        self._static = {name: make_static_image(col) for name, col in COLORS.items()}
        # animation state
        self.smooth = 0.0
        self.ripples: list[float] = []
        self.spawn_acc = 0.0
        self.last = time.monotonic()
        self._shown_state = None

    # --- lifecycle --- #
    def start(self):
        try:
            import pystray
        except ImportError:
            print("[info] Tray icon unavailable (pip install pystray to enable it).")
            return

        menu = pystray.Menu(
            pystray.MenuItem(self._status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("ログを開く (Open log)",
                             lambda: pb.open_path(pb.log_path())),
            pystray.MenuItem("設定を開く (Open config)",
                             lambda: pb.open_path(pb.config_dir() / "config.toml")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("終了 (Quit)", self._quit),
        )
        self._icon = pystray.Icon(
            "voice-term", self._static["loading"], "voice-term", menu)
        # The Win32 backend runs its message loop fine in a daemon thread, so
        # the app keeps owning the main thread (same layout as on Linux).
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        threading.Thread(target=self._pump, daemon=True).start()

    def stop(self):
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass

    def _quit(self):
        self.app.shutdown()   # in-process; no signals needed on Windows
        self.stop()

    # --- rendering --- #
    def _status_text(self, item=None) -> str:
        state = getattr(self.app, "_state", "loading")
        return f"状態: {STATE_LABELS.get(state, state)}"

    def _pump(self):
        """Poll the app state and redraw the icon; animate while recording."""
        while not self.app._stop.is_set():
            state = getattr(self.app, "_state", "loading")
            now = time.monotonic()
            dt = now - self.last
            self.last = now

            if self._icon is None:
                return
            try:
                if state == "recording":
                    level = min(1.0, self.app.recorder.level * 9.0)
                    self._icon.icon = self._animate(level, dt)
                    self._shown_state = None
                elif state != self._shown_state:
                    self._shown_state = state
                    self.ripples.clear()
                    self.smooth = 0.0
                    self._icon.icon = self._static.get(state, self._static["idle"])
                if state != getattr(self, "_menu_state", None):
                    self._menu_state = state
                    self._icon.update_menu()
            except Exception:
                pass
            time.sleep(FRAME_S if state == "recording" else 0.15)
        self.stop()

    def _animate(self, level, dt) -> Image.Image:
        # ease the level so the ripples breathe instead of jitter
        self.smooth += (level - self.smooth) * min(1.0, dt * 12.0)
        lvl = self.smooth

        period = 0.8 - 0.58 * lvl           # louder -> rings more often
        self.spawn_acc += dt
        if self.spawn_acc >= period:
            self.spawn_acc = 0.0
            self.ripples.append(RIPPLE_MIN)

        speed = 26.0                        # px/sec outward
        self.ripples = [r + speed * dt for r in self.ripples if r < RIPPLE_MAX]
        return make_recording_image(lvl, self.ripples)
