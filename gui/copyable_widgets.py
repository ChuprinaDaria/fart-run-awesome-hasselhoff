"""Copy-to-clipboard widgets for all pages."""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QGroupBox, QVBoxLayout, QPushButton, QApplication, QLabel, QWidget,
)
from PyQt5.QtCore import Qt
from i18n import get_string as _t


def extract_text_from_labels(texts: list[str]) -> str:
    """Join text lines for clipboard."""
    return "\n".join(texts)


def _collect_label_texts(widget: QWidget) -> list[str]:
    """Recursively collect text from all QLabels inside a widget."""
    texts = []
    for child in widget.findChildren(QLabel):
        text = child.text().strip()
        if text:
            texts.append(text)
    return texts


class CopyableSection(QGroupBox):
    """QGroupBox with built-in copy support (Ctrl+C)."""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self.setStyleSheet(
            "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
            "padding-top: 16px; font-weight: bold; background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        self._inner_layout = QVBoxLayout(self)
        self._inner_layout.setSpacing(2)

    def layout(self):
        return self._inner_layout

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self.copy_to_clipboard()
        else:
            super().keyPressEvent(event)

    def copy_to_clipboard(self) -> None:
        texts = _collect_label_texts(self)
        if texts:
            QApplication.clipboard().setText("\n".join(texts))


def make_copy_all_button(get_text_fn) -> QPushButton:
    """Create a 'Copy all' button that calls get_text_fn() on click."""
    btn = QPushButton(_t("copy_all"))
    btn.setStyleSheet(
        "QPushButton { padding: 3px 12px; border: 2px outset #dfdfdf; font-size: 11px; }"
        "QPushButton:pressed { border: 2px inset #808080; }"
    )
    btn.setFixedHeight(24)

    def _on_click():
        text = get_text_fn()
        if text:
            QApplication.clipboard().setText(text)

    btn.clicked.connect(_on_click)
    return btn
