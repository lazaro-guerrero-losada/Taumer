"""
Watcher View: Split Master-Detail layout for live Firefox tabs with website favicons,
active windows, and chronological activity timeline with 1-click Obsidian journal logging.
Refined English localization, deduplicated favicons, and Apple HIG styling.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Pango
import os
from datetime import datetime

from watcher import WindowWatcher
from ui.dialogs import NewJournalEntryDialog

class WatcherView(Gtk.Box):
    def __init__(self, watcher: WindowWatcher, storage):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self.watcher = watcher
        self.storage = storage
        self.right_tab_mode = "suggestions"  # "suggestions" or "history"

        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(22)
        self.set_margin_end(22)

        self._build_ui()
        self.refresh()

        GLib.timeout_add_seconds(3, self._on_live_tick)

    def _build_ui(self):
        # 1. Top Header Bar
        top_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        lbl_title = Gtk.Label(label="Windows & Tabs Monitor")
        lbl_title.add_css_class("text-heading")
        lbl_title.set_halign(Gtk.Align.START)
        lbl_sub = Gtk.Label(label="Live Firefox open tabs with deduplicated website favicons and system activity.")
        lbl_sub.add_css_class("text-muted")
        lbl_sub.set_halign(Gtk.Align.START)
        title_box.append(lbl_title)
        title_box.append(lbl_sub)
        top_bar.append(title_box)

        top_bar.append(Gtk.Box(hexpand=True))

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.add_css_class("btn-secondary")
        refresh_btn.connect("clicked", lambda b: self.refresh())
        top_bar.append(refresh_btn)

        self.append(top_bar)

        # 2. Live Active Window Banner
        self.live_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.live_card.add_css_class("card-box-accent")

        self.app_icon_img = Gtk.Image.new_from_icon_name("application-x-executable")
        self.app_icon_img.set_pixel_size(28)
        self.live_card.append(self.app_icon_img)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_hexpand(True)

        self.curr_app_lbl = Gtk.Label(label="Active Window: Detecting...")
        self.curr_app_lbl.add_css_class("text-title")
        self.curr_app_lbl.set_halign(Gtk.Align.START)
        info_box.append(self.curr_app_lbl)

        self.curr_title_lbl = Gtk.Label(label="")
        self.curr_title_lbl.add_css_class("text-muted")
        self.curr_title_lbl.set_halign(Gtk.Align.START)
        self.curr_title_lbl.set_wrap(True)
        info_box.append(self.curr_title_lbl)

        self.live_card.append(info_box)

        quick_log_btn = Gtk.Button(label="Log Current Window")
        quick_log_btn.add_css_class("btn-primary")
        quick_log_btn.connect("clicked", self._log_active_window)
        self.live_card.append(quick_log_btn)

        self.append(self.live_card)

        # 3. Two-Column Split Layout (Left: Firefox Tabs, Right: Suggestions & History)
        split_paned = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        split_paned.set_vexpand(True)
        split_paned.set_hexpand(True)
        self.append(split_paned)

        # --- Left Column: Open Firefox Tabs ---
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left_box.set_size_request(400, -1)
        left_box.add_css_class("card-box")

        l_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        lbl_ff = Gtk.Label(label="Firefox Open Tabs")
        lbl_ff.add_css_class("text-title")
        l_head.append(lbl_ff)

        l_head.append(Gtk.Box(hexpand=True))

        self.tabs_count_lbl = Gtk.Label(label="0 tabs")
        self.tabs_count_lbl.add_css_class("tag-pill")
        l_head.append(self.tabs_count_lbl)
        left_box.append(l_head)

        lbl_ff_hint = Gtk.Label(label="Click any tab to log it to your daily Obsidian journal:")
        lbl_ff_hint.add_css_class("text-muted")
        lbl_ff_hint.set_halign(Gtk.Align.START)
        left_box.append(lbl_ff_hint)

        self.tabs_scrolled = Gtk.ScrolledWindow()
        self.tabs_scrolled.set_vexpand(True)
        self.tabs_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.tabs_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.tabs_scrolled.set_child(self.tabs_container)
        left_box.append(self.tabs_scrolled)

        split_paned.append(left_box)

        # --- Right Column: Suggestions & Chronological History ---
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right_box.set_hexpand(True)
        right_box.add_css_class("card-box")

        # Top switcher of right column
        r_head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_r = Gtk.Label(label="System Activity")
        lbl_r.add_css_class("text-title")
        r_head.append(lbl_r)

        r_head.append(Gtk.Box(hexpand=True))

        self.right_mode_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.right_mode_bar.add_css_class("segmented-bar")

        self.btn_sugg = Gtk.Button(label="Daily Suggestions")
        self.btn_sugg.add_css_class("segmented-btn")
        self.btn_sugg.add_css_class("active")
        self.btn_sugg.connect("clicked", lambda b: self._switch_right_tab("suggestions"))
        self.right_mode_bar.append(self.btn_sugg)

        self.btn_hist = Gtk.Button(label="Session History")
        self.btn_hist.add_css_class("segmented-btn")
        self.btn_hist.connect("clicked", lambda b: self._switch_right_tab("history"))
        self.right_mode_bar.append(self.btn_hist)

        r_head.append(self.right_mode_bar)

        btn_refresh_right = Gtk.Button(label="⟳ Refresh")
        btn_refresh_right.add_css_class("btn-secondary")
        btn_refresh_right.set_tooltip_text("Refresh system activity and session history")
        btn_refresh_right.connect("clicked", lambda b: self.refresh())
        r_head.append(btn_refresh_right)

        right_box.append(r_head)

        self.activity_scrolled = Gtk.ScrolledWindow()
        self.activity_scrolled.set_vexpand(True)
        self.activity_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.activity_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.activity_scrolled.set_child(self.activity_container)
        right_box.append(self.activity_scrolled)

        split_paned.append(right_box)

    def _switch_right_tab(self, mode: str):
        self.right_tab_mode = mode
        if mode == "suggestions":
            self.btn_sugg.add_css_class("active")
            self.btn_hist.remove_css_class("active")
        else:
            self.btn_hist.add_css_class("active")
            self.btn_sugg.remove_css_class("active")
        self._render_right_column()

    def _on_live_tick(self) -> bool:
        cur = self.watcher.current_window
        app = cur.get("app", "Unknown")
        title = cur.get("title", "")
        icon = cur.get("icon", "application-x-executable")
        fav_path = cur.get("favicon_path")

        self.curr_app_lbl.set_text(f"Active Window: {app}")
        self.curr_title_lbl.set_text(title or "(Desktop)")

        # Render website favicon if active window is Firefox with known favicon
        icon_set = False
        if fav_path and os.path.exists(fav_path):
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(fav_path, 28, 28, True)
                self.app_icon_img.set_from_pixbuf(pix)
                icon_set = True
            except Exception:
                pass

        if not icon_set:
            self.app_icon_img.set_from_icon_name(icon)

        return True

    def _log_active_window(self, btn):
        cur = self.watcher.current_window
        title = cur.get("title", "") or cur.get("app", "")
        self._open_log_prefilled(title, f"Active session in {cur.get('app', '')}", 25)

    def refresh(self):
        self._render_firefox_tabs()
        self._render_right_column()

    def _render_firefox_tabs(self):
        while child := self.tabs_container.get_first_child():
            self.tabs_container.remove(child)

        tabs = self.watcher.get_firefox_open_tabs()
        self.tabs_count_lbl.set_text(f"{len(tabs)} tabs")

        if not tabs:
            empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            empty.set_margin_top(20)
            lbl = Gtk.Label(label="No open Firefox tabs detected")
            lbl.add_css_class("text-muted")
            empty.append(lbl)
            self.tabs_container.append(empty)
            return

        for tab in tabs:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            card.add_css_class("card-box-accent")

            top_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            
            # 1. Custom Website Favicon with Fallback
            fav_path = tab.get("favicon_path")
            icon_widget = None
            if fav_path and os.path.exists(fav_path):
                try:
                    pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(fav_path, 18, 18, True)
                    icon_widget = Gtk.Image.new_from_pixbuf(pix)
                except Exception:
                    icon_widget = None

            if not icon_widget:
                icon_widget = Gtk.Image.new_from_icon_name("firefox")
                icon_widget.set_pixel_size(18)

            top_line.append(icon_widget)

            # 2. Clean Tab Title
            t_lbl = Gtk.Label(label=tab["clean_title"])
            t_lbl.add_css_class("text-title")
            t_lbl.set_halign(Gtk.Align.START)
            t_lbl.set_hexpand(True)
            t_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            t_lbl.set_max_width_chars(45)
            top_line.append(t_lbl)

            # 3. Domain Pill for quick recognition
            if tab.get("domain"):
                dom_lbl = Gtk.Label(label=tab["domain"])
                dom_lbl.add_css_class("tag-pill")
                top_line.append(dom_lbl)

            # 4. Action Button
            log_btn = Gtk.Button(label="+ To Journal")
            log_btn.add_css_class("btn-secondary")
            log_btn.connect("clicked", lambda b, t=tab: self._open_log_prefilled(t["clean_title"], f"Firefox Tab: {t['url']}", 30))
            top_line.append(log_btn)

            card.append(top_line)

            # URL snippet
            url_str = tab["url"]
            if len(url_str) > 60:
                url_str = url_str[:60] + "..."
            u_lbl = Gtk.Label(label=url_str)
            u_lbl.add_css_class("text-muted")
            u_lbl.set_halign(Gtk.Align.START)
            card.append(u_lbl)

            self.tabs_container.append(card)

    def _render_right_column(self):
        while child := self.activity_container.get_first_child():
            self.activity_container.remove(child)

        if self.right_tab_mode == "suggestions":
            items = self.watcher.get_suggestions_today(limit=25)
            if not items:
                lbl = Gtk.Label(label="No window activity recorded yet today")
                lbl.add_css_class("text-muted")
                lbl.set_margin_top(20)
                self.activity_container.append(lbl)
                return

            for it in items:
                card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                card.add_css_class("card-box-accent")

                # Favicon if available, else system app icon
                fav_path = it.get("favicon_path")
                img_widget = None
                if fav_path and os.path.exists(fav_path):
                    try:
                        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(fav_path, 20, 20, True)
                        img_widget = Gtk.Image.new_from_pixbuf(pix)
                    except Exception:
                        pass

                if not img_widget:
                    img_widget = Gtk.Image.new_from_icon_name(it["icon"])
                    img_widget.set_pixel_size(20)

                card.append(img_widget)

                d_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                d_box.set_hexpand(True)

                h_line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
                app_lbl = Gtk.Label(label=it["app"])
                app_lbl.add_css_class("text-title")
                h_line.append(app_lbl)

                dur_pill = Gtk.Label(label=it["duration_text"])
                dur_pill.add_css_class("tag-pill")
                h_line.append(dur_pill)
                d_box.append(h_line)

                t_lbl = Gtk.Label(label=it["title"])
                t_lbl.add_css_class("text-muted")
                t_lbl.set_halign(Gtk.Align.START)
                t_lbl.set_wrap(True)
                t_lbl.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                t_lbl.set_ellipsize(Pango.EllipsizeMode.END)
                t_lbl.set_max_width_chars(50)
                d_box.append(t_lbl)
                card.append(d_box)

                add_b = Gtk.Button(label="+ To Journal")
                add_b.add_css_class("btn-secondary")
                add_b.connect("clicked", lambda b, item=it: self._open_log_prefilled(
                    item["title"], f"Session in {item['app']}", max(5, int(round(item['duration_minutes'])))
                ))
                card.append(add_b)

                self.activity_container.append(card)
        else:
            history = self.watcher.get_chronological_history_today(limit=40)
            if not history:
                lbl = Gtk.Label(label="No sessions recorded yet")
                lbl.add_css_class("text-muted")
                lbl.set_margin_top(20)
                self.activity_container.append(lbl)
                return

            for h in history:
                card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                card.add_css_class("card-box-accent")

                t_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
                t_box.set_size_request(80, -1)
                tl = Gtk.Label(label=h["time_range"])
                tl.add_css_class("text-mono")
                dl = Gtk.Label(label=h["duration_text"])
                dl.add_css_class("tag-pill")
                t_box.append(tl)
                t_box.append(dl)
                card.append(t_box)

                # Favicon if available, else system app icon
                fav_path = h.get("favicon_path")
                img_widget = None
                if fav_path and os.path.exists(fav_path):
                    try:
                        pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(fav_path, 20, 20, True)
                        img_widget = Gtk.Image.new_from_pixbuf(pix)
                    except Exception:
                        pass

                if not img_widget:
                    img_widget = Gtk.Image.new_from_icon_name(h["icon"])
                    img_widget.set_pixel_size(20)

                card.append(img_widget)

                d_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
                d_box.set_hexpand(True)
                app_l = Gtk.Label(label=h["app"])
                app_l.add_css_class("text-title")
                app_l.set_halign(Gtk.Align.START)
                d_box.append(app_l)

                tit_l = Gtk.Label(label=h["title"])
                tit_l.add_css_class("text-muted")
                tit_l.set_halign(Gtk.Align.START)
                tit_l.set_wrap(True)
                tit_l.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                tit_l.set_ellipsize(Pango.EllipsizeMode.END)
                tit_l.set_max_width_chars(50)
                d_box.append(tit_l)
                card.append(d_box)

                btn_add = Gtk.Button(label="+")
                btn_add.add_css_class("btn-secondary")
                btn_add.set_tooltip_text("Add this session to daily journal")
                btn_add.connect("clicked", lambda b, it=h: self._open_log_prefilled(
                    it["title"], f"Session in {it['app']}", it["duration_minutes"], it["start_time"]
                ))
                card.append(btn_add)

                self.activity_container.append(card)

    def _open_log_prefilled(self, title: str, description: str, duration_mins: int, start_time: str = None):
        prefill = {
            "title": title,
            "description": description,
            "duration_minutes": duration_mins,
            "start_time": start_time or datetime.now().strftime("%H:%M"),
            "source": "window_tracker"
        }
        for p in self.storage.get_projects():
            if p.name.lower() in title.lower():
                prefill["project"] = p.name
                break

        win = self.get_root()
        dlg = NewJournalEntryDialog(win, self.storage, None, prefill=prefill)
        dlg.present()
