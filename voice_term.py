#!/usr/bin/env python3
"""voice-term: local push-to-talk voice input for the active window.

Records the microphone while a hotkey is held (push-to-talk) or toggled,
transcribes locally with faster-whisper, then sends the text to whatever
window has focus via the clipboard (paste) or direct typing.

Fully local, no API keys. See README.md for setup.
"""
from __future__ import annotations

import os
import sys
import shutil
import signal
import subprocess
import threading
import queue
import time
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

import numpy as np
import sounddevice as sd
from pynput import keyboard


CONFIG_PATH = Path.home() / ".config" / "voice-term" / "config.toml"

_HAS_NOTIFY = shutil.which("notify-send") is not None


def notify(summary: str, body: str = "", timeout_ms: int = 1500):
    """Best-effort desktop toast so feedback shows even without a terminal."""
    if not _HAS_NOTIFY:
        return
    try:
        subprocess.run(
            ["notify-send", "-a", "voice-term", "-t", str(timeout_ms), summary, body],
            check=False,
        )
    except Exception:
        pass

DEFAULT_CONFIG = """\
# voice-term configuration

[model]
# faster-whisper model. "large-v3-turbo" is fast + multilingual (good for ja).
# Other options: "large-v3", "medium", "small", or a local path.
name = "large-v3-turbo"
# "auto" -> CUDA if available else CPU. Or force "cuda" / "cpu".
device = "auto"
# "auto" -> float16 on GPU, int8 on CPU. Or "float16" / "int8" / "int8_float16".
compute_type = "auto"
# Transcription language. "ja" for Japanese, "en" for English, "auto" to detect.
language = "ja"

[hotkey]
# "ptt"   = hold key to record, release to transcribe (push-to-talk)
# "toggle"= press once to start, press again to stop
mode = "ptt"
# Hotkey: a single pynput key name, or a list to allow several.
# Examples: "ctrl_r", ["ctrl_r", "ctrl_l"], "f9", "scroll_lock", "pause".
# Ctrl keys rarely clash with app shortcuts (e.g. Slack), unlike Alt-based keys.
key = ["ctrl_r", "ctrl_l"]

[audio]
sample_rate = 16000
# Input device: name substring or numeric index. Empty = system default.
# Run `python voice_term.py --list-devices` to see options.
device = ""

[output]
# "paste"     = copy to clipboard then send Ctrl+V (fast, reliable for Japanese)
# "type"      = type characters directly (xdotool/wtype)
# "clipboard" = copy to clipboard only, you paste manually
method = "paste"
# Add a trailing space after inserted text.
trailing_space = false
"""


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(DEFAULT_CONFIG)
        print(f"[init] Created default config at {CONFIG_PATH}")
    with CONFIG_PATH.open("rb") as f:
        cfg = tomllib.load(f)
    # Fill defaults defensively in case the user removed keys.
    base = tomllib.loads(DEFAULT_CONFIG)
    for section, vals in base.items():
        cfg.setdefault(section, {})
        for k, v in vals.items():
            cfg[section].setdefault(k, v)
    return cfg


# --------------------------------------------------------------------------- #
# Output backends
# --------------------------------------------------------------------------- #
class Outputter:
    """Sends text to the focused window. Detects X11 vs Wayland tools."""

    def __init__(self, method: str, trailing_space: bool):
        self.method = method
        self.trailing_space = trailing_space
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


# --------------------------------------------------------------------------- #
# Audio recording
# --------------------------------------------------------------------------- #
class Recorder:
    def __init__(self, sample_rate: int, device):
        self.sample_rate = sample_rate
        self.device = device
        self._recording = threading.Event()
        self._buffer: list[np.ndarray] = []
        self._lock = threading.Lock()
        self.stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="float32",
            device=device if device not in ("", None) else None,
            callback=self._callback,
        )

    def _callback(self, indata, frames, time_info, status):
        if status:
            # Overflows are usually harmless; print sparingly.
            pass
        if self._recording.is_set():
            with self._lock:
                self._buffer.append(indata.copy())

    def start(self):
        self.stream.start()

    def begin(self):
        with self._lock:
            self._buffer.clear()
        self._recording.set()

    def end(self) -> np.ndarray:
        self._recording.clear()
        with self._lock:
            if not self._buffer:
                return np.zeros(0, dtype=np.float32)
            data = np.concatenate(self._buffer, axis=0).flatten()
            self._buffer.clear()
        return data

    def close(self):
        self._recording.clear()
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Hotkey parsing
# --------------------------------------------------------------------------- #
def parse_key(name: str):
    name = name.strip().lower()
    if hasattr(keyboard.Key, name):
        return getattr(keyboard.Key, name)
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    raise ValueError(
        f"Unknown hotkey '{name}'. Use a pynput Key name (e.g. alt_r, f9) "
        f"or a single character."
    )


def key_matches(key, target) -> bool:
    if key == target:
        return True
    # Match KeyCode by char regardless of modifiers.
    if isinstance(target, keyboard.KeyCode) and isinstance(key, keyboard.KeyCode):
        return key.char == target.char
    return False


def parse_keys(value) -> list:
    """Parse the config hotkey, which may be a single key or a list of keys."""
    names = value if isinstance(value, (list, tuple)) else [value]
    return [parse_key(n) for n in names]


def key_matches_any(key, targets) -> bool:
    return any(key_matches(key, t) for t in targets)


