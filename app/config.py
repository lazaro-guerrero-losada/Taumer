"""
Configuration module for Tracker Tareas (Linux Mint & Obsidian).
"""

import os
from pathlib import Path

# Paths
APP_DIR = Path(__file__).resolve().parent
TRACKER_ROOT = APP_DIR.parent
VAULT_ROOT = TRACKER_ROOT.parent

DIARIO_DIR = TRACKER_ROOT / "Diario"
TAREAS_DIR = TRACKER_ROOT / "Tareas"
PROYECTOS_DIR = TRACKER_ROOT / "Proyectos"
REPORTES_DIR = TRACKER_ROOT / "Reportes"

CONFIG_DIR = Path.home() / ".config" / "tracker_tareas"
CONFIG_FILE = CONFIG_DIR / "settings.json"
CACHE_DIR = Path.home() / ".local" / "share" / "tracker_tareas"
LOCAL_DB_FILE = CACHE_DIR / "activity.db"
FAVICONS_DIR = CACHE_DIR / "favicons"

# ActivityWatch settings
AW_DEFAULT_HOST = "localhost"
AW_DEFAULT_PORT = 5600
AW_URL = f"http://{AW_DEFAULT_HOST}:{AW_DEFAULT_PORT}"

# Ensure directories exist
for p in [DIARIO_DIR, TAREAS_DIR, PROYECTOS_DIR, REPORTES_DIR, CONFIG_DIR, CACHE_DIR, FAVICONS_DIR]:
    p.mkdir(parents=True, exist_ok=True)
