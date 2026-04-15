"""Activity Log page — shows git/docker/port changes in human language."""

from __future__ import annotations

import shutil
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFileDialog, QFrame,
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont

from i18n import get_string as _t
from core.activity_tracker import ActivityTracker
from core.models import ActivityEntry, FileChange, DockerChange, PortChange


class ActivityPage(QWidget):
    """Activity Log — what changed in the project environment."""

    refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._tracker: ActivityTracker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header row: title + dir picker + refresh
        header = QHBoxLayout()
        title = QLabel(_t("activity_header"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        header.addWidget(title)
        header.addStretch()

        self._dir_label = QLabel(_t("activity_no_dir"))
        self._dir_label.setStyleSheet("color: #808080;")
        header.addWidget(self._dir_label)

        self._btn_select = QPushButton(_t("activity_btn_select"))
        self._btn_select.clicked.connect(self._on_select_dir)
        header.addWidget(self._btn_select)

        self._btn_refresh = QPushButton(_t("activity_btn_refresh"))
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
        """Show a centered placeholder message."""
        self._clear_content()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #808080; font-size: 14px; padding: 40px;")
        self._content_layout.addWidget(lbl)

    def _clear_content(self) -> None:
        """Remove all widgets from content area."""
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _on_select_dir(self) -> None:
        """Open directory picker."""
        dir_path = QFileDialog.getExistingDirectory(
            self, _t("activity_btn_select"), str(Path.home()),
        )
        if dir_path:
            self.set_project_dir(dir_path)

    def set_project_dir(self, path: str) -> None:
        """Set project directory and refresh."""
        self._project_dir = path
        self._tracker = ActivityTracker(path)

        # Truncate long paths for display
        display = path
        if len(display) > 50:
            display = "..." + display[-47:]
        self._dir_label.setText(f"{_t('activity_dir_label')} {display}")
        self._dir_label.setStyleSheet("color: #000000;")

        self._on_refresh()

    def _on_refresh(self) -> None:
        """Collect and display activity."""
        if not self._tracker or not self._project_dir:
            self._show_placeholder(_t("activity_select_dir"))
            return

        # Check git
        git_available = shutil.which("git") is not None
        if not git_available:
            self._show_placeholder(_t("activity_git_not_found"))
            return

        self.refresh_requested.emit()

    def update_data(
        self,
        entry: ActivityEntry | None = None,
        docker_data: list[dict] | None = None,
        port_data: list[dict] | None = None,
    ) -> None:
        """Update the page with fresh activity data.

        Called from app.py refresh cycle.
        If entry is None, collects data from tracker.
        """
        if not self._tracker:
            return

        if entry is None:
            entry = self._tracker.collect_activity(
                docker_containers=docker_data,
                ports=port_data,
            )

        self._render_activity(entry)

    def _render_activity(self, entry: ActivityEntry) -> None:
        """Render activity entry into the content area."""
        self._clear_content()

        has_content = False

        # Git files
        if entry.files:
            has_content = True
            group = self._make_group(
                f"{_t('activity_files_header')} ({len(entry.files)})"
            )
            group_layout = group.layout()
            for fc in entry.files:
                row = self._make_file_row(fc)
                group_layout.addWidget(row)
            self._content_layout.addWidget(group)

        # Docker changes
        if entry.docker_changes:
            has_content = True
            group = self._make_group(_t("activity_docker_header"))
            group_layout = group.layout()
            for dc in entry.docker_changes:
                row = self._make_docker_row(dc)
                group_layout.addWidget(row)
            self._content_layout.addWidget(group)

        # Port changes
        if entry.port_changes:
            has_content = True
            group = self._make_group(_t("activity_ports_header"))
            group_layout = group.layout()
            for pc in entry.port_changes:
                row = self._make_port_row(pc)
                group_layout.addWidget(row)
            self._content_layout.addWidget(group)

        # Recent commits
        if entry.commits:
            has_content = True
            group = self._make_group(_t("activity_commits_header"))
            group_layout = group.layout()
            for commit in entry.commits:
                lbl = QLabel(f"  {commit}")
                lbl.setStyleSheet("font-family: monospace; color: #333;")
                group_layout.addWidget(lbl)
            self._content_layout.addWidget(group)

        if not has_content:
            if not self._tracker.is_git_repo():
                self._show_placeholder(_t("activity_no_git"))
            else:
                self._show_placeholder(_t("activity_no_changes"))

        self._content_layout.addStretch()

    def _make_group(self, title: str) -> QGroupBox:
        """Create a Win95-style group box."""
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
        """Create a row for a file change."""
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(1)

        # Line 1: status icon + path + stats
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

        # Line 2: explanation
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
        """Create a row for a docker change."""
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
        """Create a row for a port change."""
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
