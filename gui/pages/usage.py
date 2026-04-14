"""Usage page — delegates to claude_nagger UsageTab."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt


class UsagePage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self._inner = None
        try:
            from claude_nagger.gui.usage import UsageTab
            self._inner = UsageTab()
            layout.addWidget(self._inner)
        except ImportError:
            label = QLabel("Usage data requires claude_nagger module")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("color: #808080; font-style: italic;")
            layout.addWidget(label)

    def update_data(self, stats, cost, sub=None) -> None:
        if self._inner:
            self._inner.update_data(stats, cost, sub)
