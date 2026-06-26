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
# Transcription language.
#   "auto" -> detect per phrase, but only among `auto_languages` below, so you
#             can switch languages just by speaking (English in -> English out,
#             Japanese in -> Japanese out). This is the default.
#   "ja" / "en" / … -> force that language for every phrase.
language = "auto"
# Candidate languages considered when language = "auto". Keep this short (the
# fewer, the more reliable the detection). Whisper codes: "ja", "en", ...
auto_languages = ["ja", "en"]

[hotkey]
# "ptt"   = hold key to record, release to transcribe (push-to-talk)
# "toggle"= press once to start, press again to stop
mode = "ptt"
# Hotkey: a single key, a "+"-joined combo to hold together, or a list of
# alternatives. Modifier names cmd/super/win, alt, ctrl, shift each match their
# left & right keys.
# Examples: "cmd+alt" (hold Windows+Alt), "ctrl_r", ["ctrl_r", "ctrl_l"], "f9".
# A combo like cmd+alt avoids clashing with copy/paste (Ctrl+C / Ctrl+V).
key = "cmd+alt"

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

[ui]
# Show a colour-coded status icon in the top-bar tray: grey=loading, blue=idle,
# green=recording (with sonar ripples that pulse to your voice), amber=
# transcribing. Needs the AyatanaAppIndicator typelib; if it's missing the app
# still works, just without the icon.
tray = true
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
        self.level = 0.0  # latest mic RMS (0..~1), streamed to the tray icon
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
            # Cheap RMS level for the tray ripples (atomic float write).
            self.level = float(np.sqrt(np.mean(np.square(indata), dtype=np.float64)))
        else:
            self.level = 0.0

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
# Friendly modifier names -> the pynput keys they should match. We accept both
# the left/right variants and the generic key so users don't have to care which
# physical key they press.
MODIFIER_ALIASES = {
    "cmd": ("cmd", "cmd_l", "cmd_r"),
    "super": ("cmd", "cmd_l", "cmd_r"),
    "win": ("cmd", "cmd_l", "cmd_r"),
    "windows": ("cmd", "cmd_l", "cmd_r"),
    "meta": ("cmd", "cmd_l", "cmd_r"),
    "alt": ("alt", "alt_l", "alt_r", "alt_gr"),
    "ctrl": ("ctrl", "ctrl_l", "ctrl_r"),
    "control": ("ctrl", "ctrl_l", "ctrl_r"),
    "shift": ("shift", "shift_l", "shift_r"),
}


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


def key_id(key):
    """A stable, hashable identity for a pressed key (so we can track held keys)."""
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return ("char", key.char)
        return ("vk", key.vk)
    return ("key", key)  # keyboard.Key enum members are hashable


def parse_key_group(name: str) -> frozenset:
    """One slot of a chord: the set of key identities that satisfy it.

    A modifier alias like "alt" expands to left/right/generic variants so any of
    them counts. Anything else is a single literal key.
    """
    name = name.strip().lower()
    variants = MODIFIER_ALIASES.get(name)
    if variants is None:
        return frozenset({key_id(parse_key(name))})
    ids = set()
    for v in variants:
        if hasattr(keyboard.Key, v):
            ids.add(key_id(getattr(keyboard.Key, v)))
    return frozenset(ids)


def parse_hotkey(value) -> list:
    """Parse the config hotkey into a list of chords (alternatives).

    Each chord is a list of key-groups that must ALL be held at once.
    - "cmd+alt"            -> one chord: hold Super and Alt together
    - "ctrl_r"             -> one chord: a single key
    - ["ctrl_r", "ctrl_l"] -> two chords: either key alone works
    """
    alts = value if isinstance(value, (list, tuple)) else [value]
    chords = []
    for alt in alts:
        groups = [parse_key_group(part) for part in str(alt).split("+") if part.strip()]
        if groups:
            chords.append(groups)
    return chords


