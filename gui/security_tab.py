"""Security Scan tab — Win95 style PyQt5 widget."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor


SEVERITY_COLORS = {
    "critical": ("#ffffff", "#cc0000"),  # white on red
    "high": ("#000000", "#ff8c00"),      # black on orange
    "medium": ("#000000", "#ffcc00"),    # black on yellow
    "low": ("#000000", "#c0c0c0"),       # black on grey
}


class SecurityTab(QWidget):
    scan_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Severity counters
        counter_layout = QHBoxLayout()
        self.counters = {}
        for sev in ["critical", "high", "medium", "low"]:
            fg, bg = SEVERITY_COLORS[sev]
            label = QLabel(f" {sev.upper()}: 0 ")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(
                f"font-size: 14px; font-weight: bold; color: {fg}; "
                f"background: {bg}; border: 2px outset #dfdfdf; padding: 4px 12px;"
            )
            self.counters[sev] = label
            counter_layout.addWidget(label)
        layout.addLayout(counter_layout)

        # Findings table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["SEV", "TYPE", "DESCRIPTION", "SOURCE"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        # Scan button + last scan label
        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton("🔍 Scan Now")
        self.btn_scan.setStyleSheet("font-size: 13px; padding: 6px 16px;")
        self.btn_scan.clicked.connect(self.scan_requested.emit)
        btn_layout.addWidget(self.btn_scan)
        self.last_scan_label = QLabel("Last scan: never")
        self.last_scan_label.setStyleSheet("font-style: italic; color: #666;")
        btn_layout.addWidget(self.last_scan_label)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def update_data(self, findings: list[dict]) -> None:
        # Sort: critical first
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings.sort(key=lambda f: order.get(f.get("severity", "low"), 4))

        # Update counters
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            sev = f.get("severity", "low")
            counts[sev] = counts.get(sev, 0) + 1
        for sev, label in self.counters.items():
            label.setText(f" {sev.upper()}: {counts[sev]} ")

        # Update table
        self.table.setRowCount(len(findings))
        for i, f in enumerate(findings):
            sev = f.get("severity", "low")
            fg_hex, bg_hex = SEVERITY_COLORS.get(sev, ("#000", "#ccc"))

            sev_item = QTableWidgetItem(sev.upper())
            sev_item.setTextAlignment(Qt.AlignCenter)
            sev_item.setForeground(QColor(fg_hex))
            sev_item.setBackground(QColor(bg_hex))
            self.table.setItem(i, 0, sev_item)

            self.table.setItem(i, 1, QTableWidgetItem(f.get("type", "")))

            desc = f.get("description", "")[:80]
            self.table.setItem(i, 2, QTableWidgetItem(desc))

            source = f.get("source", "")[:30]
            self.table.setItem(i, 3, QTableWidgetItem(source))

        # Update last scan time
        from datetime import datetime
        self.last_scan_label.setText(f"Last scan: {datetime.now().strftime('%H:%M:%S')}")

    def set_scanning(self, scanning: bool) -> None:
        self.btn_scan.setEnabled(not scanning)
        self.btn_scan.setText("⏳ Scanning..." if scanning else "🔍 Scan Now")
