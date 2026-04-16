"""Frozen Files tab — lock files AI must not touch.

Shown inside SavePointsPage alongside Code and Environment tabs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QFileDialog, QInputDialog, QMessageBox,
)
from PyQt5.QtCore import Qt

from i18n import get_string as _t
from core.history import HistoryDB
from core import frozen_manager as fm

log = logging.getLogger(__name__)


class FrozenTab(QWidget):
    """List of frozen files + lock/unlock + hook toggle."""

    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._db: HistoryDB | None = None
        self._build_ui()
        self._refresh()

    def _get_db(self) -> HistoryDB:
        if self._db is None:
            self._db = HistoryDB()
            self._db.init()
        return self._db

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Hint
        hint = QLabel(_t("frozen_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color: #333; font-size: 12px; "
            "padding: 10px 12px; background: #fffff0; "
            "border: 2px solid #cccc00; border-radius: 4px;"
        )
        layout.addWidget(hint)

        # Actions
        actions = QHBoxLayout()
        self._btn_add = QPushButton(_t("frozen_add_btn"))
        self._btn_add.setStyleSheet(
            "QPushButton { background: #000080; color: white; padding: 6px 16px; "
            "border: 2px outset #4040c0; font-weight: bold; }"
            "QPushButton:pressed { border: 2px inset #000080; }"
        )
        self._btn_add.clicked.connect(self._on_add)
        actions.addWidget(self._btn_add)
        actions.addStretch()
        layout.addLayout(actions)

        # Hook status + toggle
        self._hook_status_lbl = QLabel("")
        self._hook_status_lbl.setStyleSheet("font-size: 11px; padding: 4px;")
        layout.addWidget(self._hook_status_lbl)

        self._btn_hook_toggle = QPushButton("")
        self._btn_hook_toggle.clicked.connect(self._on_toggle_hook)
        layout.addWidget(self._btn_hook_toggle)

        # Scroll of frozen files
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px inset #808080; background: white; }")
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

    # --- Public API ---

    def set_project_dir(self, path: str) -> None:
        self._project_dir = path
        self._btn_add.setEnabled(True)
        self._refresh()

    # --- Actions ---

    def _on_add(self) -> None:
        if not self._project_dir:
            return
        fp, _ok = QFileDialog.getOpenFileName(
            self, _t("frozen_add_title"), self._project_dir,
        )
        if not fp:
            return
        # Store as relative to project when possible
        try:
            rel = str(Path(fp).resolve().relative_to(
                Path(self._project_dir).resolve()))
        except ValueError:
            rel = fp

        note, _ = QInputDialog.getText(
            self, _t("frozen_add_title"), _t("frozen_note_prompt"),
        )
        self._get_db().add_frozen_file(self._project_dir, rel, note or "")
        self._sync_claude_md()
        self._refresh()

    def _on_unlock(self, path: str) -> None:
        if not self._project_dir:
            return
        self._get_db().remove_frozen_file(self._project_dir, path)
        self._sync_claude_md()
        self._refresh()

    def _on_toggle_hook(self) -> None:
        if fm.is_hook_installed():
            fm.uninstall_hook()
            QMessageBox.information(self, "Claude Code", _t("frozen_hook_removed"))
        else:
            if fm.install_hook():
                QMessageBox.information(self, "Claude Code", _t("frozen_hook_installed"))
        self._refresh()

    # --- Rendering ---

    def _sync_claude_md(self) -> None:
        if not self._project_dir:
            return
        frozen = self._get_db().get_frozen_files(self._project_dir)
        fm.sync_claude_md(self._project_dir, [f["path"] for f in frozen])

    def _refresh(self) -> None:
        self._render_hook_status()
        self._render_list()

    def _render_hook_status(self) -> None:
        installed = fm.is_hook_installed()
        if installed:
            self._hook_status_lbl.setText(_t("frozen_hook_on"))
            self._hook_status_lbl.setStyleSheet(
                "color: #006600; font-size: 11px; padding: 4px; font-weight: bold;"
            )
            self._btn_hook_toggle.setText(_t("frozen_hook_toggle_off"))
        else:
            self._hook_status_lbl.setText(_t("frozen_hook_off"))
            self._hook_status_lbl.setStyleSheet(
                "color: #808080; font-size: 11px; padding: 4px;"
            )
            self._btn_hook_toggle.setText(_t("frozen_hook_toggle_on"))

    def _render_list(self) -> None:
        # Clear
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._project_dir:
            self._show_placeholder(_t("snap_no_dir"))
            return

        frozen = self._get_db().get_frozen_files(self._project_dir)
        if not frozen:
            self._show_placeholder(_t("frozen_empty"))
            return

        for f in frozen:
            self._content_layout.addWidget(self._make_row(f))

    def _show_placeholder(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color: #808080; font-size: 13px; padding: 40px;"
        )
        self._content_layout.addWidget(lbl)

    def _make_row(self, f: dict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { border-bottom: 1px solid #e0e0e0; padding: 6px; }"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)

        lock_icon = QLabel("🔒")
        lock_icon.setStyleSheet("font-size: 16px;")
        layout.addWidget(lock_icon)

        info = QVBoxLayout()
        info.setSpacing(2)
        path_lbl = QLabel(f["path"])
        path_lbl.setStyleSheet("font-family: monospace; font-weight: bold; color: #000080;")
        info.addWidget(path_lbl)
        if f.get("note"):
            note_lbl = QLabel(f["note"])
            note_lbl.setStyleSheet("color: #555; font-size: 11px;")
            info.addWidget(note_lbl)
        info_widget = QWidget()
        info_widget.setLayout(info)
        layout.addWidget(info_widget, 1)

        btn_unlock = QPushButton(_t("frozen_unlock"))
        btn_unlock.setStyleSheet("QPushButton { font-size: 11px; padding: 2px 10px; }")
        btn_unlock.clicked.connect(lambda _, p=f["path"]: self._on_unlock(p))
        layout.addWidget(btn_unlock)

        return frame
