"""
Window tracker and ActivityWatch integration module.
Includes live Firefox open tabs extractor via ctypes liblz4 decompression,
deduplicated favicon extraction and download service, active window tracking via X11 xprop,
and chronological timeline history.
"""

import ctypes
import glob
import json
import os
import re
import sqlite3
import struct
import subprocess
import threading
import time
import urllib.parse
import shutil
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import requests

from config import LOCAL_DB_FILE, AW_URL, FAVICONS_DIR
from models import WindowActivityItem

# Load system liblz4 for Firefox session decompression
try:
    _liblz4 = ctypes.CDLL('liblz4.so.1')
    _liblz4.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    _liblz4.LZ4_decompress_safe.restype = ctypes.c_int
except Exception:
    _liblz4 = None


class FaviconService:
    """
    Manages extraction, downloading, and strict deduplication of website favicons.
    Favicons are cached in FAVICONS_DIR and mapped by normalized domain name
    so that icons are never downloaded or written more than once.
    """
    def __init__(self):
        self._icon_cache: Dict[str, Optional[str]] = {}
        self._lock = threading.Lock()
        self._load_existing_cache()

    def _load_existing_cache(self):
        """Populates in-memory cache from disk to avoid any disk queries or downloads."""
        try:
            if FAVICONS_DIR.exists():
                for f in FAVICONS_DIR.glob("*.*"):
                    if f.is_file() and f.stat().st_size > 0:
                        domain = f.stem.lower()
                        self._icon_cache[domain] = str(f)
        except Exception:
            pass

    def _detect_image_ext(self, data: bytes, icon_url: str = "") -> str:
        if data.startswith(b"\x89PNG"):
            return "png"
        elif data.startswith(b"RIFF") and b"WEBP" in data[:16]:
            return "webp"
        elif data.startswith(b"\x00\x00\x01\x00") or data.startswith(b"\x00\x00\x02\x00"):
            return "ico"
        elif b"<svg" in data[:100] or b"<?xml" in data[:50]:
            return "svg"
        elif data.startswith(b"\xff\xd8\xff"):
            return "jpg"
        if icon_url:
            path = urllib.parse.urlparse(icon_url).path.lower()
            for ext in ["png", "ico", "svg", "webp", "jpg"]:
                if path.endswith("." + ext):
                    return ext
        return "png"

    def get_or_download_favicon(self, url: str) -> Optional[str]:
        """
        Retrieves local favicon path for a URL with deduplication.
        1. Checks in-memory cache by domain (O(1)).
        2. Checks persistent on-disk cache (prevents duplicate downloads).
        3. Extracts from local Firefox favicons.sqlite (instant, offline).
        4. Downloads from favicon service as fallback if missing.
        """
        if not url:
            return None

        try:
            parsed = urllib.parse.urlparse(url)
            domain = parsed.netloc.lower()
            if not domain or parsed.scheme in ("about", "chrome", "resource", "data", "file"):
                return None

            safe_domain = re.sub(r"[^a-zA-Z0-9.-]", "_", domain)

            with self._lock:
                # 1. In-memory deduplication check
                if domain in self._icon_cache:
                    cached_path = self._icon_cache[domain]
                    if cached_path and os.path.exists(cached_path):
                        return cached_path

                # 2. Disk deduplication check (prevents duplicate download or re-write)
                for existing in FAVICONS_DIR.glob(f"{safe_domain}.*"):
                    if existing.is_file() and existing.stat().st_size > 0:
                        self._icon_cache[domain] = str(existing)
                        return str(existing)

                # 3. Extract from local Firefox favicons.sqlite (offline, high resolution)
                extracted_path = self._extract_from_firefox_db(url, parsed.scheme, domain, safe_domain)
                if extracted_path:
                    self._icon_cache[domain] = extracted_path
                    return extracted_path

                # 4. Fallback: Download via DuckDuckGo / Google Favicon API
                downloaded_path = self._download_favicon_fallback(domain, safe_domain)
                if downloaded_path:
                    self._icon_cache[domain] = downloaded_path
                    return downloaded_path

                self._icon_cache[domain] = None
                return None
        except Exception:
            return None

    def _extract_from_firefox_db(self, url: str, scheme: str, domain: str, safe_domain: str) -> Optional[str]:
        try:
            ff_favs = glob.glob(os.path.expanduser("~/.mozilla/firefox/*/favicons.sqlite"))
            if not ff_favs:
                return None

            ff_favs.sort(key=os.path.getmtime, reverse=True)
            src = ff_favs[0]
            tmp_db = f"/tmp/taumer_fav_{os.getpid()}.sqlite"

            shutil.copy2(src, tmp_db)
            if os.path.exists(src + "-wal"):
                try:
                    shutil.copy2(src + "-wal", tmp_db + "-wal")
                except Exception:
                    pass

            conn = sqlite3.connect(tmp_db)
            c = conn.cursor()
            prefix = f"{scheme}://{domain}%"
            c.execute("""
                SELECT i.data, i.icon_url
                FROM moz_pages_w_icons p
                JOIN moz_icons_to_pages ip ON p.id = ip.page_id
                JOIN moz_icons i ON ip.icon_id = i.id
                WHERE p.page_url LIKE ? OR p.page_url LIKE ?
                ORDER BY LENGTH(i.data) DESC
                LIMIT 1
            """, (url + "%", prefix))
            row = c.fetchone()
            conn.close()

            # Cleanup temp sqlite snapshot
            for p in [tmp_db, tmp_db + "-wal", tmp_db + "-shm"]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            if row and row[0]:
                data = row[0]
                ext = self._detect_image_ext(data, row[1])
                out_path = FAVICONS_DIR / f"{safe_domain}.{ext}"
                out_path.write_bytes(data)
                return str(out_path)
        except Exception:
            pass
        return None

    def _download_favicon_fallback(self, domain: str, safe_domain: str) -> Optional[str]:
        # Try DuckDuckGo first, then Google Favicon API
        providers = [
            f"https://icons.duckduckgo.com/ip3/{domain}.ico",
            f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
        ]
        # Also try base domain if subdomain (e.g. web.whatsapp.com -> whatsapp.com)
        parts = domain.split(".")
        if len(parts) > 2:
            base_domain = ".".join(parts[-2:])
            providers.append(f"https://icons.duckduckgo.com/ip3/{base_domain}.ico")
            providers.append(f"https://www.google.com/s2/favicons?domain={base_domain}&sz=32")

        for provider_url in providers:
            try:
                r = requests.get(provider_url, timeout=1.5)
                if r.status_code == 200 and len(r.content) > 100:
                    ext = self._detect_image_ext(r.content, "")
                    out_path = FAVICONS_DIR / f"{safe_domain}.{ext}"
                    out_path.write_bytes(r.content)
                    return str(out_path)
            except Exception:
                continue
        return None


