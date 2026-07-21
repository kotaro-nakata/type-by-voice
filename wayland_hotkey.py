"""Native Linux hotkey listener for Wayland sessions."""
from __future__ import annotations

import select
import threading

from evdev import InputDevice, ecodes, list_devices
from pynput import keyboard

CODE_TO_KEY = {
    ecodes.KEY_LEFTMETA: keyboard.Key.cmd_l,
    ecodes.KEY_RIGHTMETA: keyboard.Key.cmd_r,
    ecodes.KEY_LEFTALT: keyboard.Key.alt_l,
    ecodes.KEY_RIGHTALT: keyboard.Key.alt_r,
    ecodes.KEY_LEFTCTRL: keyboard.Key.ctrl_l,
    ecodes.KEY_RIGHTCTRL: keyboard.Key.ctrl_r,
    ecodes.KEY_LEFTSHIFT: keyboard.Key.shift_l,
    ecodes.KEY_RIGHTSHIFT: keyboard.Key.shift_r,
}


class WaylandHotkeyListener:
    """Observe hotkey events without grabbing the keyboard."""

    def __init__(self, on_press, on_release, devices=None):
        self._on_press = on_press
        self._on_release = on_release
        self._provided_devices = devices
        self._devices = []
        self._stop = threading.Event()

    def start(self):
        self._devices = list(self._provided_devices or self._find_keyboards())
        if not self._devices:
            raise PermissionError(
                "読み取り可能なキーボードがありません。"
                "ユーザーを input グループへ追加して再ログインしてください。"
            )
        names = ", ".join(device.name for device in self._devices)
        print(f"[input] Wayland native hotkey listener: {names}")
        threading.Thread(target=self._run, daemon=True).start()

    @staticmethod
    def _find_keyboards():
        for path in list_devices():
            try:
                device = InputDevice(path)
                keys = set(device.capabilities().get(ecodes.EV_KEY, []))
                has_meta = bool(keys & {ecodes.KEY_LEFTMETA, ecodes.KEY_RIGHTMETA})
                has_alt = bool(keys & {ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT})
                if has_meta and has_alt:
                    yield device
                else:
                    device.close()
            except (PermissionError, OSError):
                continue

    def _run(self):
        while not self._stop.is_set():
            try:
                readable, _, _ = select.select(self._devices, [], [], 0.2)
                for device in readable:
                    for event in device.read():
                        self._dispatch(event)
            except OSError as exc:
                if not self._stop.is_set():
                    print(f"[error] Keyboard device disconnected: {exc}")
                return

    def _dispatch(self, event):
        if event.type != ecodes.EV_KEY or event.value == 2:
            return
        key = CODE_TO_KEY.get(event.code)
        if key is None:
            return
        if event.value == 1:
            self._on_press(key)
        elif event.value == 0:
            self._on_release(key)

    def stop(self):
        self._stop.set()
        for device in self._devices:
            try:
                device.close()
            except OSError:
                pass
        self._devices.clear()
