"""Port/Service Map tab — Win95 style PyQt5 widget."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


class PortsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Port table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["PORT", "PROTO", "PROCESS", "CONTAINER", "PROJECT", "STATUS"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableWidget { alternate-background-color: #e8e8e8; }")
        layout.addWidget(self.table)

        # Summary
        self.summary_label = QLabel("0 ports listening")
        self.summary_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; padding: 6px; "
            "background: #ffffcc; border: 2px inset #808080;"
        )
        layout.addWidget(self.summary_label)

    def update_data(self, ports: list[dict], docker_ports: dict[int, str] | None = None) -> None:
        docker_ports = docker_ports or {}
        self.table.setRowCount(len(ports))

        for i, p in enumerate(ports):
            port_str = str(p["port"])
            is_conflict = p.get("conflict", False)
            is_exposed = p.get("exposed", False)

            if is_conflict:
                row_color = QColor(255, 50, 50)
                port_str = f"⚠ {port_str}"
                status = "CONFLICT"
            else:
                row_color = QColor(0, 128, 0)
                status = "● UP"

            port_item = QTableWidgetItem(port_str)
            port_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, port_item)

            self.table.setItem(i, 1, QTableWidgetItem(p.get("protocol", "TCP")))
            self.table.setItem(i, 2, QTableWidgetItem(p.get("process", "")))

            container = docker_ports.get(p["port"], "—")
            self.table.setItem(i, 3, QTableWidgetItem(container))

            self.table.setItem(i, 4, QTableWidgetItem(p.get("project", "")))

            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 5, status_item)

            # Color row
            for col in range(6):
                item = self.table.item(i, col)
                if item:
                    if is_conflict:
                        item.setForeground(QColor(255, 50, 50))
                        item.setBackground(QColor(255, 230, 230))
                    elif is_exposed:
                        item.setForeground(QColor(180, 130, 0))

        # Update summary
        total = len(ports)
        conflicts = sum(1 for pp in ports if pp.get("conflict"))
        exposed = sum(1 for pp in ports if pp.get("exposed"))
        self.summary_label.setText(f"{total} ports listening  |  {conflicts} conflicts  |  {exposed} exposed (0.0.0.0)")
