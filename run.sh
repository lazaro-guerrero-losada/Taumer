#!/usr/bin/env bash
# Launcher for Taumer Tracker
SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
    DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" >/dev/null 2>&1 && pwd)"
export PYTHONPATH="$SCRIPT_DIR/app:$PYTHONPATH"
python3 "$SCRIPT_DIR/app/main.py" "$@"
