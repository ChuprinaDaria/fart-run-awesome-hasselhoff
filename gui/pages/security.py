"""Security page — findings table with detail panel and human explanations."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidgetItem,
    QHeaderView, QLabel, QPushButton, QGroupBox, QTextEdit, QSplitter,
    QDialog,
)
from gui.copyable_table import CopyableTableWidget
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QColor

from gui.security_explanations import get_explanation, get_human_description, get_course_link
from i18n import get_string as _t


SEVERITY_COLORS = {
    "critical": ("#ffffff", "#cc0000"),
    "high": ("#000000", "#ff8c00"),
    "medium": ("#000000", "#ffcc00"),
    "low": ("#000000", "#c0c0c0"),
}


class CriticalAlertDialog(QDialog):
    _shown_findings: set[str] = set()

    def __init__(self, finding: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("hasselhoff_angry"))
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(
            "background: #1a0000; color: #ffffff; border: 2px solid #cc0000;"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QLabel(f'🚨 {_t("hasselhoff_angry")} 🚨')
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #ff4444; "
            "background: #1a0000; padding: 8px;"
        )
        layout.addWidget(header)

        # Finding description
        desc_text = finding.get("description", "")
        desc_label = QLabel(desc_text)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            "font-size: 13px; color: #ffff00; background: #1a0000; padding: 4px;"
        )
        layout.addWidget(desc_label)

        # Fart emoji
        fart = QLabel("💨 *ПРРРРТ* 💨")
        fart.setAlignment(Qt.AlignCenter)
        fart.setStyleSheet("font-size: 22px; padding: 4px;")
        layout.addWidget(fart)

        explanation = get_explanation(finding.get("type", ""), desc_text)

        # What is this
        what_title = QLabel(_t("what_is_this"))
        what_title.setStyleSheet("font-weight: bold; color: #ffffff; background: #1a0000;")
        layout.addWidget(what_title)
        what_label = QLabel(explanation.get("what", ""))
        what_label.setWordWrap(True)
        what_label.setStyleSheet("color: #dddddd; background: #1a0000; padding: 2px 8px;")
        layout.addWidget(what_label)

        # Risk
        risk_title = QLabel(_t("risk"))
        risk_title.setStyleSheet("font-weight: bold; color: #ff4444; background: #1a0000;")
        layout.addWidget(risk_title)
        risk_label = QLabel(explanation.get("risk", ""))
        risk_label.setWordWrap(True)
        risk_label.setStyleSheet("color: #ff8888; background: #1a0000; padding: 2px 8px;")
        layout.addWidget(risk_label)

        # How to fix
        fix_title = QLabel(_t("how_to_fix"))
        fix_title.setStyleSheet("font-weight: bold; color: #00ff00; background: #1a0000;")
        layout.addWidget(fix_title)
        fix_edit = QTextEdit()
        fix_edit.setReadOnly(True)
        fix_edit.setPlainText(explanation.get("fix", ""))
        fix_edit.setMaximumHeight(110)
        fix_edit.setFontFamily("Courier New")
        fix_edit.setFontPointSize(10)
        fix_edit.setStyleSheet(
            "background: #0a1a0a; color: #00ff00; border: 2px inset #808080;"
        )
        layout.addWidget(fix_edit)

        # Coursera link
        course = get_course_link(finding.get("type", ""), desc_text)
        if course:
            course_label = QLabel(
                f'📚 <a href="{course["url"]}" style="color:#5599ff;">'
                f'{_t("learn_more")}: {course["title"]}</a>'
            )
            course_label.setOpenExternalLinks(True)
            course_label.setStyleSheet("background: #1a0000; padding: 4px;")
            layout.addWidget(course_label)

        # Close button
        btn = QPushButton(_t("understood"))
        btn.setStyleSheet(
            "font-size: 13px; font-weight: bold; padding: 8px 20px; "
            "background: #cc0000; color: #ffffff; border: 2px outset #ff4444;"
        )
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignCenter)

    @classmethod
    def show_if_new(cls, finding: dict, parent=None) -> None:
        desc = finding.get("description", "")
        if desc in cls._shown_findings:
            return
        cls._shown_findings.add(desc)
        dlg = cls(finding, parent)
        dlg.exec_()


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

        self.table = CopyableTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([_t("sev"), _t("type"), _t("description"), _t("source")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(CopyableTableWidget.SelectRows)
        self.table.setEditTriggers(CopyableTableWidget.NoEditTriggers)
        self.table.currentCellChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        self.detail_panel = QGroupBox(_t("details"))
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

        self.detail_course = QLabel("")
        self.detail_course.setOpenExternalLinks(True)
        self.detail_course.setStyleSheet("padding: 4px; color: #5599ff;")
        self.detail_course.hide()

        detail_layout.addWidget(QLabel(_t("what_is_this")))
        detail_layout.addWidget(self.detail_what)
        detail_layout.addWidget(QLabel(_t("risk")))
        detail_layout.addWidget(self.detail_risk)
        detail_layout.addWidget(QLabel(_t("how_to_fix")))
        detail_layout.addWidget(self.detail_fix)
        detail_layout.addWidget(QLabel("📚"))
        detail_layout.addWidget(self.detail_course)
        self.detail_panel.setLayout(detail_layout)
        self.detail_panel.hide()
        splitter.addWidget(self.detail_panel)

        layout.addWidget(splitter)

        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton(_t("scan_now"))
        self.btn_scan.setStyleSheet("font-size: 13px; padding: 6px 16px;")
        self.btn_scan.clicked.connect(self.scan_requested.emit)
        btn_layout.addWidget(self.btn_scan)
        self.last_scan_label = QLabel(_t("last_scan_never"))
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
        self.last_scan_label.setText(_t("last_scan").format(datetime.now().strftime("%H:%M:%S")))

        for f in findings:
            if f.get("severity") == "critical":
                CriticalAlertDialog.show_if_new(f, self)

    def _on_row_selected(self, row, _col, _prev_row, _prev_col):
        if row < 0 or row >= len(self._findings):
            self.detail_panel.hide()
            return
        finding = self._findings[row]
        finding_type = finding.get("type", "")
        description = finding.get("description", "")
        explanation = get_explanation(finding_type, description)
        self.detail_what.setText(explanation["what"])
        self.detail_risk.setText(explanation["risk"])
        self.detail_fix.setPlainText(explanation["fix"])

        course = get_course_link(finding_type, description)
        if course:
            self.detail_course.setText(
                f'<a href="{course["url"]}" style="color:#5599ff;">'
                f'{_t("learn_more")}: {course["title"]}</a>'
            )
            self.detail_course.show()
        else:
            self.detail_course.hide()

        self.detail_panel.show()

    def set_scanning(self, scanning: bool) -> None:
        self.btn_scan.setEnabled(not scanning)
        self.btn_scan.setText(_t("scanning") if scanning else "Scan Now")

    def critical_count(self) -> int:
        return sum(1 for f in self._findings if f.get("severity") in ("critical", "high"))
