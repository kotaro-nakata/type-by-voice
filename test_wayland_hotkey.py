import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from evdev import ecodes
from pynput import keyboard

from wayland_hotkey import WaylandHotkeyListener


class WaylandHotkeyTests(unittest.TestCase):
    def test_dispatches_press_and_release(self):
        pressed = Mock()
        released = Mock()
        listener = WaylandHotkeyListener(pressed, released, devices=[])
        listener._dispatch(SimpleNamespace(
            type=ecodes.EV_KEY, code=ecodes.KEY_LEFTMETA, value=1))
        listener._dispatch(SimpleNamespace(
            type=ecodes.EV_KEY, code=ecodes.KEY_LEFTMETA, value=0))
        pressed.assert_called_once_with(keyboard.Key.cmd_l)
        released.assert_called_once_with(keyboard.Key.cmd_l)

    def test_ignores_repeat_and_unrelated_keys(self):
        pressed = Mock()
        listener = WaylandHotkeyListener(pressed, Mock(), devices=[])
        listener._dispatch(SimpleNamespace(
            type=ecodes.EV_KEY, code=ecodes.KEY_LEFTALT, value=2))
        listener._dispatch(SimpleNamespace(
            type=ecodes.EV_KEY, code=ecodes.KEY_A, value=1))
        pressed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
