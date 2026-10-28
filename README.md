<p align="center">
  <img src="app/taumer.svg" width="220" alt="Taumer Logo" />
</p>

# Taumer 🦈

> **Native Linux Task, Focus & Activity Tracker with Seamless Obsidian Integration.**

Taumer is a lightweight productivity application designed for Linux (Linux Mint, Ubuntu, GNOME, and modern desktop environments). It merges deep-work focus sessions, calendar time-blocking, automatic window activity logging, and bidirectional Obsidian Markdown synchronization into an interface inspired by modern desktop UX and ASCII art aesthetics.

---

## ✨ Features

- **🦈 ASCII Shark Focus Timer**: An interactive focus and Pomodoro timer featuring animated ASCII shark visuals (adapted from [ascii-sharks](https://github.com/stackedlol/ascii-sharks)) that react to timer states and cursor interaction.
- **📅 Time-Blocking & Daily Planner**: Plan tasks, fixed events, and open-ended focus blocks directly on an interactive daily grid.
- **📓 Direct Obsidian Integration**:
  - Automatically exports daily journals formatted in clean Markdown (`Diario/YYYY-MM-DD.md`) with YAML frontmatter.
  - Maintains tasks in sync with Markdown checklists and structured storage (`Tareas/tareas.md`).
  - Generates weekly summaries and progress reports (`Reportes/`).
- **👀 Background Window & App Watcher**:
  - Automatically captures active application usage and browser tab titles (Firefox & Chromium-based browsers).
  - Automatically filters out internal tool noise and micro-interruptions (< 60s).

---

## 🛠️ Requirements & System Dependencies

Taumer is built with Python 3, GTK 4, Libadwaita, and WebKitGTK 6.0.

### Debian / Ubuntu / Linux Mint
```bash
sudo apt update
sudo apt install -y \
    python3 \
    python3-gi \
    python3-gi-cairo \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    gir1.2-webkit-6.0 \
    x11-utils \
    python3-yaml \
    python3-requests
```

---

## 🚀 Installation & Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/lazaro-guerrero-losada/Taumer.git
   cd Taumer
   ```

2. **Install desktop shortcut and CLI launcher:**
   ```bash
   ./install.sh
   ```
   This will configure `taumer` in your application menu and make the `taumer` terminal command available.

3. **Or run directly:**
   ```bash
   ./run.sh
   ```

---

## 📂 Project Structure

```text
├── app/
│   ├── main.py              # Application entry point & GTK lifecycle
│   ├── config.py            # Global paths, vault locations & settings
│   ├── models.py            # Task, JournalEntry, and Project dataclasses
│   ├── storage.py           # Obsidian Markdown parser and JSON sync
│   ├── watcher.py           # Native X11 window activity tracker
│   ├── style.css            # Custom styling & minimalist typography
│   ├── taumer.svg / .png    # Official application brand marks
│   └── ui/
│       ├── main_window.py   # Application window & navigation shell
│       ├── shark_home_view.py # ASCII Shark focus view (WebKit6)
│       ├── calendar_view.py # Interactive time-blocking calendar
│       ├── tasks_view.py    # Task management and project lists
│       ├── journal_view.py  # Daily timeline & activity reconciliation
│       ├── watcher_view.py  # App usage analytics & browser tabs
│       ├── reports_view.py  # Weekly reports generator
│       └── dialogs.py       # Task creation, completion & settings modals
├── install.sh               # One-click desktop installer
├── taumer.desktop           # Linux Desktop Entry file
├── run.sh                   # Main executable launcher
├── requirements.txt         # Python dependencies
└── README.md
```

---

## 🙏 Credits & Acknowledgments

- **ASCII Sharks Animation**: Special thanks to [stackedlol/ascii-sharks](https://github.com/stackedlol/ascii-sharks) for the interactive ASCII shark canvas and animations that power Taumer's focus timer.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.
