#!/usr/bin/env bash
set -e

# Installer for Taumer
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

echo "=== Installing Taumer ==="

mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

# 1. Symlink launcher command to ~/.local/bin/taumer
ln -sf "$REPO_DIR/run.sh" "$BIN_DIR/taumer"
chmod +x "$REPO_DIR/run.sh"

# 2. Install application icon
cp "$REPO_DIR/app/taumer.svg" "$ICON_DIR/taumer.svg"

# 3. Generate desktop entry with full path
cat << EOF > "$DESKTOP_DIR/taumer.desktop"
[Desktop Entry]
Name=Taumer
GenericName=Task & Focus Tracker
Comment=Native Linux Task & Focus Tracker with Obsidian Integration
Exec=$BIN_DIR/taumer %u
Icon=taumer
Terminal=false
Type=Application
Categories=Utility;Office;ProjectManagement;
Keywords=task;todo;tracker;obsidian;focus;taumer;pomodoro;timeblock;
StartupNotify=true
EOF

chmod +x "$DESKTOP_DIR/taumer.desktop"

# Optional: update desktop entry on ~/Desktop if directory exists
if [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_DIR/taumer.desktop" "$HOME/Desktop/Taumer.desktop"
    chmod +x "$HOME/Desktop/Taumer.desktop"
    gio set "$HOME/Desktop/Taumer.desktop" metadata::trusted true 2>/dev/null || true
fi

# Update icon cache if available
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "✓ Taumer installed successfully!"
echo "  Run it from your application menu or simply type 'taumer' in your terminal."
