"""
Configuration module for Taumer Tracker (Linux & Windows Obsidian Integration).
"""

import os
import sys
import subprocess
from pathlib import Path

# Paths & Execution Context
if getattr(sys, 'frozen', False):
    # Running inside a PyInstaller frozen bundle
    _meipass = getattr(sys, '_MEIPASS', None)
    if _meipass and (Path(_meipass) / "app").exists():
        APP_DIR = Path(_meipass) / "app"
    elif _meipass:
        APP_DIR = Path(_meipass)
    else:
        APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parent

# Check for Vault / Tracker root:
# 1. Environment variable TAUMER_VAULT
# 2. Current working directory if it contains Tareas/ or Diario/
# 3. Executable parent directory if frozen and contains Tareas/ or Diario/
# 4. Fallback to repo root (when running in repo) or user home Documents/Taumer
tracker_root_candidate = None
env_vault = os.environ.get("TAUMER_VAULT")
if env_vault and Path(env_vault).exists():
    tracker_root_candidate = Path(env_vault)
elif (Path.cwd() / "Tareas").exists() or (Path.cwd() / "Diario").exists():
    tracker_root_candidate = Path.cwd()
elif getattr(sys, 'frozen', False) and ((Path(sys.executable).parent / "Tareas").exists() or (Path(sys.executable).parent / "Diario").exists()):
    tracker_root_candidate = Path(sys.executable).parent
elif not getattr(sys, 'frozen', False) and (APP_DIR.parent / "Tareas").exists():
    tracker_root_candidate = APP_DIR.parent
else:
    tracker_root_candidate = Path.home() / "Documents" / "Taumer"

TRACKER_ROOT = tracker_root_candidate
VAULT_ROOT = TRACKER_ROOT.parent

DIARIO_DIR = TRACKER_ROOT / "Diario"
TAREAS_DIR = TRACKER_ROOT / "Tareas"
PROYECTOS_DIR = TRACKER_ROOT / "Proyectos"
REPORTES_DIR = TRACKER_ROOT / "Reportes"

# OS specific user config and cache
if sys.platform == "win32":
    appdata = os.environ.get("APPDATA")
    localappdata = os.environ.get("LOCALAPPDATA")
    CONFIG_DIR = (Path(appdata) if appdata else Path.home() / ".config") / "tracker_tareas"
    CACHE_DIR = (Path(localappdata) if localappdata else Path.home() / ".local" / "share") / "tracker_tareas"
else:
    CONFIG_DIR = Path.home() / ".config" / "tracker_tareas"
    CACHE_DIR = Path.home() / ".local" / "share" / "tracker_tareas"

CONFIG_FILE = CONFIG_DIR / "settings.json"
LOCAL_DB_FILE = CACHE_DIR / "activity.db"
FAVICONS_DIR = CACHE_DIR / "favicons"

# ActivityWatch settings
AW_DEFAULT_HOST = "localhost"
AW_DEFAULT_PORT = 5600
AW_URL = f"http://{AW_DEFAULT_HOST}:{AW_DEFAULT_PORT}"

# Ensure directories exist
for p in [DIARIO_DIR, TAREAS_DIR, PROYECTOS_DIR, REPORTES_DIR, CONFIG_DIR, CACHE_DIR, FAVICONS_DIR]:
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def open_file_or_url(target: str | Path):
    """Cross-platform launcher for opening files or URLs with default desktop apps."""
    try:
        target_str = str(target)
        if sys.platform == "win32":
            os.startfile(target_str)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target_str])
        else:
            subprocess.Popen(["xdg-open", target_str])
    except Exception as e:
        print(f"[Taumer] Error opening {target}: {e}")

