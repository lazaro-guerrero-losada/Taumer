#!/usr/bin/env bash
set -e

# Installer for Taumer
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
REPO_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"

BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR_SCALABLE="$HOME/.local/share/icons/hicolor/scalable/apps"
ICON_DIR_512="$HOME/.local/share/icons/hicolor/512x512/apps"
PIXMAPS_DIR="$HOME/.local/share/pixmaps"

echo "=== Installing Taumer ==="

mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR_SCALABLE" "$ICON_DIR_512" "$PIXMAPS_DIR"

# 1. Symlink launcher command to ~/.local/bin/taumer
chmod +x "$REPO_DIR/run.sh"
ln -sf "$REPO_DIR/run.sh" "$BIN_DIR/taumer"

# 2. Install application icon in all standard locations
cp "$REPO_DIR/app/taumer.svg" "$ICON_DIR_SCALABLE/taumer.svg"
cp "$REPO_DIR/app/taumer.png" "$ICON_DIR_512/taumer.png"
cp "$REPO_DIR/app/taumer.svg" "$PIXMAPS_DIR/taumer.svg"
cp "$REPO_DIR/app/taumer.png" "$PIXMAPS_DIR/taumer.png"

# 3. Generate desktop application menu entry
cat << EOF > "$DESKTOP_DIR/taumer.desktop"
[Desktop Entry]
Name=Taumer
GenericName=Task & Focus Tracker
Comment=Native Linux Task & Focus Tracker with Obsidian Integration
Exec=$BIN_DIR/taumer
Icon=taumer
Terminal=false
Type=Application
Categories=Utility;Office;ProjectManagement;
Keywords=task;todo;tracker;obsidian;focus;taumer;pomodoro;timeblock;
StartupNotify=true
EOF

chmod +x "$DESKTOP_DIR/taumer.desktop"

# 4. Generate Desktop shortcut (with absolute path to icon and script for Nemo / Cinnamon)
if [ -d "$HOME/Desktop" ]; then
    cat << EOF > "$HOME/Desktop/Taumer.desktop"
[Desktop Entry]
Name=Taumer
GenericName=Task & Focus Tracker
Comment=Native Linux Task & Focus Tracker with Obsidian Integration
Exec=sh -c '"$REPO_DIR/run.sh"'
Icon=$REPO_DIR/app/taumer.png
Terminal=false
Type=Application
Categories=Utility;Office;ProjectManagement;
Keywords=task;todo;tracker;obsidian;focus;taumer;pomodoro;timeblock;
StartupNotify=true
EOF
    chmod +x "$HOME/Desktop/Taumer.desktop"
    gio set "$HOME/Desktop/Taumer.desktop" metadata::trusted true 2>/dev/null || true
    touch "$HOME/Desktop/Taumer.desktop"
fi

# 5. Clear Nemo desktop icon thumbnail cache so new icon renders immediately
rm -rf "$HOME/.cache/thumbnails/normal/"*taumer* "$HOME/.cache/thumbnails/large/"*taumer* 2>/dev/null || true

# Update icon cache if available
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "✓ Taumer installed successfully!"
echo "  Run it from your application menu, desktop shortcut, or type 'taumer'."
