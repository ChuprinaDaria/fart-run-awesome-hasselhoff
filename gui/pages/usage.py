"""Usage page — delegates to UsageTab."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt


class UsagePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self._inner = None
        try:
            from gui.pages.usage_tab import UsageTab
            self._inner = UsageTab()
            layout.addWidget(self._inner)
        except ImportError:
            from i18n import get_string as _t
            label = QLabel(_t("usage_require"))
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #808080; font-style: italic;")
            layout.addWidget(label)

    def update_data(self, stats, cost, sub=None) -> None:
        if self._inner:
            self._inner.update_data(stats, cost, sub)
