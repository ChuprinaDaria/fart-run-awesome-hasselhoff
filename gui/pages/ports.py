"""Ports page — listening ports, conflicts, project mapping."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidgetItem,
    QHeaderView, QLabel,
)
from gui.copyable_table import CopyableTableWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from claude_nagger.i18n import get_string as _t


class PortsPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.warning_banner = QLabel("")
        self.warning_banner.setWordWrap(True)
        self.warning_banner.setStyleSheet(
            "background: #ffffcc; color: #000; padding: 8px; "
            "border: 2px inset #808080;"
        )
        self.warning_banner.hide()
        layout.addWidget(self.warning_banner)

        self.table = CopyableTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [_t("port"), _t("proto"), _t("process"), _t("project"), _t("ip"), _t("status")]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(CopyableTableWidget.SelectRows)
        self.table.setEditTriggers(CopyableTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableWidget { alternate-background-color: #e8e8e8; }")
        layout.addWidget(self.table)

        self.summary = QLabel("")
        self.summary.setStyleSheet("padding: 4px; font-style: italic;")
        layout.addWidget(self.summary)

    def set_psutil_warning(self, limited: bool) -> None:
        if limited:
            self.warning_banner.setText(
                _t("psutil_warning")  #
                
            )
            self.warning_banner.show()
        else:
            self.warning_banner.hide()

    def update_data(self, ports: list[dict]) -> None:
        self.table.setRowCount(len(ports))
        conflicts = 0
        exposed = 0

        for i, p in enumerate(ports):
            is_conflict = p.get("conflict", False)
            is_exposed = p.get("exposed", False)
            if is_conflict:
                conflicts += 1
            if is_exposed:
                exposed += 1

            if is_conflict:
                color = QColor(255, 50, 50)
            elif is_exposed:
                color = QColor(200, 140, 0)
            else:
                color = QColor(0, 120, 0)

            port_item = QTableWidgetItem(str(p.get("port", "")))
            port_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, port_item)
            self.table.setItem(i, 1, QTableWidgetItem(p.get("protocol", "")))

            process = p.get("process", "") or "<unknown process>"
            self.table.setItem(i, 2, QTableWidgetItem(process))
            self.table.setItem(i, 3, QTableWidgetItem(p.get("project", "")))
            self.table.setItem(i, 4, QTableWidgetItem(p.get("ip", "")))

            status = "CONFLICT" if is_conflict else ("EXPOSED" if is_exposed else "OK")
            self.table.setItem(i, 5, QTableWidgetItem(status))

            for col in range(6):
                item = self.table.item(i, col)
                if item:
                    item.setForeground(color)

        self.summary.setText(
            _t("ports_summary").format(len(ports), conflicts, exposed)
        )

    def port_count(self) -> int:
        return self.table.rowCount()
