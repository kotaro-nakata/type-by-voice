"""Platform abstraction layer for voice-term.

Everything OS-specific lives here so voice_term.py never needs to check
sys.platform itself. Linux keeps the existing behaviour (X11/Wayland tools,
notify-send, fcntl lock, CUDA .so preload); Windows gets equivalents built on
pyperclip / pynput / msvcrt / os.add_dll_directory.
"""
from __future__ import annotations

import os
import sys
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

APP_NAME = "voice-term"


# --------------------------------------------------------------------------- #
# Directories
# --------------------------------------------------------------------------- #
def runtime_dir() -> Path:
    """Per-session scratch dir for the state file, lock and tray icons."""
    if IS_WINDOWS:
        base = Path(tempfile.gettempdir())
    else:
        base = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_dir() -> Path:
    """Where config.toml lives (created by the caller on demand)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / APP_NAME


def log_path() -> Path:
    """Where the launcher writes the app log (tray "Open log" target)."""
    if IS_WINDOWS:
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / APP_NAME / "voice-term.log"
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return cache / "voice-term.log"


# --------------------------------------------------------------------------- #
# Notifications / opening files
# --------------------------------------------------------------------------- #
_HAS_NOTIFY = IS_LINUX and shutil.which("notify-send") is not None


def notify(summary: str, body: str = "", timeout_ms: int = 1500):
    """Best-effort desktop toast so feedback shows even without a terminal.

    Windows: console-only for now (the tray icon already conveys the state);
    a toast library can be added later without touching callers.
    """
    if _HAS_NOTIFY:
        try:
            subprocess.run(
                ["notify-send", "-a", APP_NAME, "-t", str(timeout_ms), summary, body],
                check=False,
            )
        except Exception:
            pass


def open_path(path):
    """Open a file in the user's default app (best-effort)."""
    try:
        if IS_WINDOWS:
            os.startfile(str(path))  # noqa: attribute exists on Windows only
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Single-instance lock
# --------------------------------------------------------------------------- #
def acquire_single_instance():
    """Prevent a second instance (double listeners -> double paste).

    Returns an open file handle to keep for the process lifetime, or None if
    another instance already holds the lock.
    """
    lock_path = runtime_dir() / "voice-term.lock"
    fh = open(lock_path, "w")
    try:
        if IS_WINDOWS:
            import msvcrt

            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


# --------------------------------------------------------------------------- #
# GPU runtime libraries
# --------------------------------------------------------------------------- #
def preload_accel_libs():
    """Make the pip-installed CUDA/cuDNN runtime findable by ctranslate2.

    Best-effort on both platforms; on CPU-only boxes the nvidia packages are
    absent and this simply does nothing.
    """
    if IS_WINDOWS:
        _add_windows_dll_dirs()
    elif IS_LINUX:
        _preload_linux_cuda_libs()


def _nvidia_package_root():
    import importlib.util

    spec = importlib.util.find_spec("nvidia")
    if not spec or not spec.submodule_search_locations:
        return None
    return list(spec.submodule_search_locations)[0]


