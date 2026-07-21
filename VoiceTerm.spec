# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir bundle for VoiceTerm.

Run this spec on the target OS; PyInstaller does not cross-compile. Keeping the
bundle as onedir makes native-library failures diagnosable and lets the native
installer own installation and removal.
"""
from pathlib import Path
import sys

from PyInstaller.utils.hooks import (
    collect_all,
    collect_dynamic_libs,
    collect_submodules,
)


ROOT = Path(SPECPATH)

datas = []
binaries = []
hiddenimports = [
    "platform_backend",
    "wayland_hotkey",
]

# These libraries load parts of their implementation dynamically, so static
# import analysis alone is not sufficient on every platform.
for package in ("faster_whisper", "ctranslate2"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

hiddenimports += collect_submodules("pynput")
if sys.platform.startswith("linux"):
    hiddenimports += collect_submodules("evdev")

if sys.platform == "win32":
    hiddenimports += ["tray_win", "icon_art", "pystray", "pyperclip", "PIL"]
    icon = str(ROOT / "voice-term.ico")
else:
    # The Linux AppIndicator helper runs under system Python. Ship its source
    # beside the frozen modules so voice_term.py can launch it unchanged.
    datas += [
        (str(ROOT / "tray_indicator.py"), "."),
        (str(ROOT / "icon_art.py"), "."),
    ]
    icon = None

# NVIDIA wheels are found dynamically by platform_backend, so PyInstaller's
# import scan cannot see their shared libraries. Include them when installed;
# CPU-only build environments simply return empty lists here.
if sys.platform in ("win32", "linux"):
    for package in ("nvidia.cublas", "nvidia.cudnn"):
        binaries += collect_dynamic_libs(package)

a = Analysis(
    [str(ROOT / "voice_term.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VoiceTerm",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="VoiceTerm",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="VoiceTerm.app",
        icon=None,
        bundle_identifier="VoiceTerm.VoiceTerm",
        info_plist={
            "CFBundleDisplayName": "VoiceTerm",
            "NSMicrophoneUsageDescription":
                "VoiceTerm uses the microphone to transcribe speech locally.",
        },
    )