# --------------------------------------------------------------------------- #
# Main app
# --------------------------------------------------------------------------- #
class App:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.language = cfg["model"]["language"]
        if self.language.lower() == "auto":
            self.language = None

        self.outputter = Outputter(cfg["output"]["method"], cfg["output"]["trailing_space"])
        self.outputter.warn_if_missing()

        device_cfg = cfg["audio"]["device"]
        device = device_cfg
        if isinstance(device_cfg, str) and device_cfg.isdigit():
            device = int(device_cfg)
        self.recorder = Recorder(cfg["audio"]["sample_rate"], device)

        self.target_keys = parse_keys(cfg["hotkey"]["key"])
        self.mode = cfg["hotkey"]["mode"].lower()
        self._active = False  # currently recording
        self._jobs: queue.Queue = queue.Queue()
        self._stop = threading.Event()

        self.model = self._load_model()

    def _load_model(self):
        _preload_cuda_libs()
        from faster_whisper import WhisperModel

        name = self.cfg["model"]["name"]
        device = self.cfg["model"]["device"].lower()
        compute_type = self.cfg["model"]["compute_type"].lower()

        if device == "auto":
            device = "cuda" if _cuda_available() else "cpu"
        if compute_type == "auto":
            compute_type = "float16" if device == "cuda" else "int8"

        print(f"[model] Loading '{name}' on {device} ({compute_type}).")
        print("[model] First run downloads the model; this can take a while...")
        try:
            model = WhisperModel(name, device=device, compute_type=compute_type)
        except Exception as e:
            if device == "cuda":
                print(f"[warn] CUDA load failed ({e}); falling back to CPU/int8.")
                model = WhisperModel(name, device="cpu", compute_type="int8")
            else:
                raise
        print("[model] Ready.")
        return model

    # --- recording lifecycle --- #
    def _start_recording(self):
        if self._active:
            return
        self._active = True
        self.recorder.begin()
        print("\n[●] Recording... (release to transcribe)" if self.mode == "ptt"
              else "\n[●] Recording... (press again to stop)")
        notify("🎤 録音中...", "話してください", timeout_ms=600)

    def _stop_recording(self):
        if not self._active:
            return
        self._active = False
        audio = self.recorder.end()
        dur = len(audio) / self.recorder.sample_rate
        if dur < 0.3:
            print("[..] Too short, ignored.")
            return
        print(f"[…] Transcribing {dur:.1f}s ...")
        notify("⏳ 変換中...", f"{dur:.1f}秒の音声", timeout_ms=1000)
        self._jobs.put(audio)

    # --- transcription worker --- #
    def _worker(self):
        while not self._stop.is_set():
            try:
                audio = self._jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                segments, info = self.model.transcribe(
                    audio,
                    language=self.language,
                    beam_size=5,
                    vad_filter=True,
                )
                text = "".join(seg.text for seg in segments).strip()
            except Exception as e:
                print(f"[error] Transcription failed: {e}")
                notify("❌ 変換失敗", str(e)[:120])
                continue
            if text:
                print(f"[✓] {text}")
                notify("✓ 入力しました", text[:120])
                self.outputter.send(text)
            else:
                print("[..] (no speech detected)")
                notify("…無音でした", "", timeout_ms=800)

    # --- key handlers --- #
    def _on_press(self, key):
        if not key_matches_any(key, self.target_keys):
            return
        if self.mode == "ptt":
            self._start_recording()
        else:  # toggle
            if self._active:
                self._stop_recording()
            else:
                self._start_recording()

    def _on_release(self, key):
        if self.mode == "ptt" and key_matches_any(key, self.target_keys):
            self._stop_recording()

    def run(self):
        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()
        self.recorder.start()

        mode_desc = "hold" if self.mode == "ptt" else "toggle"
        keys = self.cfg["hotkey"]["key"]
        keys_str = " or ".join(keys) if isinstance(keys, (list, tuple)) else str(keys)
        print(f"[ready] {mode_desc.capitalize()} '{keys_str}' to dictate. "
              f"Ctrl+C to quit.")

        listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        listener.start()
        try:
            while not self._stop.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            print("\n[exit] Shutting down...")
            self._stop.set()
            listener.stop()
            self.recorder.close()


def _preload_cuda_libs():
    """Load the pip-installed CUDA/cuDNN .so files into the process directly.

    ctranslate2 dlopen()s libs like libcublas.so.12 / libcudnn*.so.9 by SONAME.
    Preloading them with RTLD_GLOBAL makes those symbols resolvable no matter
    what LD_LIBRARY_PATH is — robust against polluted shell environments
    (e.g. ROS) or launchers that don't export the path. Best-effort; on CPU-only
    boxes the nvidia packages are absent and this simply does nothing.
    """
    import ctypes
    import glob
    import importlib.util

    spec = importlib.util.find_spec("nvidia")
    if not spec or not spec.submodule_search_locations:
        return
    base = list(spec.submodule_search_locations)[0]
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


def _cuda_available() -> bool:
    try:
        from ctranslate2 import get_cuda_device_count

        return get_cuda_device_count() > 0
    except Exception:
        return shutil.which("nvidia-smi") is not None


def _acquire_single_instance():
    """Prevent a second instance (double listeners -> double paste)."""
    import fcntl

    runtime = os.environ.get("XDG_RUNTIME_DIR", "/tmp")
    lock_path = Path(runtime) / "voice-term.lock"
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[error] voice-term is already running. Exiting.")
        notify("voice-term", "すでに起動しています")
        sys.exit(1)
    return fh  # keep open for the process lifetime


def main():
    if "--list-devices" in sys.argv:
        print(sd.query_devices())
        return
    _lock = _acquire_single_instance()  # noqa: F841 (held for lifetime)
    cfg = load_config()
    app = App(cfg)
    # Make Ctrl+C work even while threads are alive.
    signal.signal(signal.SIGINT, signal.default_int_handler)
    app.run()


if __name__ == "__main__":
    main()
