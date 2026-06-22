#!/usr/bin/env bash
# Installs a one-click "voice-term" launcher into the GNOME app menu.
# Run after setting up the venv (see README).
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"

cat > "$APPS/voice-term.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=voice-term
Comment=Local push-to-talk voice typing (hold Right Ctrl)
Exec=gnome-terminal --title=voice-term -- bash -lc "$HERE/voice-term; echo; echo '[voice-term ended] press Enter to close'; read"
Icon=audio-input-microphone
Terminal=false
Categories=Utility;
StartupNotify=true
EOF

update-desktop-database "$APPS" 2>/dev/null || true
echo "Installed launcher: $APPS/voice-term.desktop"
echo "Look for 'voice-term' in your app grid."
