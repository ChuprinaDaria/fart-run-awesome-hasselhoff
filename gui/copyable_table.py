"""QTableWidget with Ctrl+C support for copying selected rows."""

from PyQt5.QtWidgets import QTableWidget, QApplication
from PyQt5.QtCore import Qt


class CopyableTableWidget(QTableWidget):
    """QTableWidget that copies selected cells to clipboard on Ctrl+C."""

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
            self._copy_selection()
        else:
            super().keyPressEvent(event)

    def _copy_selection(self):
        selection = self.selectedIndexes()
        if not selection:
            return

        rows = sorted(set(idx.row() for idx in selection))
        cols = sorted(set(idx.column() for idx in selection))

        lines = []
        for row in rows:
            cells = []
            for col in cols:
                item = self.item(row, col)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))

        text = "\n".join(lines)
        QApplication.clipboard().setText(text)
