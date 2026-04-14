"""Security page — findings table with detail panel and human explanations."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QGroupBox, QTextEdit, QSplitter,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QColor

from gui.security_explanations import get_explanation, get_human_description


SEVERITY_COLORS = {
    "critical": ("#ffffff", "#cc0000"),
    "high": ("#000000", "#ff8c00"),
    "medium": ("#000000", "#ffcc00"),
    "low": ("#000000", "#c0c0c0"),
}


class SecurityScanThread(QThread):
    scan_done = pyqtSignal(list)

    def __init__(self, scanner_fn):
        super().__init__()
        self._scanner_fn = scanner_fn

    def run(self):
        try:
            findings = self._scanner_fn()
            self.scan_done.emit(findings)
        except Exception:
            self.scan_done.emit([])


class SecurityPage(QWidget):
    scan_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

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

        splitter = QSplitter(Qt.Vertical)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["SEV", "TYPE", "DESCRIPTION", "SOURCE"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.currentCellChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        self.detail_panel = QGroupBox("Details")
        detail_layout = QVBoxLayout()

        self.detail_what = QLabel("")
        self.detail_what.setWordWrap(True)
        self.detail_what.setStyleSheet("padding: 4px;")

        self.detail_risk = QLabel("")
        self.detail_risk.setWordWrap(True)
        self.detail_risk.setStyleSheet("padding: 4px; color: #cc0000;")

        self.detail_fix = QTextEdit("")
        self.detail_fix.setReadOnly(True)
        self.detail_fix.setMaximumHeight(100)
        self.detail_fix.setFontFamily("Courier New")
        self.detail_fix.setFontPointSize(10)
        self.detail_fix.setStyleSheet("background: #1a1a2e; color: #00ff00; border: 2px inset #808080;")

        detail_layout.addWidget(QLabel("What is this:"))
        detail_layout.addWidget(self.detail_what)
        detail_layout.addWidget(QLabel("Risk:"))
        detail_layout.addWidget(self.detail_risk)
        detail_layout.addWidget(QLabel("How to fix:"))
        detail_layout.addWidget(self.detail_fix)
        self.detail_panel.setLayout(detail_layout)
        self.detail_panel.hide()
        splitter.addWidget(self.detail_panel)

        layout.addWidget(splitter)

        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton("Scan Now")
        self.btn_scan.setStyleSheet("font-size: 13px; padding: 6px 16px;")
        self.btn_scan.clicked.connect(self.scan_requested.emit)
        btn_layout.addWidget(self.btn_scan)
        self.last_scan_label = QLabel("Last scan: never")
        self.last_scan_label.setStyleSheet("font-style: italic; color: #666;")
        btn_layout.addWidget(self.last_scan_label)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._findings: list[dict] = []

    def update_data(self, findings: list[dict]) -> None:
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        findings.sort(key=lambda f: order.get(f.get("severity", "low"), 4))
        self._findings = findings

        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            counts[f.get("severity", "low")] = counts.get(f.get("severity", "low"), 0) + 1
        for sev, label in self.counters.items():
            label.setText(f" {sev.upper()}: {counts[sev]} ")

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

            desc = get_human_description(f.get("type", ""), f.get("description", ""))
            self.table.setItem(i, 2, QTableWidgetItem(desc[:100]))

            self.table.setItem(i, 3, QTableWidgetItem(f.get("source", "")[:30]))

        from datetime import datetime
        self.last_scan_label.setText(f"Last scan: {datetime.now().strftime('%H:%M:%S')}")

    def _on_row_selected(self, row, _col, _prev_row, _prev_col):
        if row < 0 or row >= len(self._findings):
            self.detail_panel.hide()
            return
        finding = self._findings[row]
        explanation = get_explanation(finding.get("type", ""), finding.get("description", ""))
        self.detail_what.setText(explanation["what"])
        self.detail_risk.setText(explanation["risk"])
        self.detail_fix.setPlainText(explanation["fix"])
        self.detail_panel.show()

    def set_scanning(self, scanning: bool) -> None:
        self.btn_scan.setEnabled(not scanning)
        self.btn_scan.setText("Scanning..." if scanning else "Scan Now")

    def critical_count(self) -> int:
        return sum(1 for f in self._findings if f.get("severity") in ("critical", "high"))
