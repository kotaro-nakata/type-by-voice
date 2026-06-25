#!/usr/bin/env bash
# Installs a one-click "voice-term" launcher into the GNOME app menu.
# Run after setting up the venv (see README).
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APPS="$HOME/.local/share/applications"
mkdir -p "$APPS"

# Runs without a terminal: state is shown by the on-screen overlay + toasts.
# Logs go to ~/.cache/voice-term.log for troubleshooting. Right-click the
# overlay to quit.
cat > "$APPS/voice-term.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=voice-term
Comment=Local push-to-talk voice typing (hold Windows+Alt)
Exec=bash -lc "exec '$HERE/voice-term' >> \$HOME/.cache/voice-term.log 2>&1"
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
