#!/usr/bin/env bash
# Installs a one-click "voice-term" launcher into the GNOME app menu.
# Run after setting up the venv (see README).
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"

# Runs without a terminal: feedback is the colour-coded tray icon (quit from its
# menu). The launcher itself logs to ~/.cache/voice-term.log when it has no
# terminal, so the Exec line stays a clean, spec-compliant single command.
cat > "$APPS/voice-term.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=voice-term
Comment=Local push-to-talk voice typing (hold Windows+Alt)
Exec="$HERE/voice-term"
Icon=audio-input-microphone
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

update-desktop-database "$APPS" 2>/dev/null || true
echo "Installed launcher: $APPS/voice-term.desktop"
echo "Look for 'voice-term' in your app grid."
echo
echo "For the colour-coded tray icon, install the AppIndicator typelib once:"
echo "  sudo apt install gir1.2-ayatanaappindicator3-0.1"
