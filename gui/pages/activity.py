"""Activity Log page — timeline with 'where you stopped' + history."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFrame,
)
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtGui import QFont

from i18n import get_string as _t
from core.activity_tracker import ActivityTracker, serialize_activity
from core.models import ActivityEntry, FileChange, DockerChange, PortChange
from gui.copyable_widgets import make_copy_all_button

log = logging.getLogger(__name__)


class HaikuContextThread(QThread):
    """Background thread — asks Haiku for 'where you stopped' and activity summary."""

    result_ready = pyqtSignal(str, str)  # (haiku_context, haiku_summary)

    def __init__(self, entry: ActivityEntry, config: dict, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._config = config

    def run(self):
        try:
            from core.haiku_client import HaikuClient
            client = HaikuClient(config=self._config)
            if not client.is_available():
                self.result_ready.emit("", "")
                return

            lang = self._config.get("general", {}).get("language", "en")

            # Build activity summary text for Haiku
            parts = []
            if self._entry.files:
                file_list = ", ".join(f.path for f in self._entry.files[:10])
                parts.append(f"Files changed: {file_list}")
            if self._entry.commits:
                parts.append(f"Recent commits: {'; '.join(self._entry.commits[:3])}")
            if self._entry.docker_changes:
                docker_list = ", ".join(
                    f"{d.name} ({d.status})" for d in self._entry.docker_changes
                )
                parts.append(f"Docker: {docker_list}")
            if self._entry.port_changes:
                port_list = ", ".join(
                    f":{p.port} {p.status}" for p in self._entry.port_changes
                )
                parts.append(f"Ports: {port_list}")

            if not parts:
                self.result_ready.emit("", "")
                return

            activity_text = "\n".join(parts)

            # "Where you stopped" context
            context_prompt = (
                f"You are a developer assistant. Based on the recent activity in a project, "
                f"write a short 2-3 sentence summary in {lang} of 'where the developer left off'. "
                f"Be practical and specific. No fluff.\n\nActivity:\n{activity_text}"
            )
            haiku_context = client.ask(context_prompt, max_tokens=200) or ""

            # Short activity summary
            summary_prompt = (
                f"Summarize this developer activity in one sentence ({lang}). "
                f"Just the facts, what changed.\n\nActivity:\n{activity_text}"
            )
            haiku_summary = client.ask(summary_prompt, max_tokens=100) or ""

            self.result_ready.emit(haiku_context, haiku_summary)

        except Exception as e:
            log.error("HaikuContextThread error: %s", e)
            self.result_ready.emit("", "")


class ActivityPage(QWidget):
    """Activity Log — timeline with 'where you stopped' block and history."""

    refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._tracker: ActivityTracker | None = None
        self._config: dict = {}
        self._haiku_thread: HaikuContextThread | None = None
        self._all_texts: list[str] = []
        self._where_stopped_label: QLabel | None = None
        self._db = None
        self._build_ui()

    def set_config(self, config: dict) -> None:
        """Receive config (including Haiku API key)."""
        self._config = config

    def hide_dir_picker(self) -> None:
        """Hide per-page dir picker when shared project selector is active."""
        if hasattr(self, '_btn_select'):
            self._btn_select.hide()
        if hasattr(self, '_dir_label'):
            self._dir_label.hide()

    def _get_db(self):
        if self._db is None:
            from core.history import HistoryDB
            self._db = HistoryDB()
            self._db.init()
        return self._db

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header row: title + refresh + copy all
        header = QHBoxLayout()
        title = QLabel(_t("activity_header"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        header.addWidget(title)
        header.addStretch()

        copy_btn = make_copy_all_button(lambda: "\n".join(self._all_texts))
        header.addWidget(copy_btn)

        self._btn_refresh = QPushButton(_t("activity_btn_refresh"))
        self._btn_refresh.setStyleSheet(
            "QPushButton { padding: 4px 12px; }"
            "QPushButton:pressed { border: 2px inset #808080; }"
        )
        self._btn_refresh.clicked.connect(self._on_refresh)
        header.addWidget(self._btn_refresh)

        layout.addLayout(header)

        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px inset #808080; background: white; }")

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._content_widget)

        layout.addWidget(scroll)

        # Initial state
        self._show_placeholder(_t("activity_select_dir"))

    def _show_placeholder(self, text: str) -> None:
        self._clear_content()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #808080; font-size: 14px; padding: 40px;")
        self._content_layout.addWidget(lbl)

    def _clear_content(self) -> None:
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._all_texts = []
        self._where_stopped_label = None

    def set_project_dir(self, path: str) -> None:
        """Set project directory — called from shared project selector."""
        self._project_dir = path
        self._tracker = ActivityTracker(path)
        self._on_refresh()

    def _on_refresh(self) -> None:
        if not self._tracker or not self._project_dir:
            self._show_placeholder(_t("activity_select_dir"))
            return

        if shutil.which("git") is None:
            self._show_placeholder(_t("activity_git_not_found"))
            return

        self.refresh_requested.emit()

    def update_data(
        self,
        entry: ActivityEntry | None = None,
        docker_data: list[dict] | None = None,
        port_data: list[dict] | None = None,
    ) -> None:
        """Update page with fresh activity data. Compatible with app.py call signature."""
        if not self._tracker:
            return

        if entry is None:
            entry = self._tracker.collect_activity(
                docker_containers=docker_data,
                ports=port_data,
            )

        self._render_activity(entry)

        # Save to SQLite
        try:
            db = self._get_db()
            entry_json = serialize_activity(entry)
            db.save_activity(
                project_dir=entry.project_dir or self._project_dir or "",
                timestamp=entry.timestamp,
                entry_json=entry_json,
            )
        except Exception as e:
            log.error("Activity log save error: %s", e)

        # Trigger Haiku in background
        self._start_haiku_thread(entry)

    def _start_haiku_thread(self, entry: ActivityEntry) -> None:
        if self._haiku_thread and self._haiku_thread.isRunning():
            return

        self._haiku_thread = HaikuContextThread(entry, self._config, self)
        self._haiku_thread.result_ready.connect(self._on_haiku_ready)
        self._haiku_thread.start()

    def _on_haiku_ready(self, haiku_context: str, haiku_summary: str) -> None:
        """Update 'where you stopped' block with Haiku response."""
        if self._where_stopped_label is None:
            return

        if haiku_context:
            self._where_stopped_label.setText(haiku_context)
            self._where_stopped_label.setStyleSheet(
                "color: #333; font-size: 12px; padding: 4px;"
            )
            # Update texts for copy-all
            if haiku_context not in self._all_texts:
                self._all_texts.insert(0, haiku_context)

            # Save haiku context to last activity_log row
            try:
                db = self._get_db()
                if self._project_dir:
                    rows = db.get_activity_log(self._project_dir, limit=1)
                    if rows:
                        db._conn.execute(
                            "UPDATE activity_log SET haiku_context=?, haiku_summary=? WHERE id=?",
                            (haiku_context, haiku_summary, rows[0]["id"]),
                        )
                        db._conn.commit()
            except Exception as e:
                log.error("Haiku context save error: %s", e)

    def _render_activity(self, entry: ActivityEntry) -> None:
        """Render activity entry into the content area with timeline style."""
        self._clear_content()

        has_content = bool(
            entry.files or entry.docker_changes
            or entry.port_changes or entry.commits
        )

        # --- "Where you stopped" block ---
        where_box = QFrame()
        where_box.setStyleSheet(
            "QFrame { border: 2px solid #cccc00; background: #ffffcc; "
            "border-radius: 4px; padding: 6px; margin-bottom: 4px; }"
        )
        where_layout = QVBoxLayout(where_box)
        where_layout.setContentsMargins(8, 6, 8, 6)
        where_layout.setSpacing(4)

        where_title = QLabel(f"-- {_t('activity_where_stopped')} --")
        where_title.setStyleSheet("font-weight: bold; color: #806600; font-size: 12px;")
        where_layout.addWidget(where_title)

        self._where_stopped_label = QLabel(_t("activity_haiku_loading"))
        self._where_stopped_label.setStyleSheet("color: #808080; font-size: 11px; padding: 2px;")
        self._where_stopped_label.setWordWrap(True)
        where_layout.addWidget(self._where_stopped_label)

        self._content_layout.addWidget(where_box)
        self._all_texts.append(_t("activity_where_stopped"))

        if not self._tracker or not self._tracker.is_git_repo():
            self._where_stopped_label.setText(_t("activity_no_git"))
            self._content_layout.addStretch()
            return

        if not has_content:
            self._where_stopped_label.setText(_t("activity_no_changes"))
            # Still show recent commits even with no uncommitted changes
            commits = self._tracker.get_recent_commits(limit=10)
            if commits:
                group = self._make_group(f"{_t('activity_commits_header')} ({len(commits)})")
                group_layout = group.layout()
                for commit in commits:
                    lbl = QLabel(f"  {commit}")
                    lbl.setStyleSheet("font-family: monospace; color: #333;")
                    group_layout.addWidget(lbl)
                    self._all_texts.append(f"  {commit}")
                self._content_layout.addWidget(group)
            self._content_layout.addStretch()
            return

        # --- Timeline header ---
        ts = entry.timestamp
        try:
            dt = datetime.fromisoformat(ts)
            time_str = dt.strftime("%H:%M")
            date_str = _t("activity_today")
        except ValueError:
            time_str = ts
            date_str = ""

        ts_label = QLabel(f"{date_str}, {time_str}" if date_str else time_str)
        ts_label.setStyleSheet(
            "color: #000080; font-weight: bold; font-size: 12px; "
            "padding: 6px 0 2px 0; border-bottom: 1px solid #000080;"
        )
        self._content_layout.addWidget(ts_label)
        self._all_texts.append(ts_label.text())

        # Git files
        if entry.files:
            group = self._make_group(
                f"{_t('activity_files_header')} ({len(entry.files)})"
            )
            self._all_texts.append(f"{_t('activity_files_header')} ({len(entry.files)})")
            group_layout = group.layout()
            for fc in entry.files:
                row = self._make_file_row(fc)
                group_layout.addWidget(row)
                self._all_texts.append(f"{fc.status} {fc.path} {fc.explanation}")
            self._content_layout.addWidget(group)

        # Docker changes
        if entry.docker_changes:
            group = self._make_group(_t("activity_docker_header"))
            self._all_texts.append(_t("activity_docker_header"))
            group_layout = group.layout()
            for dc in entry.docker_changes:
                row = self._make_docker_row(dc)
                group_layout.addWidget(row)
                self._all_texts.append(f"{dc.name} ({dc.status}) {dc.explanation}")
            self._content_layout.addWidget(group)

        # Port changes
        if entry.port_changes:
            group = self._make_group(_t("activity_ports_header"))
            self._all_texts.append(_t("activity_ports_header"))
            group_layout = group.layout()
            for pc in entry.port_changes:
                row = self._make_port_row(pc)
                group_layout.addWidget(row)
                self._all_texts.append(f":{pc.port} {pc.status} {pc.explanation}")
            self._content_layout.addWidget(group)

        # Recent commits
        if entry.commits:
            group = self._make_group(_t("activity_commits_header"))
            self._all_texts.append(_t("activity_commits_header"))
            group_layout = group.layout()
            for commit in entry.commits:
                lbl = QLabel(f"  {commit}")
                lbl.setStyleSheet("font-family: monospace; color: #333;")
                group_layout.addWidget(lbl)
                self._all_texts.append(commit)
            self._content_layout.addWidget(group)

        self._content_layout.addStretch()

    def _make_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(
            "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
            "padding-top: 16px; font-weight: bold; background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        layout = QVBoxLayout(group)
        layout.setSpacing(2)
        return group

    def _make_file_row(self, fc: FileChange) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(1)

        top = QHBoxLayout()

        status_map = {
            "added": ("+", "#006600", _t("activity_file_added")),
            "modified": ("~", "#000080", _t("activity_file_modified")),
            "deleted": ("-", "#cc0000", _t("activity_file_deleted")),
            "renamed": ("R", "#806600", _t("activity_file_renamed")),
        }
        icon, color, label = status_map.get(fc.status, ("?", "#808080", fc.status))

        status_lbl = QLabel(icon)
        status_lbl.setFixedWidth(16)
        status_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-family: monospace;")
        top.addWidget(status_lbl)

        path_lbl = QLabel(fc.path)
        path_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        top.addWidget(path_lbl)

        if fc.status in ("added", "deleted"):
            tag = QLabel(f"({label})")
            tag.setStyleSheet(f"color: {color}; font-weight: bold;")
            top.addWidget(tag)

        top.addStretch()

        if fc.additions or fc.deletions:
            stats_parts = []
            if fc.additions:
                stats_parts.append(f"+{fc.additions}")
            if fc.deletions:
                stats_parts.append(f"-{fc.deletions}")
            stats_lbl = QLabel(" ".join(stats_parts))
            stats_lbl.setStyleSheet("color: #808080; font-family: monospace;")
            top.addWidget(stats_lbl)

        layout.addLayout(top)

        if fc.explanation:
            is_env = ".env" in fc.path.lower()
            expl_color = "#cc6600" if is_env else "#666666"
            prefix = "\u26a0\ufe0f " if is_env else "  "
            expl_text = _t("activity_env_warning") if is_env else fc.explanation

            expl_lbl = QLabel(f"{prefix}{expl_text}")
            expl_lbl.setStyleSheet(f"color: {expl_color}; font-size: 11px;")
            layout.addWidget(expl_lbl)

        return frame

    def _make_docker_row(self, dc: DockerChange) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)

        status_styles = {
            "new": ("+", "#006600"),
            "removed": ("-", "#cc0000"),
            "crashed": ("\u25cf", "#cc0000"),
            "restarted": ("\u25cf", "#cc6600"),
        }
        icon, color = status_styles.get(dc.status, ("?", "#808080"))

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(20)
        icon_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(dc.name)
        name_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(name_lbl)

        if dc.image:
            img_lbl = QLabel(f"({dc.image})")
            img_lbl.setStyleSheet("color: #808080;")
            layout.addWidget(img_lbl)

        layout.addStretch()

        status_text = {
            "new": _t("activity_docker_new"),
            "removed": _t("activity_docker_removed"),
            "crashed": _t("activity_docker_crashed"),
            "restarted": _t("activity_docker_restarted"),
        }.get(dc.status, dc.status)

        status_tag = QLabel(status_text)
        status_tag.setStyleSheet(
            f"color: {color}; font-weight: bold; "
            "border: 1px solid #808080; padding: 1px 4px;"
        )
        layout.addWidget(status_tag)

        if dc.explanation:
            expl = QLabel(dc.explanation)
            expl.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(expl)

        return frame

    def _make_port_row(self, pc: PortChange) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)

        is_new = pc.status == "new"
        color = "#006600" if is_new else "#cc0000"
        icon = "+" if is_new else "-"

        icon_lbl = QLabel(icon)
        icon_lbl.setFixedWidth(16)
        icon_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-family: monospace;")
        layout.addWidget(icon_lbl)

        port_lbl = QLabel(f":{pc.port}")
        port_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-family: monospace;")
        layout.addWidget(port_lbl)

        if pc.process:
            proc_lbl = QLabel(f"({pc.process})")
            proc_lbl.setStyleSheet("color: #808080;")
            layout.addWidget(proc_lbl)

        layout.addStretch()

        tag_text = _t("activity_port_new") if is_new else _t("activity_port_closed")
        tag = QLabel(tag_text)
        tag.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(tag)

        if pc.explanation:
            expl = QLabel(pc.explanation)
            expl.setStyleSheet("color: #666; font-size: 11px;")
            layout.addWidget(expl)

        return frame