# --------------------------------------------------------------------------- #
# Main app
# --------------------------------------------------------------------------- #
class App:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.language = cfg["model"]["language"]
        self.auto_languages = [str(l).lower() for l in cfg["model"].get("auto_languages", ["ja", "en"])]
        if self.language.lower() == "auto":
            self.language = None   # detect per phrase, restricted to auto_languages

        self.outputter = Outputter(cfg["output"]["method"], cfg["output"]["trailing_space"])
        self.outputter.warn_if_missing()

        device_cfg = cfg["audio"]["device"]
        device = device_cfg
        if isinstance(device_cfg, str) and device_cfg.isdigit():
            device = int(device_cfg)
        self.recorder = Recorder(cfg["audio"]["sample_rate"], device)

        self.chords = parse_hotkey(cfg["hotkey"]["key"])
        self.mode = cfg["hotkey"]["mode"].lower()
        self._held: set = set()       # key ids currently pressed
        self._chord_on = False        # whether a hotkey chord is fully held
        self._active = False  # currently recording
        self._jobs: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._ready = threading.Event()   # set once the model is loaded
        self._listener = None

        # IPC for the tray helper: we write "<state> [level]", it polls and
        # renders the icon (e.g. sonar ripples that pulse to the live level).
        runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
        self._ipc_dir = runtime / "voice-term"
        self._ipc_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._ipc_dir / "state"
        self._tray_proc = None
        self._tray_enabled = cfg.get("ui", {}).get("tray", True)
        self._state = "loading"

        # Model is loaded asynchronously in run() so the tray can show progress.
        self.model = None

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

    def _write_state(self, text: str):
        try:
            self._state_file.write_text(text)
        except OSError:
            pass

    def _set_state(self, state: str):
        """Publish a UI state for the tray helper to render."""
        self._state = state
        self._write_state(state)

    def _level_pump(self):
        """While recording, stream the live mic level to the tray (~20 fps) so
        its sonar ripples pulse to your voice. Idle otherwise."""
        while not self._stop.is_set():
            if self._active:
                level = min(1.0, self.recorder.level * 9.0)
                self._write_state(f"recording {level:.3f}")
                time.sleep(0.05)
            else:
                time.sleep(0.1)

    # --- recording lifecycle --- #
    def _start_recording(self):
        if self._active:
            return
        if not self._ready.is_set():
            notify("voice-term", "モデル読込中です。少々お待ちください…", timeout_ms=1200)
            return
        self._active = True
        self.recorder.begin()
        self._set_state("recording")
        print("\n[●] Recording... (release to transcribe)" if self.mode == "ptt"
              else "\n[●] Recording... (press again to stop)")

    def _stop_recording(self):
        if not self._active:
            return
        self._active = False
        audio = self.recorder.end()
        dur = len(audio) / self.recorder.sample_rate
        if dur < 0.3:
            print("[..] Too short, ignored.")
            self._set_state("idle")
            return
        print(f"[…] Transcribing {dur:.1f}s ...")
        self._set_state("transcribing")
        self._jobs.put(audio)

    def _pick_language(self, audio) -> str | None:
        """Choose the transcription language.

        If a fixed language is configured, use it. Otherwise detect, but only
        among `auto_languages` — so speaking English types English and Japanese
        types Japanese, without misfiring into some third language.
        """
        if self.language is not None:
            return self.language
        try:
            _, _, probs = self.model.detect_language(audio=audio)
        except Exception as e:
            print(f"[warn] Language detection failed ({e}); letting Whisper decide.")
            return None
        if not self.auto_languages:
            return None
        ranked = {lang: p for lang, p in probs}
        best = max(self.auto_languages, key=lambda l: ranked.get(l, 0.0))
        print(f"[lang] {best} ({ranked.get(best, 0.0):.2f})")
        return best

    # --- transcription worker --- #
    def _worker(self):
        while not self._stop.is_set():
            try:
                audio = self._jobs.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                language = self._pick_language(audio)
                segments, info = self.model.transcribe(
                    audio,
                    language=language,
                    beam_size=5,
                    vad_filter=True,
                )
                text = "".join(seg.text for seg in segments).strip()
            except Exception as e:
                print(f"[error] Transcription failed: {e}")
                notify("❌ 変換失敗", str(e)[:120])
                self._set_state("idle")
                continue
            if text:
                print(f"[✓] {text}")
                notify("✓ 入力しました", text[:120])
                self.outputter.send(text)
            else:
                print("[..] (no speech detected)")
                notify("…無音でした", "", timeout_ms=800)
            self._set_state("idle")

    # --- key handlers --- #
    def _chord_satisfied(self) -> bool:
        """True if any configured chord has all of its key-groups held."""
        for chord in self.chords:
            if all(group & self._held for group in chord):
                return True
        return False

    def _update_chord(self):
        on = self._chord_satisfied()
        if on and not self._chord_on:
            self._chord_on = True
            if self.mode == "ptt":
                self._start_recording()
            elif self._active:  # toggle
                self._stop_recording()
            else:
                self._start_recording()
        elif not on and self._chord_on:
            self._chord_on = False
            if self.mode == "ptt":
                self._stop_recording()

    def _on_press(self, key):
        self._held.add(key_id(key))
        self._update_chord()

    def _on_release(self, key):
        self._held.discard(key_id(key))
        self._update_chord()

    def _init_model(self):
        """Load the model in the background so the tray can show progress."""
        try:
            self.model = self._load_model()
        except Exception as e:
            print(f"[error] Model load failed: {e}")
            notify("voice-term", f"モデル読込に失敗しました: {str(e)[:120]}")
            self._set_state("idle")
            return
        self._ready.set()
        self._set_state("idle")
        mode_desc = "hold" if self.mode == "ptt" else "toggle"
        keys = self.cfg["hotkey"]["key"]
        keys_str = " or ".join(str(k) for k in keys) if isinstance(keys, (list, tuple)) else str(keys)
        print(f"[ready] {mode_desc.capitalize()} '{keys_str}' to dictate.")
        notify("voice-term", f"準備完了。'{keys_str}' を長押しで音声入力。", timeout_ms=2500)

    def shutdown(self):
        """Stop everything. Safe to call from any thread, more than once."""
        if self._stop.is_set():
            return
        print("\n[exit] Shutting down...")
        self._stop.set()
        if self._listener:
            self._listener.stop()
        self.recorder.close()
        if self._tray_proc and self._tray_proc.poll() is None:
            self._tray_proc.terminate()

    def _start_tray(self):
        """Launch the colour-coded tray icon as a separate system-python helper.

        It lives in a different toolkit (GTK) and process. Best-effort: if the
        AppIndicator typelib is missing we just skip it.
        """
        if not self._tray_enabled:
            return
        helper = Path(__file__).resolve().parent / "tray_indicator.py"
        if not helper.exists():
            return
        py = "/usr/bin/python3"
        check = subprocess.run(
            [py, "-c", "import gi; gi.require_version('AyatanaAppIndicator3','0.1');"
                       " from gi.repository import AyatanaAppIndicator3; import PIL"],
            capture_output=True,
        )
        if check.returncode != 0:
            print("[info] Tray icon unavailable (install gir1.2-ayatanaappindicator3-0.1 "
                  "to enable it).")
            return
        try:
            self._tray_proc = subprocess.Popen(
                [py, str(helper),
                 "--state-file", str(self._state_file),
                 "--pid", str(os.getpid()),
                 "--icon-dir", str(self._ipc_dir)],
            )
        except Exception as e:
            print(f"[warn] Could not start tray icon: {e}")

    def run(self):
        worker = threading.Thread(target=self._worker, daemon=True)
        worker.start()
        threading.Thread(target=self._level_pump, daemon=True).start()
        self.recorder.start()

        self._set_state("loading")
        self._start_tray()
        notify("voice-term", "起動中… モデルを読み込んでいます。", timeout_ms=2000)
        threading.Thread(target=self._init_model, daemon=True).start()

        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

        # The tray "Quit" item sends SIGTERM to us; shut down gracefully.
        signal.signal(signal.SIGTERM, lambda *a: self.shutdown())

        try:
            while not self._stop.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()


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
