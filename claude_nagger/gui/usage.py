from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QLabel, QGroupBox,
                              QFormLayout, QTableWidget, QTableWidgetItem,
                              QHeaderView, QScrollArea)
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

        # --- Current session ---
        self.session_group = QGroupBox(get_string("this_session"))
        sg = QFormLayout()
        self.sess_tokens = QLabel("0")
        self.sess_cost = QLabel("$0.00")
        self.sess_cache = QLabel("0%")
        sg.addRow("Billable:", self.sess_tokens)
        sg.addRow("API equiv.:", self.sess_cost)
        sg.addRow("Cache:", self.sess_cache)
        self.session_group.setLayout(sg)
        layout.addWidget(self.session_group)

        # --- Today ---
        self.today_group = QGroupBox(get_string("today"))
        tg = QFormLayout()
        self.today_sessions = QLabel("0")
        self.today_tokens = QLabel("0")
        self.today_cost = QLabel("$0.00")
        self.today_cache = QLabel("0%")
        self.today_saved = QLabel("$0.00")
        tg.addRow(get_string("sessions") + ":", self.today_sessions)
        tg.addRow("Billable:", self.today_tokens)
        tg.addRow("API equiv.:", self.today_cost)
        tg.addRow("Cache:", self.today_cache)
        tg.addRow(get_string("cache_saved") + ":", self.today_saved)
        self.today_group.setLayout(tg)
        layout.addWidget(self.today_group)

        # --- This week ---
        self.week_group = QGroupBox(get_string("this_week"))
        wg = QFormLayout()
        self.week_sessions = QLabel("0")
        self.week_tokens = QLabel("0")
        self.week_cost = QLabel("$0.00")
        self.week_avg = QLabel("$0.00")
        wg.addRow(get_string("sessions") + ":", self.week_sessions)
        wg.addRow("Billable:", self.week_tokens)
        wg.addRow("API equiv.:", self.week_cost)
        wg.addRow(get_string("per_day") + " avg:", self.week_avg)
        self.week_group.setLayout(wg)
        layout.addWidget(self.week_group)

        # --- Daily breakdown table ---
        self.daily_table = QTableWidget()
        self.daily_table.setColumnCount(4)
        self.daily_table.setHorizontalHeaderLabels(["Date", "Sessions", "Billable", "API equiv."])
        self.daily_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.daily_table.setMaximumHeight(200)
        layout.addWidget(self.daily_table)

        # --- Subscription info ---
        self.sub_info = QLabel("")
        self.sub_info.setWordWrap(True)
        self.sub_info.setStyleSheet(
            "padding: 8px; background: #ffffcc; border: 2px inset #808080; color: #000;"
        )
        layout.addWidget(self.sub_info)

        layout.addStretch()

        # Store label refs for retranslate
        self._form_labels_session = [("Billable:", 0), ("API equiv.:", 1), ("Cache:", 2)]
        self._form_labels_today = []

    def update_data(self, stats, cost, sub=None, current_session_id=None):
        sub = sub or {}
        is_sub = sub.get("type") in ("pro", "max", "team")
        parser = TokenParser()
        calc = CostCalculator()

        # --- Current session (latest/largest) ---
        if stats.sessions:
            # Find the largest active session
            latest = max(stats.sessions,
                         key=lambda s: sum(mu.billable_tokens for mu in s.model_stats.values()))
            sess_billable = sum(mu.billable_tokens for mu in latest.model_stats.values())
            sess_cache_read = sum(mu.cache_read for mu in latest.model_stats.values())
            sess_total = sess_cache_read + sum(mu.input + mu.cache_write for mu in latest.model_stats.values())
            sess_eff = (sess_cache_read / sess_total * 100) if sess_total > 0 else 0

            from claude_nagger.core.models import TokenStats
            sess_stats = TokenStats(
                date=stats.date, sessions=[latest],
                total_input=sum(mu.input for mu in latest.model_stats.values()),
                total_output=sum(mu.output for mu in latest.model_stats.values()),
                total_cache_read=sess_cache_read,
                total_cache_write=sum(mu.cache_write for mu in latest.model_stats.values()),
                total_billable=sess_billable,
                model_totals=latest.model_stats,
            )
            sess_cost = calc.calculate_cost(sess_stats)

            self.sess_tokens.setText(_fmt(sess_billable))
            self.sess_cost.setText(f"${sess_cost.total_cost:.2f}")
            self.sess_cache.setText(f"{sess_eff:.0f}%")
            self.session_group.setTitle(f"{get_string('this_session')} ({latest.project})")
        else:
            self.sess_tokens.setText("0")
            self.sess_cost.setText("$0.00")
            self.sess_cache.setText("0%")

        # --- Today ---
        cache_eff = Analyzer.cache_efficiency(stats)
        savings = Analyzer.cache_savings_usd(stats)
        self.today_sessions.setText(str(len(stats.sessions)))
        self.today_tokens.setText(_fmt(stats.total_billable))
        self.today_cost.setText(f"${cost.total_cost:.2f}")
        self.today_cache.setText(f"{cache_eff:.0f}%")
        self.today_saved.setText(f"~${savings:.2f}")

        # --- Week ---
        week_data = parser.parse_range(days=7)
        week_total_sessions = 0
        week_total_billable = 0
        week_total_cost = 0.0
        days_with_data = 0

        self.daily_table.setRowCount(len(week_data))
        for i, day_stats in enumerate(week_data):
            day_cost = calc.calculate_cost(day_stats)
            n_sessions = len(day_stats.sessions)
            week_total_sessions += n_sessions
            week_total_billable += day_stats.total_billable
            week_total_cost += day_cost.total_cost
            if day_stats.total_billable > 0:
                days_with_data += 1

            self.daily_table.setItem(i, 0, QTableWidgetItem(day_stats.date))
            self.daily_table.setItem(i, 1, QTableWidgetItem(str(n_sessions)))
            self.daily_table.setItem(i, 2, QTableWidgetItem(_fmt(day_stats.total_billable)))
            self.daily_table.setItem(i, 3, QTableWidgetItem(f"${day_cost.total_cost:.2f}"))

        self.week_sessions.setText(str(week_total_sessions))
        self.week_tokens.setText(_fmt(week_total_billable))
        self.week_cost.setText(f"${week_total_cost:.2f}")
        avg = week_total_cost / max(days_with_data, 1)
        self.week_avg.setText(f"${avg:.2f}")

        # --- Subscription info ---
        if is_sub:
            plan = sub.get("type", "").upper()
            tier = sub.get("tier", "")
            self.sub_info.setText(
                f"Plan: {plan} | Rate tier: {tier}\n"
                f"Weekly API equiv.: ${week_total_cost:.2f} | "
                f"Monthly projection: ${avg * 30:.2f}\n"
                f"Use /usage in Claude CLI for exact remaining quota"
            )
            self.sub_info.show()
        else:
            self.sub_info.setText(
                f"API billing | Weekly: ${week_total_cost:.2f} | "
                f"Monthly projection: ${avg * 30:.2f}"
            )
            self.sub_info.show()

    def retranslate(self):
        self.session_group.setTitle(get_string("this_session"))
        self.today_group.setTitle(get_string("today"))
        self.week_group.setTitle(get_string("this_week"))
