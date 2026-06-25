# type-by-voice 🎙️

**Type by voice, anywhere on Linux — local, GPU-accelerated, and fully open source.**

Hold a hotkey, speak, release. Your words are transcribed locally with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper) and pasted into
**whatever app has focus** — terminal, Slack, Discord, browser, email, your
editor. No cloud, no API keys, no subscriptions. Your voice never leaves your
machine.

Nothing ever covers your screen: the only UI is a single, tidy **tray dot** that
turns green and **ripples to your voice** while it listens — like a little sonar
in your top bar. 🟢〰️

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
- 🎨 **Stays out of your way** — no floating windows or popups. Just one
  colour-coded tray dot that pulses to your voice while recording.
- 🪶 **Tiny & hackable** — two small, dependency-light Python files. Read them,
  change them.

## Features

- 🔒 100% local & offline (after the one-time model download)
- 🎚️ Push-to-talk (hold) or toggle mode
- ⌨️ Configurable global hotkey or combo (default: **hold Windows + Alt together**)
- 📋 Clipboard-paste, direct-type, or copy-only output
- 🖥️ X11 (`xdotool`) and Wayland (`wtype` / `ydotool`) auto-detection
- 🚦 Colour-coded tray icon (grey→blue→green→amber) so you always know the state
- 🌊 While recording, the green icon emits **sonar ripples that pulse to your voice**
- 🖱️ Quit from the tray icon's menu; one-click app launcher (no terminal)
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

# 1b. (Recommended) the colour-coded tray icon
sudo apt install -y gir1.2-ayatanaappindicator3-0.1

# 2. Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

That's it — `./voice-term` and start talking. 👇

> **Wayland:** install `wl-clipboard` and `wtype` (or `ydotool` + its daemon
> and `/dev/uinput` permissions) instead of `xdotool`/`xclip`. The session type
> is auto-detected at startup.

## Usage

```bash
./voice-term                 # start dictating
./voice-term --list-devices  # list microphones
```

Focus any app, **hold Windows + Alt together**, speak, release — the text is
pasted at your cursor. Nothing floats over your screen: the **tray icon** carries
all the feedback, and while you talk it emits sonar ripples that pulse to your
voice. First run downloads the model (~1.5 GB), a few minutes. Quit from the tray
icon's menu (or **Ctrl+C** in a terminal).

### Status tray icon (recommended)

A colour-coded dot shows up in the top-bar indicator area:

| Colour | Meaning |
|---|---|
| ⚪ grey | loading the model |
| 🔵 blue | idle / ready (running, waiting for the hotkey) |
| 🟢 green + ripples | recording (ripples pulse to your voice) |
| 🟡 amber | transcribing |

It needs the AppIndicator typelib (the runtime library is already on Ubuntu
GNOME). Install it once:

```bash
sudo apt install gir1.2-ayatanaappindicator3-0.1
```

Without it the app still works — you just don't get the tray icon (a hint is
logged). The tray helper runs under the *system* python via GObject, separate
from the venv.

### One-click launcher (GNOME)

```bash
./install-desktop.sh   # adds "voice-term" to your app grid (pin it to the dock)
```

Launched from the app grid it runs **without a terminal** — the tray icon and
desktop toasts are your feedback; logs go to `~/.cache/voice-term.log`.
**Quit from the tray icon's menu** (終了).

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
| `hotkey.key` | `"cmd+alt"` | One key, a `+`-combo held together (e.g. `cmd+alt`), or a list of alternatives. Names: `cmd`/`super`/`win`, `alt`, `ctrl`, `f9`, … or a single char. |
| `audio.device` | `""` | Mic name substring or index; empty = default. |
| `output.method` | `paste` | `paste`, `type`, or `clipboard` (manual paste). |
| `output.trailing_space` | `false` | Add a space after inserted text. |
| `ui.tray` | `true` | Show the colour-coded tray icon (needs the AppIndicator typelib). |

## Troubleshooting

- **The combo triggers your desktop (e.g. Super+Alt moves a window):** your
  window manager has a shortcut on the same combo. Change `hotkey.key` to
  something free like `f9` or `pause`.
- **`libcublas.so.12 ... cannot be loaded`:** should not happen (libs are
  preloaded), but if it does, reinstall requirements so the
  `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` wheels are present.
- **Running on CPU unexpectedly:** look for `Loading ... on cuda` at startup.
- **No paste:** check `xdotool`/`xclip` (X11) are installed; text stays on the
  clipboard as a fallback.
- **No tray icon:** install `gir1.2-ayatanaappindicator3-0.1`, and make sure the
  GNOME "AppIndicator" extension is enabled. Without it the app runs fine,
  just without the icon.

## How it works

```
Win+Alt held → sounddevice captures 16 kHz mono (RMS level → tray ripples)
   → faster-whisper (GPU) transcribes on release
      → text copied to clipboard → Ctrl+V sent to the focused window
```

The tray icon is a separate helper (`tray_indicator.py`) launched under the
system python, because GObject/AppIndicator and the venv's faster-whisper don't
share an interpreter. They communicate through a tiny state file in
`$XDG_RUNTIME_DIR/voice-term/`: the main app writes `"<state> <level>"`, the
helper polls it (~16 fps) and renders the dot — emitting sonar ripples whose rate
and brightness follow the live mic level while recording. The tray's *Quit*
signals the main process.

## Contributing

Issues and PRs welcome — especially Wayland testing, packaging, and
additional output backends. Two small Python files; dive in.

## License

[MIT](LICENSE) © 2026 Kotaro Nakata
