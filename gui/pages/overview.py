"""Overview page — budget, tokens, nag messages, compact Docker/Ports."""

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


_COMPACT_STYLE = (
    "padding: 4px 8px; background: white; border: 2px inset #808080; font-size: 11px;"
)


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

        # Token stats
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

        # --- Compact Docker/Ports ---
        self.infra_group = QGroupBox("Infrastructure")
        il = QVBoxLayout()

        self.docker_status = QLabel("Docker: --")
        self.docker_status.setStyleSheet(_COMPACT_STYLE)
        il.addWidget(self.docker_status)

        self.ports_status = QLabel("Ports: --")
        self.ports_status.setStyleSheet(_COMPACT_STYLE)
        il.addWidget(self.ports_status)

        self.infra_group.setLayout(il)
        layout.addWidget(self.infra_group)

        # --- Security Score ---
        sec_layout = QHBoxLayout()
        self.security_score = QLabel("--")
        self.security_score.setStyleSheet(
            "font-size: 36px; font-weight: bold; color: #000080; "
            "border: 2px inset #808080; background: white; padding: 8px; min-width: 80px;"
        )
        self.security_score.setAlignment(Qt.AlignCenter)
        sec_layout.addWidget(self.security_score)

        self.security_breakdown = QLabel("Security Score")
        self.security_breakdown.setWordWrap(True)
        self.security_breakdown.setStyleSheet("padding: 4px; font-size: 11px;")
        sec_layout.addWidget(self.security_breakdown, stretch=1)
        layout.addLayout(sec_layout)

        # Nag message
        self.nag_label = QLabel("")
        self.nag_label.setWordWrap(True)
        self.nag_label.setStyleSheet(
            "font-style: italic; padding: 8px; background: #ffffcc; "
            "color: #000; border: 2px inset #808080;"
        )
        layout.addWidget(self.nag_label)

        # Hasselhoff image (shown on manual trigger only)
        self.hoff_label = QLabel()
        self.hoff_label.setAlignment(Qt.AlignCenter)
        self.hoff_label.setFixedHeight(120)
        layout.addWidget(self.hoff_label)

        # Buttons
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
            self.budget_label.setText(_t("api_cost_today").format(f"{cost.total_cost:.2f}"))
            self.cost_label.setText(f"${cost.total_cost:.2f}")
            pct = min(cost.total_cost / 10.0 * 100, 100)
        else:
            plan_name = sub_type.capitalize() if sub_type != "unknown" else "Plan"
            self.budget_label.setText(
                _t("session_info").format(plan_name, len(stats.sessions), _fmt(stats.total_billable))
            )
            self.cost_label.setText(f"{_fmt(stats.total_billable)} tok")
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

    def update_docker_compact(self, infos: list[dict]) -> None:
        """Compact Docker status line."""
        running = sum(1 for i in infos if i.get("status") == "running")
        stopped = len(infos) - running
        alerts = 0
        for i in infos:
            if i.get("status") == "exited" and i.get("exit_code", 0) != 0:
                alerts += 1
            if i.get("cpu_percent", 0) > 80:
                alerts += 1

        text = f"Docker: {running} running | {stopped} stopped"
        if alerts:
            text += f" | {alerts} alerts"

        color = "#006600" if alerts == 0 else "#cc0000"
        self.docker_status.setText(text)
        self.docker_status.setStyleSheet(f"{_COMPACT_STYLE} color: {color};")

    def update_ports_compact(self, ports: list[dict]) -> None:
        """Compact Ports status line."""
        total = len(ports)
        conflicts = sum(1 for p in ports if p.get("conflict"))
        text = f"Ports: {total} listening | {conflicts} conflicts"
        color = "#006600" if conflicts == 0 else "#cc8800"
        self.ports_status.setText(text)
        self.ports_status.setStyleSheet(f"{_COMPACT_STYLE} color: {color};")

    def update_security_score(self, findings: list[dict]) -> None:
        """Calculate and display security score 0-100."""
        if not findings:
            self.security_score.setText("100")
            self.security_score.setStyleSheet(
                "font-size: 36px; font-weight: bold; color: #006600; "
                "border: 2px inset #808080; background: white; padding: 8px; min-width: 80px;"
            )
            self.security_breakdown.setText("No issues found")
            return

        deductions = {"critical": 20, "high": 10, "medium": 3, "low": 1}
        total_deduction = 0
        counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            sev = f.get("severity", "low")
            counts[sev] = counts.get(sev, 0) + 1
            total_deduction += deductions.get(sev, 1)

        score = max(0, 100 - total_deduction)
        color = "#006600" if score >= 80 else ("#cc8800" if score >= 50 else "#cc0000")

        self.security_score.setText(str(score))
        self.security_score.setStyleSheet(
            f"font-size: 36px; font-weight: bold; color: {color}; "
            "border: 2px inset #808080; background: white; padding: 8px; min-width: 80px;"
        )

        parts = []
        for sev in ("critical", "high", "medium", "low"):
            if counts[sev] > 0:
                parts.append(f"{counts[sev]} {sev}")
        self.security_breakdown.setText(" | ".join(parts) if parts else "No issues")

    def set_docker_error(self, msg: str) -> None:
        self.docker_status.setText(f"Docker: {msg}")
        self.docker_status.setStyleSheet(f"{_COMPACT_STYLE} color: #999999;")

    def set_hoff_image(self, path: str) -> None:
        pixmap = QPixmap(path).scaledToHeight(100, Qt.SmoothTransformation)
        self.hoff_label.setPixmap(pixmap)

    def set_no_claude(self) -> None:
        self.budget_label.setText(_t("claude_not_found"))
        self.cost_label.setText("--")
        self.nag_label.setText(_t("set_claude_path"))
