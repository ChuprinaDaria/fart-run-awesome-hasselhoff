"""Analytics page — model comparison and project breakdown."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar,
    QTableWidgetItem, QHeaderView,
)
from gui.copyable_table import CopyableTableWidget
from PyQt5.QtCore import Qt
from i18n import get_string as _t
from gui.fmt_utils import fmt_tokens as _fmt


class AnalyticsPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.cache_label = QLabel(_t("cache_eff_pct").format("0"))
        self.cache_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.cache_label)

        self.cache_bar = QProgressBar()
        self.cache_bar.setMaximum(100)
        layout.addWidget(self.cache_bar)

        self.savings_label = QLabel(_t("cache_saved_usd").format("0.00"))
        layout.addWidget(self.savings_label)

        self.model_table = CopyableTableWidget()
        self.model_table.setColumnCount(3)
        self.model_table.setHorizontalHeaderLabels([_t("model"), _t("tokens"), _t("cost")])
        self.model_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.model_table.setEditTriggers(CopyableTableWidget.NoEditTriggers)
        layout.addWidget(self.model_table)

        self.project_table = CopyableTableWidget()
        self.project_table.setColumnCount(3)
        self.project_table.setHorizontalHeaderLabels([_t("project"), _t("billable"), _t("sessions")])
        self.project_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.project_table.setEditTriggers(CopyableTableWidget.NoEditTriggers)
        layout.addWidget(self.project_table)

        # --- Weekly Trends ---
        from PyQt5.QtWidgets import QGroupBox
        self.trends_group = QGroupBox("Weekly Trends")
        tl = QVBoxLayout()
        self.trend_labels: list[QLabel] = []
        for _ in range(7):
            lbl = QLabel("")
            lbl.setStyleSheet("padding: 2px 4px; font-size: 11px; font-family: monospace;")
            tl.addWidget(lbl)
            self.trend_labels.append(lbl)
        self.trend_summary = QLabel("")
        self.trend_summary.setStyleSheet("padding: 4px; font-weight: bold;")
        tl.addWidget(self.trend_summary)
        self.trends_group.setLayout(tl)
        layout.addWidget(self.trends_group)

        layout.addStretch()

    def update_data(self, stats, cache_eff: float, savings: float,
                    comparison: dict, projects: list) -> None:
        self.cache_label.setText(_t("cache_eff_pct").format(f"{cache_eff:.1f}"))
        self.cache_bar.setValue(int(cache_eff))
        self.savings_label.setText(_t("cache_saved_usd").format(f"{savings:.2f}"))

        # Filter out synthetic/unknown models
        real_models = {m: mu for m, mu in stats.model_totals.items()
                       if "claude" in m.lower() or "gpt" in m.lower()}
        if not real_models:
            real_models = stats.model_totals

        self.model_table.setRowCount(len(real_models))
        for i, (model, mu) in enumerate(real_models.items()):
            name = model.replace("claude-", "").replace("-", " ").upper()
            self.model_table.setItem(i, 0, QTableWidgetItem(name))
            self.model_table.setItem(i, 1, QTableWidgetItem(_fmt(mu.billable_tokens)))
            self.model_table.setItem(i, 2, QTableWidgetItem(f"${comparison.get('actual', 0):.2f}"))

        self.project_table.setRowCount(min(len(projects), 10))
        for i, p in enumerate(projects[:10]):
            self.project_table.setItem(i, 0, QTableWidgetItem(p.project))
            self.project_table.setItem(i, 1, QTableWidgetItem(_fmt(p.total_billable)))
            self.project_table.setItem(i, 2, QTableWidgetItem(str(p.sessions)))

    def update_trends(self, history: list[dict]) -> None:
        """Show last 7 days as text-based bar chart."""
        if not history:
            return

        max_tokens = max((h["tokens"] for h in history), default=1) or 1
        for i, h in enumerate(history[:7]):
            if i >= len(self.trend_labels):
                break
            bar_len = int(h["tokens"] / max_tokens * 20)
            bar = "\u2588" * bar_len + "\u2591" * (20 - bar_len)
            self.trend_labels[i].setText(
                f"{h['date'][-5:]}  {bar}  {h['tokens']/1000:.0f}K  ${h['cost']:.2f}"
            )

        if len(history) >= 2:
            today = history[0]["tokens"]
            yesterday = history[1]["tokens"]
            if yesterday > 0:
                change = (today - yesterday) / yesterday * 100
                arrow = "\u2191" if change > 0 else "\u2193"
                avg_cache = sum(h["cache_efficiency"] for h in history) / len(history)
                self.trend_summary.setText(
                    f"{arrow} {abs(change):.0f}% vs yesterday | Avg cache: {avg_cache:.0f}%"
                )

    def set_no_claude(self) -> None:
        self.cache_label.setText(_t("no_analytics"))