def _preload_linux_cuda_libs():
    """Load the CUDA/cuDNN .so files into the process directly.

    ctranslate2 dlopen()s libs like libcublas.so.12 / libcudnn*.so.9 by SONAME.
    Preloading them with RTLD_GLOBAL makes those symbols resolvable no matter
    what LD_LIBRARY_PATH is — robust against polluted shell environments
    (e.g. ROS) or launchers that don't export the path.
    """
    import ctypes
    import glob

    base = _nvidia_package_root()
    if not base:
        return
    # Order matters (cublasLt before cublas); cuDNN libs cross-depend, so we
    # retry a couple of passes to satisfy load ordering.
    patterns = [
        "cublas/lib/libcublasLt.so*",
        "cublas/lib/libcublas.so*",
        "cuda_nvrtc/lib/libnvrtc*.so*",
        "cudnn/lib/libcudnn_*.so*",
        "cudnn/lib/libcudnn.so*",
    ]
    paths = []
    for pat in patterns:
        paths.extend(sorted(glob.glob(os.path.join(base, pat))))
    pending = list(dict.fromkeys(paths))  # de-dupe, keep order
    for _ in range(3):
        if not pending:
            break
        still = []
        for p in pending:
            try:
                ctypes.CDLL(p, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                still.append(p)
        pending = still


def _add_windows_dll_dirs():
    """Register the nvidia pip packages' DLL folders with the loader.

    On Windows the runtime ships .dll files under <pkg>/bin (or lib).
    os.add_dll_directory() だけでは不十分: ctranslate2 は実行時に素の
    LoadLibrary("cublas64_12.dll") で解決するため PATH しか見ない。
    そのため PATH の先頭にも同じディレクトリを積む。
    """
    base = _nvidia_package_root()
    if not base:
        return
    found = []
    for sub in ("cublas", "cudnn", "cuda_nvrtc"):
        for leaf in ("bin", "lib"):
            d = os.path.join(base, sub, leaf)
            if os.path.isdir(d):
                found.append(d)
                try:
                    os.add_dll_directory(d)
                except OSError:
                    pass
    if found:
        os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")


def cuda_available() -> bool:
    try:
        from ctranslate2 import get_cuda_device_count

        return get_cuda_device_count() > 0
    except Exception:
        return shutil.which("nvidia-smi") is not None


# --------------------------------------------------------------------------- #
# Text injection (sending text to the focused window)
# --------------------------------------------------------------------------- #
class TextInjector:
    """Sends text to the focused window.

    method: "paste"     = copy to clipboard then send Ctrl+V
            "type"      = type characters directly
            "clipboard" = copy to clipboard only, user pastes manually
    """

    def __init__(self, method: str, trailing_space: bool):
        self.method = method
        self.trailing_space = trailing_space

    def warn_if_missing(self):
        pass

    def send(self, text: str):
        raise NotImplementedError


class LinuxInjector(TextInjector):
    """Drives the external X11/Wayland tools (xclip/xdotool/wl-copy/wtype/...)."""

    def __init__(self, method: str, trailing_space: bool):
        super().__init__(method, trailing_space)
        self.session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        self._detect()

    def _detect(self):
        self.copy_cmd = None
        self.paste_cmd = None
        self.type_cmd = None

        if self.session == "wayland":
            if shutil.which("wl-copy"):
                self.copy_cmd = ["wl-copy"]
            if shutil.which("wtype"):
                self.paste_cmd = ["wtype", "-M", "ctrl", "v", "-m", "ctrl"]
                self.type_cmd = ["wtype", "-"]
            elif shutil.which("ydotool"):
                self.paste_cmd = ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"]
                self.type_cmd = ["ydotool", "type", "--file", "-"]
        else:  # x11 (default)
            if shutil.which("xclip"):
                self.copy_cmd = ["xclip", "-selection", "clipboard"]
            elif shutil.which("xsel"):
                self.copy_cmd = ["xsel", "--clipboard", "--input"]
            if shutil.which("xdotool"):
                self.paste_cmd = ["xdotool", "key", "--clearmodifiers", "ctrl+v"]
                self.type_cmd = ["xdotool", "type", "--clearmodifiers", "--file", "-"]

    def _copy(self, text: str) -> bool:
        if not self.copy_cmd:
            return False
        try:
            subprocess.run(self.copy_cmd, input=text.encode("utf-8"), check=True)
            return True
        except subprocess.SubprocessError:
            return False

    def warn_if_missing(self):
        if self.method in ("paste", "clipboard") and not self.copy_cmd:
            tool = "wl-copy" if self.session == "wayland" else "xclip"
            print(f"[warn] No clipboard tool found. Install {tool}.")
        if self.method == "paste" and not self.paste_cmd:
            tool = "wtype/ydotool" if self.session == "wayland" else "xdotool"
            print(f"[warn] No paste tool found. Install {tool}.")
        if self.method == "type" and not self.type_cmd:
            tool = "wtype/ydotool" if self.session == "wayland" else "xdotool"
            print(f"[warn] No typing tool found. Install {tool}.")

    def send(self, text: str):
        if not text:
            return
        if self.trailing_space:
            text = text + " "

        if self.method == "type" and self.type_cmd:
            try:
                subprocess.run(self.type_cmd, input=text.encode("utf-8"), check=True)
                return
            except subprocess.SubprocessError as e:
                print(f"[warn] type failed ({e}); falling back to clipboard.")

        # paste / clipboard (and type-fallback)
        if not self._copy(text):
            print("[error] Could not copy to clipboard; printing instead:")
            print(text)
            return
        if self.method == "clipboard":
            print("[output] Copied to clipboard (paste with Ctrl+V).")
            return
        # Give the held hotkey a moment to fully release before pasting.
        time.sleep(0.05)
        if self.paste_cmd:
            try:
                subprocess.run(self.paste_cmd, check=True)
            except subprocess.SubprocessError as e:
                print(f"[warn] paste failed ({e}); text is on the clipboard.")
        else:
            print("[output] Copied to clipboard (no paste tool; Ctrl+V manually).")


class WindowsInjector(TextInjector):
    """Clipboard via pyperclip, paste via a synthesized Ctrl+V (pynput).

    No external tools needed: everything happens in-process. "paste" is the
    reliable path for Japanese/Unicode; "type" uses Controller.type() which
    can drop characters with some IME states, so paste stays the default.
    """

    def __init__(self, method: str, trailing_space: bool):
        super().__init__(method, trailing_space)
        try:
            import pyperclip

            self._pyperclip = pyperclip
        except ImportError:
            self._pyperclip = None
        from pynput.keyboard import Controller, Key

        self._kbd = Controller()
        self._Key = Key

    def warn_if_missing(self):
        if self.method in ("paste", "clipboard") and self._pyperclip is None:
            print("[warn] pyperclip is not installed; run `pip install pyperclip`.")

    def _release_modifiers(self):
        """Release any lingering modifiers so Ctrl+V doesn't become e.g. Ctrl+Alt+V."""
        K = self._Key
        for k in (K.alt, K.alt_l, K.alt_r, K.alt_gr,
                  K.cmd, K.cmd_l, K.cmd_r,
                  K.shift, K.shift_l, K.shift_r,
                  K.ctrl, K.ctrl_l, K.ctrl_r):
            try:
                self._kbd.release(k)
            except Exception:
                pass

    def _copy(self, text: str) -> bool:
        if self._pyperclip is None:
            return False
        try:
            self._pyperclip.copy(text)
            return True
        except Exception:
            return False

    def send(self, text: str):
        if not text:
            return
        if self.trailing_space:
            text = text + " "

        if self.method == "type":
            try:
                self._kbd.type(text)
                return
            except Exception as e:
                print(f"[warn] type failed ({e}); falling back to clipboard.")

        if not self._copy(text):
            print("[error] Could not copy to clipboard; printing instead:")
            print(text)
            return
        if self.method == "clipboard":
            print("[output] Copied to clipboard (paste with Ctrl+V).")
            return
        # Give the held hotkey a moment to fully release before pasting.
        time.sleep(0.15)
        self._release_modifiers()
        try:
            with self._kbd.pressed(self._Key.ctrl):
                self._kbd.press("v")
                self._kbd.release("v")
        except Exception as e:
            print(f"[warn] paste failed ({e}); text is on the clipboard.")


def make_injector(method: str, trailing_space: bool) -> TextInjector:
    if IS_WINDOWS:
        return WindowsInjector(method, trailing_space)
    return LinuxInjector(method, trailing_space)
