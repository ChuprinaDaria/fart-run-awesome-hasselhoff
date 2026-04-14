"""Usage page — simple session stats for subscription users."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGroupBox,
                              QFormLayout)
from PyQt5.QtCore import Qt

from claude_nagger.core.parser import TokenParser
from claude_nagger.core.calculator import CostCalculator
from claude_nagger.core.analyzer import Analyzer
from claude_nagger.i18n import get_string, get_language


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class UsageTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # --- Plan info ---
        self.plan_label = QLabel("Plan: —")
        self.plan_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; padding: 8px; "
            "background: #000080; color: white; border: 2px outset #dfdfdf;"
        )
        layout.addWidget(self.plan_label)

        # --- Today stats ---
        self.today_group = QGroupBox(get_string("today"))
        tg = QFormLayout()
        self.today_sessions = QLabel("0")
        self.today_tokens = QLabel("0")
        self.today_input = QLabel("0")
        self.today_output = QLabel("0")
        self.today_cache = QLabel("0%")
        self.today_saved = QLabel("—")
        tg.addRow(get_string("sessions") + ":", self.today_sessions)
        tg.addRow("Total tokens:", self.today_tokens)
        tg.addRow("  Input:", self.today_input)
        tg.addRow("  Output:", self.today_output)
        tg.addRow("Cache efficiency:", self.today_cache)
        tg.addRow("Cache saved:", self.today_saved)
        self.today_group.setLayout(tg)
        layout.addWidget(self.today_group)

        # --- This week ---
        self.week_group = QGroupBox(get_string("this_week"))
        wg = QFormLayout()
        self.week_sessions = QLabel("0")
        self.week_tokens = QLabel("0")
        wg.addRow(get_string("sessions") + ":", self.week_sessions)
        wg.addRow("Total tokens:", self.week_tokens)
        self.week_group.setLayout(wg)
        layout.addWidget(self.week_group)

        layout.addStretch()

    def update_data(self, stats, cost, sub=None, current_session_id=None):
        sub = sub or {}
        is_sub = sub.get("type") in ("pro", "max", "team")
        parser = TokenParser()

        # --- Plan info ---
        if is_sub:
            plan = sub.get("type", "").upper()
            tier = sub.get("tier", "")
            self.plan_label.setText(f"Plan: {plan}   |   Rate tier: {tier}")
        else:
            self.plan_label.setText("API billing")

        # --- Today ---
        cache_eff = Analyzer.cache_efficiency(stats)
        savings = Analyzer.cache_savings_usd(stats)
        self.today_sessions.setText(str(len(stats.sessions)))
        self.today_tokens.setText(_fmt(stats.total_billable))
        self.today_input.setText(_fmt(stats.total_input))
        self.today_output.setText(_fmt(stats.total_output))
        self.today_cache.setText(f"{cache_eff:.0f}%")
        self.today_saved.setText(f"~${savings:.2f}" if not is_sub else f"~{_fmt(int(savings / 0.000025))} tokens")

        # --- Week ---
        week_data = parser.parse_range(days=7)
        week_total_sessions = sum(len(d.sessions) for d in week_data)
        week_total_billable = sum(d.total_billable for d in week_data)

        self.week_sessions.setText(str(week_total_sessions))
        self.week_tokens.setText(_fmt(week_total_billable))

    def retranslate(self):
        self.today_group.setTitle(get_string("today"))
        self.week_group.setTitle(get_string("this_week"))
