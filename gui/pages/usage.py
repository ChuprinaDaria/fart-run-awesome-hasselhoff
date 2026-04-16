"""Usage page — everything about token spending: plan, today, week, models, projects, trends."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QGroupBox, QFormLayout,
    QTableWidgetItem, QHeaderView, QScrollArea,
)
from PyQt5.QtCore import Qt

from core.token_parser import TokenParser
from core.usage_analyzer import Analyzer
from gui.copyable_table import CopyableTableWidget
from gui.fmt_utils import fmt_tokens as _fmt
from i18n import get_string as _t


class UsagePage(QWidget):
    """Unified usage/analytics page."""

    def __init__(self):
        super().__init__()

        # Scroll wrapper — page is tall
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        container = QWidget()
        layout = QVBoxLayout(container)
        scroll.setWidget(container)

        # --- Plan info ---
        self.plan_label = QLabel("Plan: —")
        self.plan_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 8px; "
            "background: #000080; color: white; border: 2px outset #dfdfdf;"
        )
        layout.addWidget(self.plan_label)

        # --- Today ---
        self.today_group = QGroupBox(_t("today"))
        tg = QFormLayout()
        self.today_sessions = QLabel("0")
        self.today_tokens = QLabel("0")
        self.today_input = QLabel("0")
        self.today_output = QLabel("0")
        self.today_cache = QLabel("0%")
        self.today_saved = QLabel("—")
        tg.addRow(_t("sessions") + ":", self.today_sessions)
        tg.addRow("Total tokens:", self.today_tokens)
        tg.addRow("  Input:", self.today_input)
        tg.addRow("  Output:", self.today_output)
        tg.addRow("Cache efficiency:", self.today_cache)
        tg.addRow("Cache saved:", self.today_saved)
        self.today_group.setLayout(tg)
        layout.addWidget(self.today_group)

        # --- This week ---
        self.week_group = QGroupBox(_t("this_week"))
        wg = QFormLayout()
        self.week_sessions = QLabel("0")
        self.week_tokens = QLabel("0")
        wg.addRow(_t("sessions") + ":", self.week_sessions)
        wg.addRow("Total tokens:", self.week_tokens)
        self.week_group.setLayout(wg)
        layout.addWidget(self.week_group)

        # --- Cache efficiency bar ---
        self.cache_label = QLabel(_t("cache_eff_pct").format("0"))
        self.cache_label.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 8px;")
        layout.addWidget(self.cache_label)

        self.cache_bar = QProgressBar()
        self.cache_bar.setMaximum(100)
        layout.addWidget(self.cache_bar)

        self.savings_label = QLabel(_t("cache_saved_usd").format("0.00"))
        layout.addWidget(self.savings_label)

        # --- Model breakdown ---
        self.model_table = CopyableTableWidget()
        self.model_table.setColumnCount(3)
        self.model_table.setHorizontalHeaderLabels([_t("model"), _t("tokens"), _t("cost")])
        self.model_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.model_table.setEditTriggers(CopyableTableWidget.NoEditTriggers)
        layout.addWidget(self.model_table)

        # --- Project breakdown ---
        self.project_table = CopyableTableWidget()
        self.project_table.setColumnCount(3)
        self.project_table.setHorizontalHeaderLabels([_t("project"), _t("billable"), _t("sessions")])
        self.project_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.project_table.setEditTriggers(CopyableTableWidget.NoEditTriggers)
        layout.addWidget(self.project_table)

        # --- Weekly trends ---
        self.trends_group = QGroupBox(_t("weekly_trends"))
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

    def update_data(self, stats, cost, sub=None, cache_eff: float = 0.0,
                    savings: float = 0.0, comparison: dict | None = None,
                    projects: list | None = None) -> None:
        sub = sub or {}
        comparison = comparison or {}
        projects = projects or []
        is_sub = sub.get("type") in ("pro", "max", "team")
        parser = TokenParser()

        # --- Plan ---
        if is_sub:
            plan = sub.get("type", "").upper()
            tier = sub.get("tier", "")
            self.plan_label.setText(f"Plan: {plan}   |   Rate tier: {tier}")
        else:
            self.plan_label.setText("API billing")

        # --- Today ---
        self.today_sessions.setText(str(len(stats.sessions)))
        self.today_tokens.setText(_fmt(stats.total_billable))
        self.today_input.setText(_fmt(stats.total_input))
        self.today_output.setText(_fmt(stats.total_output))
        self.today_cache.setText(f"{cache_eff:.0f}%")
        if is_sub:
            self.today_saved.setText(f"~{_fmt(int(savings / 0.000025))} tokens")
        else:
            self.today_saved.setText(f"~${savings:.2f}")

        # --- Week ---
        week_data = parser.parse_range(days=7)
        week_total_sessions = sum(len(d.sessions) for d in week_data)
        week_total_billable = sum(d.total_billable for d in week_data)
        self.week_sessions.setText(str(week_total_sessions))
        self.week_tokens.setText(_fmt(week_total_billable))

        # --- Cache ---
        self.cache_label.setText(_t("cache_eff_pct").format(f"{cache_eff:.1f}"))
        self.cache_bar.setValue(int(cache_eff))
        self.savings_label.setText(_t("cache_saved_usd").format(f"{savings:.2f}"))

        # --- Models ---
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

        # --- Projects ---
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
        self.plan_label.setText(_t("no_analytics"))
        self.cache_label.setText(_t("no_analytics"))
