"""Overview page — budget, tokens, nag messages, hasselhoff."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QGroupBox, QFormLayout,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from i18n import get_string as _t


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class OverviewPage(QWidget):
    nag_requested = pyqtSignal()
    hoff_requested = pyqtSignal()
    refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._subscription = None
        layout = QVBoxLayout(self)

        self.budget_label = QLabel(_t("session_usage"))
        self.budget_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.budget_label)

        self.budget_bar = QProgressBar()
        self.budget_bar.setMaximum(100)
        layout.addWidget(self.budget_bar)

        self.cost_label = QLabel("--")
        self.cost_label.setStyleSheet(
            "font-size: 28px; font-weight: bold; color: #000080; "
            "border: 2px inset #808080; background: white; padding: 8px;"
        )
        self.cost_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.cost_label)

        self.stats_group = QGroupBox(_t("tokens"))
        sl = QFormLayout()
        self.lbl_sessions = QLabel("0")
        self.lbl_input = QLabel("0")
        self.lbl_output = QLabel("0")
        self.lbl_cache_read = QLabel("0")
        self.lbl_cache_write = QLabel("0")
        self.lbl_billable = QLabel("0")
        self.lbl_cache_eff = QLabel("0%")
        self.lbl_cache_saved = QLabel("$0.00")
        for label_text, widget in [
            (_t("lbl_sessions"), self.lbl_sessions),
            (_t("lbl_input_tokens"), self.lbl_input),
            (_t("lbl_output_tokens"), self.lbl_output),
            (_t("lbl_cache_read"), self.lbl_cache_read),
            (_t("lbl_cache_write"), self.lbl_cache_write),
            (_t("lbl_billable"), self.lbl_billable),
            (_t("lbl_cache_eff"), self.lbl_cache_eff),
            (_t("lbl_cache_saved"), self.lbl_cache_saved),
        ]:
            sl.addRow(QLabel(label_text), widget)
        self.stats_group.setLayout(sl)
        layout.addWidget(self.stats_group)

        self.nag_label = QLabel("")
        self.nag_label.setWordWrap(True)
        self.nag_label.setStyleSheet(
            "font-style: italic; padding: 8px; background: #ffffcc; "
            "color: #000; border: 2px inset #808080;"
        )
        layout.addWidget(self.nag_label)

        self.hoff_label = QLabel()
        self.hoff_label.setAlignment(Qt.AlignCenter)
        self.hoff_label.setFixedHeight(120)
        layout.addWidget(self.hoff_label)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton(_t("refresh"))
        self.btn_nag = QPushButton(_t("nag_me"))
        self.btn_hoff = QPushButton(_t("btn_hasselhoff"))
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        self.btn_nag.clicked.connect(self.nag_requested.emit)
        self.btn_hoff.clicked.connect(self.hoff_requested.emit)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_nag)
        btn_layout.addWidget(self.btn_hoff)
        layout.addLayout(btn_layout)
        layout.addStretch()

    def set_subscription(self, sub: dict) -> None:
        self._subscription = sub

    def update_data(self, stats, cost, cache_eff: float, savings: float,
                    nag_msg: str) -> None:
        is_api = self._subscription and self._subscription.get("is_paid_tokens")
        sub_type = (self._subscription or {}).get("type", "unknown")

        if is_api:
            # API key — show cost
            self.budget_label.setText(_t("api_cost_today").format(f"{cost.total_cost:.2f}"))
            self.cost_label.setText(f"${cost.total_cost:.2f}")
            pct = min(cost.total_cost / 10.0 * 100, 100)  # $10 soft cap for bar
        else:
            # Pro/Max/Team — show session usage, no dollar budget
            plan_name = sub_type.capitalize() if sub_type != "unknown" else "Plan"
            self.budget_label.setText(
                _t("session_info").format(plan_name, len(stats.sessions), _fmt(stats.total_billable))
            )
            self.cost_label.setText(f"{_fmt(stats.total_billable)} tok")
            # Progress bar: rough usage level (1M tokens = moderate day)
            pct = min(stats.total_billable / 1_000_000 * 100, 100)

        self.budget_bar.setValue(int(pct))
        cc = "#00cc00" if pct < 33 else ("#ffcc00" if pct < 66 else "#ff3333")
        self.budget_bar.setStyleSheet(f"QProgressBar::chunk {{ background: {cc}; }}")
        self.cost_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {cc}; "
            "border: 2px inset #808080; background: white; padding: 8px;"
        )
        self.lbl_sessions.setText(str(len(stats.sessions)))
        self.lbl_input.setText(_fmt(stats.total_input))
        self.lbl_output.setText(_fmt(stats.total_output))
        self.lbl_cache_read.setText(_fmt(stats.total_cache_read))
        self.lbl_cache_write.setText(_fmt(stats.total_cache_write))
        self.lbl_billable.setText(_fmt(stats.total_billable))
        self.lbl_cache_eff.setText(f"{cache_eff:.1f}%")
        self.lbl_cache_saved.setText(f"~${savings:.2f}")
        self.nag_label.setText(f'"{nag_msg}"')

    def set_hoff_image(self, path: str) -> None:
        pixmap = QPixmap(path).scaledToHeight(100, Qt.SmoothTransformation)
        self.hoff_label.setPixmap(pixmap)

    def set_no_claude(self) -> None:
        self.budget_label.setText(_t("claude_not_found"))
        self.cost_label.setText("--")
        self.nag_label.setText(_t("set_claude_path"))
