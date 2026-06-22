# type-by-voice 🎙️

**Type by voice, anywhere on Linux — local, GPU-accelerated, and fully open source.**

Hold a hotkey, speak, release. Your words are transcribed locally with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) and pasted into
**whatever app has focus** — terminal, Slack, Discord, browser, email, your
editor. No cloud, no API keys, no subscriptions. Your voice never leaves your
machine.

---

## Why another dictation tool?

There are several Linux dictation tools already. `type-by-voice` focuses on a
few things they often get wrong:

- ⚡ **GPU + faster-whisper** — fast *and* accurate. Many tools default to CPU
  or the lighter VOSK engine; this uses Whisper `large-v3-turbo` on your GPU.
- 🌏 **Great multilingual / Japanese support out of the box** — defaults to
  Japanese but works for any Whisper-supported language. Most English-first
  tools handle this poorly.
- 🧩 **Works in every app** — output goes to the focused window via clipboard
  paste, so Unicode/Japanese never drops characters (unlike per-character
  typing).
- 🛠️ **No `LD_LIBRARY_PATH` hell** — the CUDA/cuDNN libraries are preloaded
  automatically, so GPU "just works" even inside polluted shell environments
  (ROS, conda, etc.) — the #1 thing people get stuck on.
- 🪶 **Tiny & hackable** — a single ~350-line Python file. Read it, change it.

## Features

- 🔒 100% local & offline (after the one-time model download)
- 🎚️ Push-to-talk (hold) or toggle mode
- ⌨️ Configurable global hotkey (default: **either Ctrl** — left or right)
- 📋 Clipboard-paste, direct-type, or copy-only output
- 🖥️ X11 (`xdotool`) and Wayland (`wtype` / `ydotool`) auto-detection
- 🔔 Desktop notifications for recording / done status
- 🖱️ One-click launcher for the GNOME app menu
- 🧷 Single-instance lock (no accidental double-paste)

## Requirements

- Linux (developed on Ubuntu / GNOME, X11)
- Python 3.11+
- NVIDIA GPU with CUDA for best speed — **falls back to CPU automatically**

## Install

```bash
git clone https://github.com/kotaro-nakata/type-by-voice.git
cd type-by-voice

# 1. System packages (X11). For Wayland, see the note below.
sudo apt update
sudo apt install -y portaudio19-dev xdotool xclip

# 2. Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> **Wayland:** install `wl-clipboard` and `wtype` (or `ydotool` + its daemon
> and `/dev/uinput` permissions) instead of `xdotool`/`xclip`. The session type
> is auto-detected at startup.

## Usage

```bash
./voice-term                 # start dictating
./voice-term --list-devices  # list microphones
```

Focus any app, **hold either Ctrl** (left or right), speak, release — the text
is pasted at your cursor. First run downloads the model (~1.5 GB), a few minutes.
Press **Ctrl+C** to quit.

### One-click launcher (GNOME)

```bash
./install-desktop.sh   # adds "voice-term" to your app grid (pin it to the dock)
```

### Global command (optional)

```bash
ln -s "$(pwd)/voice-term" ~/.local/bin/voice-term   # then run: voice-term
```

## Configuration

Auto-created on first run at `~/.config/voice-term/config.toml`.

| Key | Default | Notes |
|---|---|---|
| `model.name` | `large-v3-turbo` | Multilingual + fast. Or `large-v3`, `medium`, a local path. |
| `model.device` | `auto` | `auto` → CUDA if available, else CPU. |
| `model.compute_type` | `auto` | `auto` → `float16` (GPU) / `int8` (CPU). |
| `model.language` | `ja` | `ja`, `en`, … or `auto` to detect. |
| `hotkey.mode` | `ptt` | `ptt` (hold) or `toggle` (press to start/stop). |
| `hotkey.key` | `["ctrl_r", "ctrl_l"]` | One key or a list. pynput names: `alt_r`, `f9`, `pause`, … or a single char. |
| `audio.device` | `""` | Mic name substring or index; empty = default. |
| `output.method` | `paste` | `paste`, `type`, or `clipboard` (manual paste). |
| `output.trailing_space` | `false` | Add a space after inserted text. |

## Troubleshooting

- **A specific app ignores the hotkey (e.g. Slack):** that app has a shortcut
  bound to the same key. Change `hotkey.key` to `f9` or `pause`.
- **`libcublas.so.12 ... cannot be loaded`:** should not happen (libs are
  preloaded), but if it does, reinstall requirements so the
  `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` wheels are present.
- **Running on CPU unexpectedly:** look for `Loading ... on cuda` at startup.
- **No paste:** check `xdotool`/`xclip` (X11) are installed; text stays on the
  clipboard as a fallback.

## How it works

```
Ctrl held → sounddevice captures 16 kHz mono
   → faster-whisper (GPU) transcribes on release
      → text copied to clipboard → Ctrl+V sent to the focused window
```

## Contributing

Issues and PRs welcome — especially Wayland testing, packaging, and
additional output backends. It's one small Python file; dive in.

## License

[MIT](LICENSE) © 2026 Kotaro Nakata
