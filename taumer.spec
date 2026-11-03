# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

block_cipher = None

# Base files to bundle inside the executable directory
datas = [
    ('app/taumer.svg', 'app'),
    ('app/taumer.png', 'app'),
    ('app/taumer_mark.svg', 'app'),
    ('app/style.css', 'app'),
    ('app/ui/shark_assets', 'app/ui/shark_assets'),
]

# On Linux / Windows, bundle glib schemas so GSettings is self-contained
if sys.platform != "win32":
    if os.path.exists('/usr/share/glib-2.0/schemas/gschemas.compiled'):
        datas.append(('/usr/share/glib-2.0/schemas/gschemas.compiled', 'share/glib-2.0/schemas'))
else:
    for candidate in [
        'C:/msys64/ucrt64/share/glib-2.0/schemas/gschemas.compiled',
        '/ucrt64/share/glib-2.0/schemas/gschemas.compiled',
    ]:
        if os.path.exists(candidate):
            datas.append((candidate, 'share/glib-2.0/schemas'))
            break

hidden_imports = [
    'gi',
    'gi.repository.Gtk',
    'gi.repository.Adw',
    'gi.repository.Gdk',
    'gi.repository.Gio',
    'gi.repository.GLib',
    'gi.repository.GObject',
    'gi.repository.GdkPixbuf',
    'gi.repository.Pango',
    'gi.repository.Graphene',
    'yaml',
    'requests',
    'sqlite3',
    'ctypes',
    'storage',
    'watcher',
    'models',
    'config',
    'ui',
    'ui.main_window',
    'ui.shark_home_view',
    'ui.home_view',
    'ui.tasks_view',
    'ui.calendar_view',
    'ui.journal_view',
    'ui.watcher_view',
    'ui.reports_view',
    'ui.dialogs',
]

# Only include WebKit on platforms where it's available (Linux)
try:
    import gi
    gi.require_version('WebKit', '6.0')
    hidden_imports.extend(['gi.repository.WebKit', 'gi.repository.JavaScriptCore', 'gi.repository.Soup'])
except Exception:
    pass

a = Analysis(
    ['app/main.py'],
    pathex=['app'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=['hooks'],
    hooksconfig={
        'gi': {
            'module-versions': {
                'Gtk': '4.0',
                'Adw': '1',
                'WebKit': '6.0',
            },
            'icons': ['hicolor', 'Adwaita'],
            'themes': ['Adwaita'],
            'languages': ['en'],
        }
    },
    runtime_hooks=[],
    excludes=['pkg_resources'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Taumer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app/taumer.ico' if os.path.exists('app/taumer.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Taumer',
)
