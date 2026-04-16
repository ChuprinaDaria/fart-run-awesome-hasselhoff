"""Save Points — unified page for code + environment save/restore.

Wraps existing SafetyNetPage (code via git) and SnapshotsPage (environment
state) under one sidebar item with a single "Save before feature" button on
top. Both existing widgets keep their full functionality (rollback, pick,
compare, delete) — just with hidden internal save UI so we have one obvious
action at the top.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTabWidget,
)
from PyQt5.QtGui import QFont

from i18n import get_string as _t
from gui.pages.safety_net_page import SafetyNetPage
from gui.pages.snapshots import SnapshotsPage
from gui.pages.frozen_tab import FrozenTab


class SavePointsPage(QWidget):
    """Combined Save Points page: one save button, two tabs with full features."""

    def __init__(self):
        super().__init__()
        self._safety = SafetyNetPage()
        self._snaps = SnapshotsPage()
        self._frozen = FrozenTab()

        # Hide each embedded page's own save buttons — we replace with unified one
        self._safety.hide_save_section()
        self._snaps.hide_save_section()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header
        title = QLabel(_t("sp_header"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        layout.addWidget(title)

        # Human-language hint
        hint = QLabel(_t("sp_hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color: #333; font-size: 12px; "
            "padding: 10px 12px; background: #fffff0; "
            "border: 2px solid #cccc00; border-radius: 4px;"
        )
        layout.addWidget(hint)

        # Unified save row
        save_row = QHBoxLayout()
        self._label_input = QLineEdit()
        self._label_input.setPlaceholderText(_t("sp_placeholder"))
        self._label_input.setStyleSheet(
            "QLineEdit { border: 2px inset #808080; padding: 4px; background: white; }"
        )
        save_row.addWidget(self._label_input)

        self._btn_save = QPushButton(_t("sp_save_btn"))
        self._btn_save.setStyleSheet(
            "QPushButton { background: #000080; color: white; padding: 8px 20px; "
            "border: 2px outset #4040c0; font-weight: bold; font-size: 13px; }"
            "QPushButton:pressed { border: 2px inset #000080; }"
            "QPushButton:disabled { background: #c0c0c0; color: #808080; }"
        )
        self._btn_save.clicked.connect(self._on_save)
        save_row.addWidget(self._btn_save)
        layout.addLayout(save_row)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._safety, _t("sp_tab_code"))
        tabs.addTab(self._snaps, _t("sp_tab_env"))
        tabs.addTab(self._frozen, _t("frozen_title"))
        layout.addWidget(tabs, 1)

    # --- Delegated setters ---

    def set_project_dir(self, path: str) -> None:
        self._safety.set_project_dir(path)
        self._snaps.set_project_dir(path)
        self._frozen.set_project_dir(path)

    def set_config(self, config: dict) -> None:
        self._safety.set_config(config)
        self._snaps.set_config(config)

    def set_haiku_error_callback(self, callback) -> None:
        if hasattr(self._safety, 'set_haiku_error_callback'):
            self._safety.set_haiku_error_callback(callback)
        if hasattr(self._snaps, 'set_haiku_error_callback'):
            self._snaps.set_haiku_error_callback(callback)

    def hide_dir_picker(self) -> None:
        self._safety.hide_dir_picker()
        self._snaps.hide_dir_picker()

    # --- Unified save ---

    def create_save_point_quick(self, label: str = "") -> None:
        """Called by other pages (Activity) to save both code + env."""
        final_label = label or _t("snap_btn_take")
        self._safety.create_save_point_quick(final_label)
        self._snaps.take_auto_snapshot(final_label)

    def _on_save(self) -> None:
        label = self._label_input.text().strip() or _t("snap_btn_take")
        # Code save first (may show git dialogs)
        self._safety.create_save_point_quick(label)
        # Environment snapshot — always tries, never blocks
        self._snaps.take_auto_snapshot(label)
        self._label_input.clear()

    # --- Back-compat with auto-snapshot timer in app.py ---

    def take_auto_snapshot(self, label: str,
                           docker_data=None, port_data=None) -> None:
        """Called by app's snapshot_timer — delegate to snapshot widget only."""
        self._snaps.take_auto_snapshot(label, docker_data, port_data)
