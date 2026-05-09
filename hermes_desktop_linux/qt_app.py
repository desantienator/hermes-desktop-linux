from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from PySide6.QtCore import Qt, QThread, Signal, QSize
    from PySide6.QtGui import QAction, QFont, QIcon
    from PySide6.QtWidgets import (
        QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
        QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
        QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit,
        QSizePolicy, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
        QTextEdit, QToolBar, QVBoxLayout, QWidget, QComboBox, QCheckBox,
        QAbstractItemView,
    )
except ModuleNotFoundError as exc:  # pragma: no cover - exercised on user machines
    print(
        "Hermes Desktop Linux needs PySide6. On Arch: sudo pacman -S python-pyside6. "
        "Or use: python -m pip install PySide6",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

from .models import ConnectionProfile, ProfileStore
from .remote import SSHClient

SECTIONS = [
    ("Overview", "⌁"),
    ("Sessions", "◴"),
    ("Kanban", "▦"),
    ("Files", "▱"),
    ("Usage", "◌"),
    ("Skills", "✦"),
    ("Cron", "⏱"),
    ("Terminal", "▣"),
]

STYLE = """
QMainWindow, QWidget { background: #0d1117; color: #d8dee9; font-size: 13px; }
#Sidebar { background: #090c10; border-right: 1px solid #232b36; }
#Brand { color: #f2f5f8; font-size: 21px; font-weight: 800; padding: 18px 16px 2px; }
#SubBrand { color: #7d8794; padding: 0 16px 16px; }
QListWidget { background: transparent; border: none; outline: 0; padding: 8px; }
QListWidget::item { padding: 11px 12px; border-radius: 10px; color: #aeb7c2; }
QListWidget::item:selected { background: #172033; color: #ffffff; }
QListWidget::item:hover { background: #121923; }
#Topbar { background: #0d1117; border-bottom: 1px solid #232b36; }
#Title { color: #f2f5f8; font-size: 24px; font-weight: 800; }
#Status { color: #8b949e; }
QPushButton { background: #1f6feb; color: white; border: none; padding: 8px 12px; border-radius: 8px; font-weight: 600; }
QPushButton:hover { background: #388bfd; }
QPushButton:disabled { background: #29313d; color: #6e7681; }
QPushButton[secondary="true"] { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
QPushButton[secondary="true"]:hover { background: #30363d; }
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit { background: #0b1018; color: #d8dee9; border: 1px solid #30363d; border-radius: 8px; padding: 7px; selection-background-color: #1f6feb; }
QTableWidget { background: #0b1018; alternate-background-color: #101722; color: #d8dee9; gridline-color: #232b36; border: 1px solid #30363d; border-radius: 10px; }
QHeaderView::section { background: #151b23; color: #aeb7c2; border: none; border-bottom: 1px solid #30363d; padding: 8px; font-weight: 700; }
QSplitter::handle { background: #232b36; }
#Card { background: #111823; border: 1px solid #263244; border-radius: 14px; }
#CardTitle { color: #f2f5f8; font-size: 15px; font-weight: 800; }
#Muted { color: #8b949e; }
"""

class Worker(QThread):
    finished_ok = Signal(object, int)
    failed = Signal(str, int)

    def __init__(self, client: SSHClient, action: str, arg: str = "", payload: dict | None = None, timeout: int = 60):
        super().__init__()
        self.client = client
        self.action = action
        self.arg = arg
        self.payload = payload
        self.timeout = timeout

    def run(self) -> None:
        result = self.client.run_action(self.action, self.arg, self.payload, self.timeout)
        if result.ok:
            self.finished_ok.emit(result.data, result.elapsed_ms)
        else:
            self.failed.emit(result.error or "Unknown remote error", result.elapsed_ms)

class Card(QFrame):
    def __init__(self, title: str, value: str = "", subtitle: str = ""):
        super().__init__()
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        t = QLabel(title); t.setObjectName("CardTitle"); layout.addWidget(t)
        self.value = QLabel(value); self.value.setStyleSheet("font-size: 28px; font-weight: 800; color: #58a6ff;"); layout.addWidget(self.value)
        self.subtitle = QLabel(subtitle); self.subtitle.setObjectName("Muted"); self.subtitle.setWordWrap(True); layout.addWidget(self.subtitle)

class ProfileDialog(QDialog):
    def __init__(self, profile: ConnectionProfile, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connection profile")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(profile.name)
        self.host = QLineEdit(profile.host)
        self.user = QLineEdit(profile.user)
        self.port = QLineEdit(str(profile.port))
        self.home = QLineEdit(profile.hermes_home)
        self.alias = QLineEdit(profile.ssh_alias)
        for label, widget in [
            ("Name", self.name), ("Host", self.host), ("User", self.user),
            ("Port", self.port), ("Hermes home", self.home), ("SSH alias", self.alias)
        ]:
            form.addRow(label, widget)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def profile(self) -> ConnectionProfile:
        return ConnectionProfile(
            name=self.name.text().strip() or "local",
            host=self.host.text().strip() or "localhost",
            user=self.user.text().strip(),
            port=int(self.port.text().strip() or "22"),
            hermes_home=self.home.text().strip() or "~/.hermes",
            ssh_alias=self.alias.text().strip(),
        )

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hermes Desktop Linux")
        self.resize(1360, 860)
        self.store = ProfileStore()
        self.profiles = self.store.load()
        self.profile = self.profiles[0]
        self.client = SSHClient(self.profile)
        self.workers: list[Worker] = []
        self.current_file = ""
        self._build()
        self.show_section("Overview")

    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName("Sidebar"); sidebar.setFixedWidth(232)
        side = QVBoxLayout(sidebar); side.setContentsMargins(0,0,0,0)
        brand = QLabel("Hermes Desktop"); brand.setObjectName("Brand"); side.addWidget(brand)
        sub = QLabel("Linux native workspace"); sub.setObjectName("SubBrand"); side.addWidget(sub)
        self.nav = QListWidget(); side.addWidget(self.nav, 1)
        for name, icon in SECTIONS:
            QListWidgetItem(f"{icon}  {name}", self.nav)
        self.nav.currentRowChanged.connect(lambda r: self.show_section(SECTIONS[r][0]) if r >= 0 else None)
        outer.addWidget(sidebar)

        main = QWidget(); main_layout = QVBoxLayout(main); main_layout.setContentsMargins(0,0,0,0); main_layout.setSpacing(0)
        top = QFrame(); top.setObjectName("Topbar"); top_l = QHBoxLayout(top); top_l.setContentsMargins(24,14,24,14)
        self.title = QLabel(""); self.title.setObjectName("Title"); top_l.addWidget(self.title)
        top_l.addStretch()
        self.profile_box = QComboBox(); self.profile_box.addItems([p.name for p in self.profiles]); self.profile_box.currentTextChanged.connect(self.switch_profile); top_l.addWidget(self.profile_box)
        self.edit_profile_btn = QPushButton("Edit profile"); self.edit_profile_btn.setProperty("secondary", True); self.edit_profile_btn.clicked.connect(self.edit_profile); top_l.addWidget(self.edit_profile_btn)
        self.refresh_btn = QPushButton("Refresh"); self.refresh_btn.clicked.connect(self.refresh); top_l.addWidget(self.refresh_btn)
        main_layout.addWidget(top)
        self.stack = QStackedWidget(); main_layout.addWidget(self.stack, 1)
        self.status = QLabel("Ready"); self.status.setObjectName("Status"); self.status.setStyleSheet("padding: 8px 24px; border-top: 1px solid #232b36;"); main_layout.addWidget(self.status)
        outer.addWidget(main, 1)

        self.pages: dict[str, QWidget] = {}
        for name, _ in SECTIONS:
            page = QWidget(); page.setProperty("section", name)
            page.setLayout(QVBoxLayout()); page.layout().setContentsMargins(24,24,24,24); page.layout().setSpacing(14)
            self.pages[name] = page; self.stack.addWidget(page)

    def clear_page(self, name: str):
        layout = self.pages[name].layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def show_section(self, name: str):
        self.current_section = name
        self.title.setText(name)
        self.stack.setCurrentWidget(self.pages[name])
        idx = [n for n,_ in SECTIONS].index(name)
        if self.nav.currentRow() != idx: self.nav.setCurrentRow(idx)
        getattr(self, f"build_{name.lower()}")()

    def refresh(self):
        self.show_section(getattr(self, "current_section", "Overview"))

    def run_remote(self, action: str, on_ok, arg: str = "", payload: dict | None = None, timeout: int = 60):
        self.status.setText(f"Running {action} on {self.profile.target}…")
        self.refresh_btn.setDisabled(True)
        w = Worker(self.client, action, arg, payload, timeout)
        self.workers.append(w)
        def ok(data, ms):
            self.status.setText(f"{action} complete in {ms}ms")
            self.refresh_btn.setDisabled(False)
            on_ok(data)
            self.workers.remove(w)
        def fail(err, ms):
            self.status.setText(f"{action} failed in {ms}ms")
            self.refresh_btn.setDisabled(False)
            QMessageBox.critical(self, "Remote action failed", err[:5000])
            self.workers.remove(w)
        w.finished_ok.connect(ok); w.failed.connect(fail); w.start()

    def switch_profile(self, name: str):
        if not name: return
        self.profile = next(p for p in self.profiles if p.name == name)
        self.client = SSHClient(self.profile)
        self.refresh()

    def edit_profile(self):
        dlg = ProfileDialog(self.profile, self)
        if dlg.exec() == QDialog.Accepted:
            try: p = dlg.profile()
            except ValueError:
                QMessageBox.warning(self, "Invalid profile", "Port must be a number."); return
            self.profiles = [x for x in self.profiles if x.name != self.profile.name] + [p]
            self.store.save(self.profiles)
            self.profile = p; self.client = SSHClient(p)
            self.profile_box.clear(); self.profile_box.addItems([x.name for x in self.profiles]); self.profile_box.setCurrentText(p.name)
            self.refresh()

    def table(self, headers: list[str]) -> QTableWidget:
        t = QTableWidget(0, len(headers)); t.setHorizontalHeaderLabels(headers); t.setAlternatingRowColors(True); t.setSelectionBehavior(QAbstractItemView.SelectRows); t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setVisible(False)
        return t

    def build_overview(self):
        self.clear_page("Overview"); page = self.pages["Overview"]; layout = page.layout()
        cards = QHBoxLayout(); layout.addLayout(cards)
        host = Card("Host", "…", self.profile.target); python = Card("Python", "…", "remote interpreter"); hermes = Card("Hermes", "…", "binary discovery"); home = Card("Hermes home", self.profile.hermes_home, "active workspace")
        for c in [host, python, hermes, home]: cards.addWidget(c)
        details = QTextEdit(); details.setReadOnly(True); layout.addWidget(details, 1)
        def fill(data):
            host.value.setText(data.get("host", "unknown")); python.value.setText(data.get("python", "?")); hermes.value.setText("found" if data.get("has_hermes") else "missing")
            home.value.setText(data.get("hermes_home", self.profile.hermes_home)); details.setPlainText(json.dumps(data, indent=2))
        self.run_remote("overview", fill)

    def build_usage(self):
        self.clear_page("Usage"); layout = self.pages["Usage"].layout()
        row = QHBoxLayout(); layout.addLayout(row)
        sessions = Card("Session files", "…"); bytes_card = Card("Bytes indexed", "…"); row.addWidget(sessions); row.addWidget(bytes_card)
        table = self.table(["Recent", "Path", "Size"]); layout.addWidget(table, 1)
        def fill(data):
            sessions.value.setText(str(data.get("session_files", 0))); bytes_card.value.setText(f"{data.get('bytes',0):,}")
            self.populate_table(table, [[x.get('name',''), x.get('path',''), x.get('size','')] for x in data.get('recent',[])])
        self.run_remote("usage", fill)

    def build_sessions(self):
        self.clear_page("Sessions"); layout = self.pages["Sessions"].layout(); split = QSplitter(); layout.addWidget(split, 1)
        table = self.table(["Session", "Modified", "Size", "Path"]); detail = QPlainTextEdit(); detail.setReadOnly(True)
        split.addWidget(table); split.addWidget(detail); split.setSizes([520,760])
        paths: list[str] = []
        def fill(data):
            paths.clear(); rows=[]
            for x in data:
                paths.append(x.get('path','')); rows.append([x.get('name',''), str(int(x.get('mtime',0))), x.get('size',''), x.get('path','')])
            self.populate_table(table, rows)
        def open_row(row, _):
            if row < len(paths): self.run_remote("read", lambda d: detail.setPlainText(d.get('content') or ''), paths[row])
        table.cellDoubleClicked.connect(open_row)
        self.run_remote("sessions", fill)

    def build_skills(self):
        self.clear_page("Skills"); layout = self.pages["Skills"].layout(); split = QSplitter(); layout.addWidget(split, 1)
        table = self.table(["Skill", "Description", "Path"]); detail = QPlainTextEdit(); detail.setReadOnly(True)
        split.addWidget(table); split.addWidget(detail); split.setSizes([520,760])
        paths=[]
        def fill(data):
            paths.clear(); rows=[]
            for x in data:
                paths.append(x.get('path','')); rows.append([x.get('name',''), x.get('description',''), x.get('path','')])
            self.populate_table(table, rows)
        table.cellDoubleClicked.connect(lambda r,_: self.run_remote("read", lambda d: detail.setPlainText(d.get('content') or ''), paths[r]) if r < len(paths) else None)
        self.run_remote("skills", fill)

    def build_files(self):
        self.clear_page("Files"); layout = self.pages["Files"].layout()
        bar = QHBoxLayout(); layout.addLayout(bar)
        path = QLineEdit(self.profile.hermes_home); bar.addWidget(path, 1)
        open_btn = QPushButton("Open directory"); bar.addWidget(open_btn)
        save_btn = QPushButton("Save file"); save_btn.setProperty("secondary", True); bar.addWidget(save_btn)
        split = QSplitter(); layout.addWidget(split, 1)
        table = self.table(["Name", "Kind", "Size", "Path"]); editor = QPlainTextEdit(); editor.setPlaceholderText("Double-click a file to edit it. Saves are limited to HERMES_HOME.")
        split.addWidget(table); split.addWidget(editor); split.setSizes([460,820])
        paths=[]; dirs=[]
        def load_dir(p):
            def fill(data):
                paths.clear(); dirs.clear(); rows=[]
                for x in data:
                    paths.append(x.get('path','')); dirs.append(bool(x.get('is_dir'))); rows.append([x.get('name',''), 'dir' if x.get('is_dir') else 'file', x.get('size',''), x.get('path','')])
                self.populate_table(table, rows)
            self.run_remote("files", fill, p)
        def open_row(row, _):
            if row >= len(paths): return
            if dirs[row]: path.setText(paths[row]); load_dir(paths[row])
            else:
                self.current_file = paths[row]
                self.run_remote("read", lambda d: editor.setPlainText(d.get('content') or ''), paths[row])
        def save():
            if not self.current_file: return
            if QMessageBox.question(self, "Save remote file?", self.current_file) == QMessageBox.Yes:
                self.run_remote("write", lambda _: self.status.setText("Saved " + self.current_file), self.current_file, {"content": editor.toPlainText()})
        open_btn.clicked.connect(lambda: load_dir(path.text().strip() or self.profile.hermes_home)); table.cellDoubleClicked.connect(open_row); save_btn.clicked.connect(save)
        load_dir(path.text())

    def build_kanban(self):
        self.clear_page("Kanban"); layout = self.pages["Kanban"].layout()
        hint = QLabel("Kanban board data from ~/.hermes/kanban.db. Mutations are next pass; this view now actually loads the board instead of pretending."); hint.setObjectName("Muted"); layout.addWidget(hint)
        split = QSplitter(); layout.addWidget(split, 1)
        tasks = self.table(["Title/Name", "Status", "Assignee", "ID"]); raw = QPlainTextEdit(); raw.setReadOnly(True)
        split.addWidget(tasks); split.addWidget(raw); split.setSizes([700,500])
        def fill(data):
            rows=[]
            for x in data.get('tasks',[]): rows.append([x.get('title') or x.get('name') or x.get('summary') or '', x.get('status') or x.get('state') or '', x.get('assignee') or '', x.get('id') or x.get('task_id') or ''])
            self.populate_table(tasks, rows); raw.setPlainText(json.dumps(data, indent=2, default=str))
        self.run_remote("kanban", fill)

    def build_cron(self):
        self.clear_page("Cron"); layout = self.pages["Cron"].layout()
        table = self.table(["ID", "Name", "Schedule", "Enabled/State"]); layout.addWidget(table, 1)
        raw = QPlainTextEdit(); raw.setReadOnly(True); layout.addWidget(raw, 1)
        def fill(data):
            jobs = data.get('jobs', data if isinstance(data, list) else []) if data else []
            rows=[]
            for j in jobs if isinstance(jobs, list) else []: rows.append([j.get('id',''), j.get('name') or j.get('raw',''), str(j.get('schedule','')), str(j.get('enabled', j.get('state','')))])
            self.populate_table(table, rows); raw.setPlainText(data.get('raw') if isinstance(data, dict) and data.get('raw') else json.dumps(data, indent=2, default=str))
        self.run_remote("cron", fill)

    def build_terminal(self):
        self.clear_page("Terminal"); layout = self.pages["Terminal"].layout()
        card = Card("Terminal", "External", "Launches a real Linux terminal into the active Hermes host. Embedded PTY is a future upgrade."); layout.addWidget(card)
        btn = QPushButton(f"Open terminal: {self.profile.target}"); layout.addWidget(btn, 0, Qt.AlignLeft); layout.addStretch()
        btn.clicked.connect(self.open_terminal)

    def open_terminal(self):
        terminals = [["x-terminal-emulator", "-e"], ["konsole", "-e"], ["gnome-terminal", "--"], ["xfce4-terminal", "-e"], ["kitty"], ["alacritty", "-e"], ["xterm", "-e"]]
        if self.profile.host in ("localhost", "127.0.0.1", "::1") and not self.profile.ssh_alias:
            command = ["bash"]
        else:
            command = ["ssh", "-p", str(self.profile.port), self.profile.target]
        for term in terminals:
            if shutil.which(term[0]):
                subprocess.Popen(term + command); return
        QMessageBox.information(self, "No terminal found", "Install kitty, alacritty, konsole, gnome-terminal, xterm, or x-terminal-emulator.")

    def populate_table(self, table: QTableWidget, rows: list[list[Any]]):
        table.setRowCount(0)
        for r, row in enumerate(rows):
            table.insertRow(r)
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setToolTip(str(val))
                table.setItem(r, c, item)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Hermes Desktop Linux")
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
