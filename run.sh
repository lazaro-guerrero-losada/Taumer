#!/usr/bin/env bash
# Launcher for Taumer Tracker
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/app:$PYTHONPATH"
python3 "$SCRIPT_DIR/app/main.py" "$@"