class WindowWatcher:
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.favicon_service = FaviconService()
        self.current_window = {"app": "Starting...", "title": "", "start_time": time.time()}
        self._cached_tabs: List[Dict] = []
        self._last_tabs_refresh = 0.0
        self.listeners = []
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS window_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app TEXT,
                title TEXT,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration_seconds REAL,
                date TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_date ON window_events (date)")
        conn.commit()
        conn.close()

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def is_activitywatch_available(self) -> bool:
        try:
            r = requests.get(f"{AW_URL}/api/0/info", timeout=0.8)
            return r.status_code == 200
        except Exception:
            return False

    def start_activitywatch_server(self) -> bool:
        if self.is_activitywatch_available():
            return True
        try:
            aw_server_bin = os.path.expanduser("~/.local/bin/aw-server")
            aw_watcher_bin = os.path.expanduser("~/.local/bin/aw-watcher-window")
            if os.path.exists(aw_server_bin):
                subprocess.Popen([aw_server_bin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1.5)
            if os.path.exists(aw_watcher_bin):
                subprocess.Popen([aw_watcher_bin], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return self.is_activitywatch_available()
        except Exception as e:
            print(f"Error starting ActivityWatch: {e}")
            return False

    # ==========================================
    # FIREFOX OPEN TABS & FAVICONS EXTRACTOR
    # ==========================================
    def get_firefox_open_tabs(self) -> List[Dict[str, str]]:
        """
        Extracts all currently open tabs directly from Firefox sessionstore,
        resolving deduplicated favicons for each website.
        """
        if not _liblz4:
            return []

        search_patterns = [
            os.path.expanduser('~/.mozilla/firefox/*/sessionstore-backups/recovery.jsonlz4'),
            os.path.expanduser('~/.mozilla/firefox/*/sessionstore-backups/recovery.baklz4'),
        ]

        found_files = []
        for pat in search_patterns:
            found_files.extend(glob.glob(pat))

        if not found_files:
            return []

        # Sort by modification time to get freshest session
        found_files.sort(key=os.path.getmtime, reverse=True)

        tabs_result = []
        seen_titles = set()

        for session_file in found_files:
            try:
                with open(session_file, 'rb') as f:
                    data = f.read()

                if len(data) < 12 or data[:8] != b'mozLz40\0':
                    continue

                uncompressed_size = struct.unpack('<I', data[8:12])[0]
                compressed_body = data[12:]

                out_buf = ctypes.create_string_buffer(uncompressed_size)
                res = _liblz4.LZ4_decompress_safe(compressed_body, out_buf, len(compressed_body), uncompressed_size)
                if res != uncompressed_size:
                    continue

                js_data = json.loads(out_buf.raw[:res].decode('utf-8'))

                for win in js_data.get('windows', []):
                    for tab in win.get('tabs', []):
                        entries = tab.get('entries', [])
                        idx = tab.get('index', len(entries)) - 1
                        if 0 <= idx < len(entries):
                            entry = entries[idx]
                            title = entry.get('title', '').strip()
                            url = entry.get('url', '').strip()

                            if not title or url.startswith('about:'):
                                continue

                            clean_title = self._clean_tab_title(title, "Firefox")
                            if clean_title not in seen_titles:
                                seen_titles.add(clean_title)
                                
                                parsed = urllib.parse.urlparse(url)
                                domain = parsed.netloc.lower()
                                fav_path = self.favicon_service.get_or_download_favicon(url)

                                tabs_result.append({
                                    "title": title,
                                    "clean_title": clean_title,
                                    "url": url,
                                    "domain": domain,
                                    "favicon_path": fav_path,
                                    "icon": "firefox"
                                })

                if tabs_result:
                    break
            except Exception:
                pass

        self._cached_tabs = tabs_result
        self._last_tabs_refresh = time.time()
        return tabs_result

    def _clean_tab_title(self, raw_title: str, app_name: str) -> str:
        title = raw_title.strip()
        for suffix in [" — Mozilla Firefox", " - Mozilla Firefox", " — Firefox", " - Firefox"]:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()

        for suffix in [" - Google Chrome", " — Google Chrome"]:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()

        # Remove notification prefixes like (3) or (15)
        title = re.sub(r"^\(\d+\)\s*", "", title).strip()
        return title or f"{app_name} Tab"

    def _get_active_x11_window(self) -> Optional[Dict[str, str]]:
        try:
            root_out = subprocess.check_output(
                ['xprop', '-root', '_NET_ACTIVE_WINDOW'],
                stderr=subprocess.DEVNULL,
                timeout=0.5
            ).decode('utf-8', 'ignore')
            m = re.search(r'0x[0-9a-fA-F]+', root_out)
            if not m:
                return None
            win_id = m.group(0)
            if win_id == '0x0':
                return None

            out = subprocess.check_output(
                ['xprop', '-id', win_id],
                stderr=subprocess.DEVNULL,
                timeout=0.5
            ).decode('utf-8', 'ignore')

            title = ''
            app_name = ''
            for line in out.splitlines():
                if (line.startswith('_NET_WM_NAME(') or line.startswith('WM_NAME(')) and not title:
                    parts = line.split(' = ', 1)
                    if len(parts) == 2:
                        title = parts[1].strip('\"')
                elif line.startswith('WM_CLASS(') and not app_name:
                    parts = line.split(' = ', 1)
                    if len(parts) == 2:
                        classes = [c.strip('\" ') for c in parts[1].split(',')]
                        app_name = classes[-1] if classes else ''

            app_name = self._clean_app_name(app_name)
            title = self._clean_tab_title(title, app_name) if title else "Untitled"
            return {"app": app_name, "title": title}
        except Exception:
            return None

    def _clean_app_name(self, raw_app: str) -> str:
        raw_lower = raw_app.lower()
        if "firefox" in raw_lower:
            return "Firefox"
        elif "obsidian" in raw_lower:
            return "Obsidian"
        elif "thunderbird" in raw_lower:
            return "Thunderbird"
        elif "evolution" in raw_lower or "kmail" in raw_lower or "geary" in raw_lower:
            return "Mail"
        elif "mail" in raw_lower or "correo" in raw_lower:
            return "Mail"
        elif "code" in raw_lower or "vscode" in raw_lower:
            return "VS Code"
        elif "terminal" in raw_lower or "gnome-terminal" in raw_lower or "xterm" in raw_lower:
            return "Terminal"
        elif "nemo" in raw_lower or "nautilus" in raw_lower or "archivos" in raw_lower:
            return "Files"
        elif "antigravity" in raw_lower:
            return "Antigravity"
        elif "chrome" in raw_lower:
            return "Chrome"
        elif "slack" in raw_lower:
            return "Slack"
        elif "discord" in raw_lower:
            return "Discord"
        elif "libreoffice" in raw_lower or "soffice" in raw_lower:
            return "LibreOffice"
        return raw_app.capitalize() if raw_app else "Unknown"

    def get_app_icon(self, app_name: str) -> str:
        name_lower = app_name.lower()
        if "firefox" in name_lower:
            return "firefox"
        elif "obsidian" in name_lower:
            return "text-editor"
        elif "thunderbird" in name_lower or "mail" in name_lower or "correo" in name_lower:
            return "mail-client"
        elif "code" in name_lower:
            return "applications-development"
        elif "terminal" in name_lower:
            return "utilities-terminal"
        elif "files" in name_lower or "archivos" in name_lower:
            return "system-file-manager"
        elif "chrome" in name_lower:
            return "google-chrome"
        elif "slack" in name_lower:
            return "internet-chat"
        elif "libreoffice" in name_lower:
            return "x-office-document"
        elif "antigravity" in name_lower:
            return "applications-science"
        return "application-x-executable"

    def _is_ignored(self, app: str, title: str) -> bool:
        """Determines if an app or window title should be ignored as agent/internal noise."""
        app_l = (app or "").lower()
        title_l = (title or "").lower()
        ignored_tokens = ["antigravity", "main.py", "taumer", "trazos", "agy", "subagent", "xprop", "unknown"]
        for tok in ignored_tokens:
            if tok in app_l or tok in title_l:
                return True
        return False

    def _run_loop(self):
        last_app = ""
        last_title = ""
        start_time = time.time()
        current_event_id: Optional[int] = None
        last_heartbeat_time = time.time()

        while self.running:
            try:
                win = self._get_active_x11_window()
                current_time = time.time()

                if win:
                    app = win["app"]
                    title = win["title"]

                    if app != last_app or title != last_title:
                        # Finalize previous event if active
                        if current_event_id is not None and last_app:
                            duration = current_time - start_time
                            if duration >= 2.0:
                                self._update_event(current_event_id, current_time, duration)
                            else:
                                self._delete_event(current_event_id)
                            current_event_id = None

                        last_app = app
                        last_title = title
                        start_time = current_time
                        last_heartbeat_time = current_time

                        # Start tracking new event if not ignored
                        if not self._is_ignored(app, title):
                            current_event_id = self._insert_event(app, title, start_time)

                        # Find matching favicon if Firefox
                        fav_path = None
                        if app == "Firefox" and self._cached_tabs:
                            for tab in self._cached_tabs:
                                if tab.get("clean_title") and (tab["clean_title"] in title or title in tab["clean_title"]):
                                    fav_path = tab.get("favicon_path")
                                    break

                        self.current_window = {
                            "app": app,
                            "title": title,
                            "start_time": current_time,
                            "icon": self.get_app_icon(app),
                            "favicon_path": fav_path
                        }
                    else:
                        # Ongoing window focus (e.g. typing an email)
                        elapsed = current_time - start_time
                        self.current_window["duration"] = elapsed

                        # Heartbeat commit every 15 seconds to prevent losing sessions
                        if current_event_id is not None and (current_time - last_heartbeat_time) >= 15.0:
                            self._update_event(current_event_id, current_time, elapsed)
                            last_heartbeat_time = current_time
                else:
                    if current_event_id is not None and last_app:
                        duration = current_time - start_time
                        if duration >= 2.0:
                            self._update_event(current_event_id, current_time, duration)
                        else:
                            self._delete_event(current_event_id)
                        current_event_id = None
                        last_app = ""
                        last_title = ""

                    self.current_window = {
                        "app": "Desktop",
                        "title": "",
                        "start_time": current_time,
                        "icon": "user-desktop"
                    }
            except Exception:
                pass

            time.sleep(2.0)

    def _insert_event(self, app: str, title: str, start_time: float) -> Optional[int]:
        try:
            date_str = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d")
            dt_start = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
            conn = sqlite3.connect(LOCAL_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO window_events (app, title, start_time, end_time, duration_seconds, date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (app, title, dt_start, dt_start, 0.0, date_str))
            row_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return row_id
        except Exception:
            return None

    def _update_event(self, event_id: int, current_time: float, duration: float):
        try:
            dt_end = datetime.fromtimestamp(current_time).strftime("%Y-%m-%d %H:%M:%S")
            conn = sqlite3.connect(LOCAL_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE window_events
                SET end_time = ?, duration_seconds = ?
                WHERE id = ?
            """, (dt_end, duration, event_id))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _delete_event(self, event_id: int):
        try:
            conn = sqlite3.connect(LOCAL_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM window_events WHERE id = ?", (event_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _save_event(self, app: str, title: str, start_time: float, end_time: float, duration: float):
        if self._is_ignored(app, title):
            return
        try:
            date_str = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d")
            dt_start = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
            dt_end = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S")

            conn = sqlite3.connect(LOCAL_DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO window_events (app, title, start_time, end_time, duration_seconds, date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (app, title, dt_start, dt_end, duration, date_str))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error saving window event: {e}")

    def get_suggestions_today(self, limit: int = 20) -> List[Dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT app, title, SUM(duration_seconds) as total_dur, MAX(end_time) as last_seen
            FROM window_events
            WHERE date = ? 
              AND duration_seconds >= 60
              AND LOWER(app) NOT IN ('antigravity', 'main.py', 'taumer', 'trazos', 'agy', 'subagent', 'xprop', 'unknown')
              AND LOWER(title) NOT LIKE '%antigravity%'
              AND LOWER(title) NOT LIKE '%main.py%'
              AND LOWER(title) NOT LIKE '%taumer%'
              AND LOWER(title) NOT LIKE '%trazos%'
            GROUP BY app, title
            ORDER BY total_dur DESC
            LIMIT ?
        """, (today, limit))
        rows = cursor.fetchall()
        conn.close()

        results = []
        for app, title, dur, last_seen in rows:
            dur_mins = round(dur / 60, 1)
            fav_path = None
            if app == "Firefox" and self._cached_tabs:
                for tab in self._cached_tabs:
                    if tab.get("clean_title") and (tab["clean_title"] in title or title in tab["clean_title"]):
                        fav_path = tab.get("favicon_path")
                        break

            results.append({
                "app": app,
                "title": title,
                "duration_seconds": dur,
                "duration_minutes": dur_mins,
                "duration_text": self._format_duration(dur),
                "last_seen": last_seen,
                "icon": self.get_app_icon(app),
                "favicon_path": fav_path
            })
        return results

    def get_chronological_history_today(self, limit: int = 50) -> List[Dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect(LOCAL_DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, app, title, start_time, end_time, duration_seconds
            FROM window_events
            WHERE date = ? 
              AND duration_seconds >= 60
              AND LOWER(app) NOT IN ('antigravity', 'main.py', 'taumer', 'trazos', 'agy', 'subagent', 'xprop', 'unknown')
              AND LOWER(title) NOT LIKE '%antigravity%'
              AND LOWER(title) NOT LIKE '%main.py%'
              AND LOWER(title) NOT LIKE '%taumer%'
              AND LOWER(title) NOT LIKE '%trazos%'
            ORDER BY id DESC
            LIMIT ?
        """, (today, limit))
        rows = cursor.fetchall()
        conn.close()

        history = []
        for row_id, app, title, st, et, dur in rows:
            time_start = st.split(" ")[1][:5] if " " in st else st
            time_end = et.split(" ")[1][:5] if " " in et else et
            fav_path = None
            if app == "Firefox" and self._cached_tabs:
                for tab in self._cached_tabs:
                    if tab.get("clean_title") and (tab["clean_title"] in title or title in tab["clean_title"]):
                        fav_path = tab.get("favicon_path")
                        break

            history.append({
                "id": row_id,
                "app": app,
                "title": title,
                "time_range": f"{time_start} - {time_end}",
                "start_time": time_start,
                "duration_seconds": dur,
                "duration_minutes": max(1, round(dur / 60)),
                "duration_text": self._format_duration(dur),
                "icon": self.get_app_icon(app),
                "favicon_path": fav_path
            })
        return history

    def _format_duration(self, seconds: float) -> str:
        minutes = int(seconds // 60)
        hours = minutes // 60
        rem_mins = minutes % 60
        if hours > 0:
            return f"{hours}h {rem_mins}m"
        elif minutes > 0:
            return f"{minutes}m"
        else:
            return f"{int(seconds)}s"
