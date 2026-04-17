"""Frozen Files tab — lock files AI must not touch.

Shown inside SavePointsPage alongside Code and Environment tabs.

Locking is one-click: picking a file writes it into ``CLAUDE.md`` AND
installs the PreToolUse hook automatically if it isn't already. There is
no separate "enable hard block" toggle — hard block is the default.
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
from gui.win95 import (
    BUTTON_STYLE, FONT_MONO, HINT_STRIP_STYLE, PRIMARY_BUTTON_STYLE,
    SHADOW, SUNKEN_FRAME_STYLE, TITLE_DARK,
)

log = logging.getLogger(__name__)


class FrozenTab(QWidget):
    """List of frozen files + add/unlock. Hook installs automatically."""

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
        hint.setStyleSheet(HINT_STRIP_STYLE)
        layout.addWidget(hint)

        # Action — single Add button. Hook is auto-installed on first add.
        actions = QHBoxLayout()
        self._btn_add = QPushButton(_t("frozen_add_btn"))
        self._btn_add.setStyleSheet(PRIMARY_BUTTON_STYLE)
        self._btn_add.clicked.connect(self._on_add)
        actions.addWidget(self._btn_add)
        actions.addStretch()
        layout.addLayout(actions)

        # Scroll of frozen files
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 2px inset {SHADOW}; background: white; }}"
        )
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
        self._ensure_hook_installed()
        self._refresh()

    def _on_unlock(self, path: str) -> None:
        if not self._project_dir:
            return
        self._get_db().remove_frozen_file(self._project_dir, path)
        self._sync_claude_md()
        self._refresh()

    def _ensure_hook_installed(self) -> None:
        """Install the PreToolUse hook on first lock; silent if already there."""
        if fm.is_hook_installed():
            return
        if not fm.install_hook():
            QMessageBox.warning(
                self, "Claude Code",
                _t("frozen_hook_install_failed"),
            )

    # --- Rendering ---

    def _sync_claude_md(self) -> None:
        if not self._project_dir:
            return
        frozen = self._get_db().get_frozen_files(self._project_dir)
        fm.sync_claude_md(self._project_dir, [f["path"] for f in frozen])

    def _refresh(self) -> None:
        self._render_list()

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
        """Render one frozen file row.

        Lock icon is fixed-width, baseline-aligned; path + note sit in a
        stacked layout that's top-aligned so the icon lines up with the
        path, not the middle of the row.
        """
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { border-bottom: 1px solid #e0e0e0; padding: 6px; }"
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(6, 4, 6, 4)
        row.setAlignment(Qt.AlignTop)

        lock_icon = QLabel("\U0001F512")  # 🔒
        lock_icon.setFixedWidth(22)
        lock_icon.setStyleSheet("font-size: 14px; padding-top: 1px;")
        lock_icon.setAlignment(Qt.AlignTop)
        row.addWidget(lock_icon)

        info_widget = QWidget()
        info = QVBoxLayout(info_widget)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)
        info.setAlignment(Qt.AlignTop)

        path_lbl = QLabel(f["path"])
        path_lbl.setStyleSheet(
            f"font-family: {FONT_MONO}; font-weight: bold; color: {TITLE_DARK};"
        )
        path_lbl.setWordWrap(True)
        info.addWidget(path_lbl)

        if f.get("note"):
            note_lbl = QLabel(f["note"])
            note_lbl.setStyleSheet("color: #555; font-size: 11px;")
            note_lbl.setWordWrap(True)
            info.addWidget(note_lbl)

        row.addWidget(info_widget, 1)

        btn_unlock = QPushButton(_t("frozen_unlock"))
        btn_unlock.setStyleSheet(BUTTON_STYLE)
        btn_unlock.clicked.connect(lambda _, p=f["path"]: self._on_unlock(p))
        row.addWidget(btn_unlock, 0, Qt.AlignTop)

        return frame
