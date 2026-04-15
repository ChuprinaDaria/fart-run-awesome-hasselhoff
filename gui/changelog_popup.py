"""Changelog popup — shown when Claude Code version changes."""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from i18n import get_string as _t


class ChangelogPopup(QDialog):
    """Win95-style popup for Claude Code updates."""

    def __init__(
        self,
        old_version: str,
        new_version: str,
        changelog_url: str,
        parent=None,
    ):
        super().__init__(parent)
        self._changelog_url = changelog_url
        self._dismissed = False

        self.setWindowTitle(_t("changelog_title"))
        self.setFixedSize(420, 220)
        self.setStyleSheet(
            "QDialog { background: #c0c0c0; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel(_t("changelog_title"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(8)

        # Version change
        version_lbl = QLabel(f"{old_version}  \u2192  {new_version}")
        version_lbl.setFont(QFont("MS Sans Serif", 16, QFont.Bold))
        version_lbl.setAlignment(Qt.AlignCenter)
        version_lbl.setStyleSheet("color: #000000;")
        layout.addWidget(version_lbl)

        layout.addSpacing(8)

        # Message
        msg = QLabel(_t("changelog_message"))
        msg.setWordWrap(True)
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("color: #333; font-size: 12px;")
        layout.addWidget(msg)

        layout.addSpacing(12)

        # Buttons
        buttons = QHBoxLayout()

        btn_got_it = QPushButton(_t("changelog_got_it"))
        btn_got_it.setStyleSheet(
            "QPushButton { background: #000080; color: white; padding: 6px 20px; "
            "border: 2px outset #4040c0; font-weight: bold; }"
            "QPushButton:pressed { border: 2px inset #000080; }"
        )
        btn_got_it.clicked.connect(self._on_got_it)
        buttons.addWidget(btn_got_it)

        btn_changelog = QPushButton(_t("changelog_show_full"))
        btn_changelog.setStyleSheet(
            "QPushButton { padding: 6px 20px; border: 2px outset #dfdfdf; }"
            "QPushButton:pressed { border: 2px inset #808080; }"
        )
        btn_changelog.clicked.connect(self._on_show_changelog)
        buttons.addWidget(btn_changelog)

        layout.addLayout(buttons)

    def _on_got_it(self) -> None:
        self._dismissed = True
        self.accept()

    def _on_show_changelog(self) -> None:
        from core.platform import get_platform
        get_platform().open_url(self._changelog_url)

    @property
    def was_dismissed(self) -> bool:
        return self._dismissed
