import sys
import os
import argparse
from PyQt5.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QMainWindow, QTabWidget,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
    QGroupBox, QFormLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QAction,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QPixmap,  QColor, QPainter, QFont

from claude_nagger.core.parser import TokenParser
from claude_nagger.core.calculator import CostCalculator
from claude_nagger.core.analyzer import Analyzer
from claude_nagger.core.tips import TipsEngine
from claude_nagger.core.sounds import SoundPlayer
from claude_nagger.nagger.messages import get_nag_message, get_nag_level
from claude_nagger.nagger.hasselhoff import get_hoff_phrase, get_hoff_image, get_victory_sound
from claude_nagger.i18n import get_string, set_language, get_language
from claude_nagger.gui.discover import DiscoverTab
from claude_nagger.gui.usage import UsageTab
from claude_nagger.gui.popup import NaggerPopup


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _make_tray_icon(color: str = "green") -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    colors = {"green": QColor(0, 200, 0), "yellow": QColor(255, 200, 0), "red": QColor(255, 50, 50)}
    painter.setBrush(colors.get(color, colors["green"]))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(2, 2, 28, 28)
    painter.setPen(QColor(255, 255, 255))
    painter.setFont(QFont("Arial", 14, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "C")
    painter.end()
    return QIcon(pixmap)


class OverviewTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.budget_label = QLabel("Budget: $0.00 / $5.00")
        self.budget_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.budget_label)
        self.budget_bar = QProgressBar()
        self.budget_bar.setMaximum(100)
        layout.addWidget(self.budget_bar)
        self.cost_label = QLabel("$0.0000")
        self.cost_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #000080; border: 2px inset #808080; background: white; padding: 8px;")
        self.cost_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.cost_label)

        self.stats_group = QGroupBox(get_string("tokens"))
        sl = QFormLayout()
        self.lbl_sessions = QLabel("0")
        self.lbl_input = QLabel("0")
        self.lbl_output = QLabel("0")
        self.lbl_cache_read = QLabel("0")
        self.lbl_cache_write = QLabel("0")
        self.lbl_billable = QLabel("0")
        self.lbl_cache_eff = QLabel("0%")
        self.lbl_cache_saved = QLabel("$0.00")
        self._row_labels = []
        for key, widget in [("sessions", self.lbl_sessions), ("input_tokens", self.lbl_input),
                            ("output_tokens", self.lbl_output), ("cache_read", self.lbl_cache_read),
                            ("cache_write", self.lbl_cache_write), ("billable", self.lbl_billable),
                            ("cache_efficiency", self.lbl_cache_eff), ("cache_saved", self.lbl_cache_saved)]:
            row_label = QLabel(get_string(key) + ":")
            self._row_labels.append((row_label, key))
            sl.addRow(row_label, widget)
        self.stats_group.setLayout(sl)
        layout.addWidget(self.stats_group)

        self.nag_label = QLabel("")
        self.nag_label.setWordWrap(True)
        self.nag_label.setStyleSheet("font-style: italic; padding: 8px; background: #ffffcc; color: #000; border: 2px inset #808080;")
        layout.addWidget(self.nag_label)
        self.hoff_label = QLabel()
        self.hoff_label.setAlignment(Qt.AlignCenter)
        self.hoff_label.setFixedHeight(120)
        layout.addWidget(self.hoff_label)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton(get_string("refresh"))
        self.btn_nag = QPushButton(get_string("nag_me"))
        self.btn_hoff = QPushButton(get_string("hoff_mode"))
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_nag)
        btn_layout.addWidget(self.btn_hoff)

        # Language selector
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["EN", "UA"])
        self.lang_combo.setCurrentText("UA" if get_language() == "ua" else "EN")
        lang_layout.addWidget(self.lang_combo)
        lang_layout.addStretch()

        # Subscription badge
        self.sub_label = QLabel("")
        self.sub_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #000080; background: #ffffcc; border: 2px outset #dfdfdf; padding: 2px 8px;")
        lang_layout.addWidget(self.sub_label)

        layout.addLayout(btn_layout)
        layout.addLayout(lang_layout)
        layout.addStretch()

    def retranslate(self):
        """Update all translatable labels."""
        self.stats_group.setTitle(get_string("tokens"))
        self.btn_refresh.setText(get_string("refresh"))
        self.btn_nag.setText(get_string("nag_me"))
        self.btn_hoff.setText(get_string("hoff_mode"))
        for lbl, key in self._row_labels:
            lbl.setText(get_string(key) + ":")


class AnalyticsTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.cache_label = QLabel("Cache Efficiency: 0%")
        self.cache_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.cache_label)
        self.cache_bar = QProgressBar()
        self.cache_bar.setMaximum(100)
        layout.addWidget(self.cache_bar)
        self.savings_label = QLabel("Cache saved: $0.00")
        layout.addWidget(self.savings_label)
        self.model_table = QTableWidget()
        self.model_table.setColumnCount(5)
        self.model_table.setHorizontalHeaderLabels(["Model", "Tokens", "Cost", "If Sonnet", "If Haiku"])
        self.model_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.model_table)
        self.project_table = QTableWidget()
        self.project_table.setColumnCount(3)
        self.project_table.setHorizontalHeaderLabels(["Project", "Billable Tokens", "Sessions"])
        self.project_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.project_table)
        layout.addStretch()


class CalculatorTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.cost_table = QTableWidget()
        self.cost_table.setColumnCount(2)
        self.cost_table.setHorizontalHeaderLabels(["Category", "Cost (USD)"])
        self.cost_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.cost_table.setRowCount(5)
        layout.addWidget(self.cost_table)
        wl = QHBoxLayout()
        wl.addWidget(QLabel("What if model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5"])
        wl.addWidget(self.model_combo)
        self.what_if_label = QLabel("$0.00")
        self.what_if_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #00cc00;")
        wl.addWidget(self.what_if_label)
        layout.addLayout(wl)
        self.monthly_label = QLabel("Monthly projection: $0.00")
        self.monthly_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.monthly_label)
        layout.addStretch()
        self._stats = None
        self.model_combo.currentTextChanged.connect(self._update_what_if)

    def _update_what_if(self):
        if not self._stats:
            return
        model = self.model_combo.currentText()
        calc = CostCalculator()
        alt = calc.what_if_model(self._stats, model)
        actual = calc.calculate_cost(self._stats)
        diff = actual.total_cost - alt.total_cost
        sign = "+" if diff < 0 else "-"
        color = "#ff3333" if diff < 0 else "#00cc00"
        self.what_if_label.setText(f"${alt.total_cost:.2f} ({sign}${abs(diff):.2f})")
        self.what_if_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {color};")


class TipsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.main_layout = QVBoxLayout(self)
        self.tips_layout = QVBoxLayout()
        self.main_layout.addLayout(self.tips_layout)
        self.main_layout.addStretch()

    def update_data(self, stats, cost, sub=None):
        while self.tips_layout.count():
            item = self.tips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        tips = TipsEngine.get_tips(stats, cost, subscription=sub)
        lang_attr = "message_ua" if get_language() == "ua" else "message_en"
        icons = {"cache": "\U0001f4e6", "model": "\U0001f916", "prompt": "\u270f\ufe0f",
                 "session": "\U0001f4dd", "docs": "\U0001f4da"}
        for tip in tips[:10]:
            icon = icons.get(tip.category, "\U0001f4a1")
            lbl = QLabel(f"{icon}  {getattr(tip, lang_attr)}")
            lbl.setWordWrap(True)
            bc = "#ff6600" if tip.relevance > 0.8 else "#666"
            lbl.setStyleSheet(f"padding: 6px; margin: 2px; background: #ffffcc; color: #000; border: 1px solid #808080; border-left: 3px solid {bc};")
            self.tips_layout.addWidget(lbl)


WIN95_STYLE = """
QMainWindow, QWidget { background-color: #c0c0c0; font-family: "MS Sans Serif", "Liberation Sans", Arial, sans-serif; font-size: 12px; }
QTabWidget::pane { border: 2px solid #808080; background: #c0c0c0; }
QTabBar::tab { background: #c0c0c0; border: 2px outset #dfdfdf; padding: 4px 12px; min-width: 80px; }
QTabBar::tab:selected { background: #c0c0c0; border: 2px inset #808080; }
QPushButton { background: #c0c0c0; border: 2px outset #dfdfdf; padding: 4px 12px; font-weight: bold; }
QPushButton:pressed { border: 2px inset #808080; }
QProgressBar { border: 2px inset #808080; background: white; text-align: center; height: 20px; }
QProgressBar::chunk { background: #000080; }
QGroupBox { border: 2px groove #808080; margin-top: 12px; padding-top: 16px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QTableWidget { background: white; border: 2px inset #808080; gridline-color: #808080; }
QHeaderView::section { background: #c0c0c0; border: 1px outset #dfdfdf; padding: 2px; font-weight: bold; }
QComboBox { background: white; border: 2px inset #808080; padding: 2px; }
QLabel { color: #000000; }
"""


class NaggerDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("fart.run & amazing Hasselhoff")
        self.setMinimumSize(750, 550)
        self.setStyleSheet(WIN95_STYLE)
        self.budget = 5.0
        self.sounds = SoundPlayer()
        self.tabs = QTabWidget()
        self.tab_overview = OverviewTab()
        self.tab_usage = UsageTab()
        self.tab_analytics = AnalyticsTab()
        self.tab_calculator = CalculatorTab()
        self.tab_tips = TipsTab()
        self.tab_discover = DiscoverTab()
        self.tabs.addTab(self.tab_overview, get_string("tab_overview"))
        self.tabs.addTab(self.tab_usage, get_string("tab_usage"))
        self.tabs.addTab(self.tab_analytics, get_string("tab_analytics"))
        self.tabs.addTab(self.tab_calculator, get_string("tab_calculator"))
        self.tabs.addTab(self.tab_tips, get_string("tab_tips"))
        self.tabs.addTab(self.tab_discover, get_string("tab_discover"))
        self.setCentralWidget(self.tabs)
        self.tab_overview.btn_refresh.clicked.connect(self.refresh_data)
        self.tab_overview.btn_nag.clicked.connect(self.do_nag)
        self.tab_overview.btn_hoff.clicked.connect(self.do_hoff)
        self.tab_overview.lang_combo.currentTextChanged.connect(self._change_lang)

        # Auto-refresh every 60 seconds
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_data)
        self._refresh_timer.start(60_000)

        self.refresh_data()

    def _change_lang(self, lang_text: str):
        set_language("ua" if lang_text == "UA" else "en")
        self.tab_overview.retranslate()
        self.tab_usage.retranslate()
        self.tab_discover.retranslate()
        self.tabs.setTabText(0, get_string("tab_overview"))
        self.tabs.setTabText(1, get_string("tab_usage"))
        self.tabs.setTabText(2, get_string("tab_analytics"))
        self.tabs.setTabText(3, get_string("tab_calculator"))
        self.tabs.setTabText(4, get_string("tab_tips"))
        self.tabs.setTabText(5, get_string("tab_discover"))
        self.refresh_data()

    def refresh_data(self):
        parser = TokenParser()
        stats = parser.parse_today()
        sub = parser.get_subscription()
        calc = CostCalculator()
        cost = calc.calculate_cost(stats)
        cache_eff = Analyzer.cache_efficiency(stats)
        savings = Analyzer.cache_savings_usd(stats)
        comparison = Analyzer.model_comparison(stats)
        projects = Analyzer.project_breakdown(stats)
        self._stats = stats
        self._cost = cost
        is_sub = sub.get("type") in ("pro", "max", "team")

        ov = self.tab_overview
        ov.sub_label.setText(f"Plan: {sub.get('type', 'unknown').upper()}" if is_sub else "API")
        if is_sub:
            budget_tokens = 5_000_000
            pct = min(stats.total_billable / budget_tokens * 100, 100)
            ov.budget_label.setText(f"Tokens: {_fmt(stats.total_billable)} / {_fmt(budget_tokens)} (use /usage)")
        else:
            pct = min(cost.total_cost / self.budget * 100, 100) if self.budget > 0 else 0
            ov.budget_label.setText(f"Budget: ${cost.total_cost:.2f} / ${self.budget:.2f}")
        ov.budget_bar.setValue(int(pct))
        cc = "#00cc00" if pct < 33 else ("#ffcc00" if pct < 66 else "#ff3333")
        ov.budget_bar.setStyleSheet(f"QProgressBar::chunk {{ background: {cc}; }}")
        ov.cost_label.setText(f"${cost.total_cost:.2f}")
        ov.cost_label.setStyleSheet(f"font-size: 28px; font-weight: bold; color: {cc};")
        ov.lbl_sessions.setText(str(len(stats.sessions)))
        ov.lbl_input.setText(_fmt(stats.total_input))
        ov.lbl_output.setText(_fmt(stats.total_output))
        ov.lbl_cache_read.setText(_fmt(stats.total_cache_read))
        ov.lbl_cache_write.setText(_fmt(stats.total_cache_write))
        ov.lbl_billable.setText(_fmt(stats.total_billable))
        ov.lbl_cache_eff.setText(f"{cache_eff:.1f}%")
        ov.lbl_cache_saved.setText(f"~${savings:.2f}")
        level = get_nag_level(stats.total_billable)
        msg = get_nag_message(level, stats.total_billable, len(stats.sessions))
        ov.nag_label.setText(f'"{msg}"')

        an = self.tab_analytics
        an.cache_label.setText(f"Cache Efficiency: {cache_eff:.1f}%")
        an.cache_bar.setValue(int(cache_eff))
        an.savings_label.setText(f"Cache saved: ~${savings:.2f}")
        an.model_table.setRowCount(len(stats.model_totals))
        for i, (model, mu) in enumerate(stats.model_totals.items()):
            name = model.replace("claude-", "").upper()
            an.model_table.setItem(i, 0, QTableWidgetItem(name))
            an.model_table.setItem(i, 1, QTableWidgetItem(_fmt(mu.billable_tokens)))
            an.model_table.setItem(i, 2, QTableWidgetItem(f"${comparison.get('actual', 0):.2f}"))
            an.model_table.setItem(i, 3, QTableWidgetItem(f"${comparison.get('claude-sonnet-4-6', 0):.2f}"))
            an.model_table.setItem(i, 4, QTableWidgetItem(f"${comparison.get('claude-haiku-4-5', 0):.2f}"))
        an.project_table.setRowCount(min(len(projects), 10))
        for i, p in enumerate(projects[:10]):
            an.project_table.setItem(i, 0, QTableWidgetItem(p.project))
            an.project_table.setItem(i, 1, QTableWidgetItem(_fmt(p.total_billable)))
            an.project_table.setItem(i, 2, QTableWidgetItem(str(p.sessions)))

        ct = self.tab_calculator
        ct._stats = stats
        for i, (cat, val) in enumerate([("Input", f"${cost.input_cost:.2f}"), ("Output", f"${cost.output_cost:.2f}"),
                ("Cache Read", f"${cost.cache_read_cost:.2f}"), ("Cache Write", f"${cost.cache_write_cost:.2f}"),
                ("Total", f"${cost.total_cost:.2f}")]):
            ct.cost_table.setItem(i, 0, QTableWidgetItem(cat))
            ct.cost_table.setItem(i, 1, QTableWidgetItem(val))
        ct.monthly_label.setText(f"Monthly projection: ${calc.monthly_projection(stats):.2f}")
        ct._update_what_if()

        self.tab_usage.update_data(stats, cost, sub)
        self.tab_tips.update_data(stats, cost, sub)

    def do_nag(self):
        self.sounds.play_random("farts")
        self.refresh_data()
        if hasattr(self, '_stats'):
            level = get_nag_level(self._stats.total_billable)
            msg = get_nag_message(level, self._stats.total_billable, len(self._stats.sessions))
            self._notify("Claude Nagger", msg, timeout=8)

    def do_hoff(self):
        img_path = get_hoff_image()
        if img_path:
            pixmap = QPixmap(img_path).scaledToHeight(100, Qt.SmoothTransformation)
            self.tab_overview.hoff_label.setPixmap(pixmap)
        v = get_victory_sound()
        if v:
            self.sounds.play(v)
        phrase = get_hoff_phrase()
        self._notify("HASSELHOFF MODE!", phrase, timeout=6, icon=img_path)

    def _notify(self, title: str, body: str, timeout: int = 8, icon: str = None):
        """Show custom popup notification with large image."""
        popup = NaggerPopup(title, body, image_path=icon, timeout_ms=timeout * 1000)
        popup.show()
        # Keep reference to prevent garbage collection
        if not hasattr(self, '_popups'):
            self._popups = []
        self._popups = [p for p in self._popups if p.isVisible()]
        self._popups.append(popup)


class NaggerTrayApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.dashboard = NaggerDashboard()
        self.sounds = SoundPlayer()
        self.tray = QSystemTrayIcon(_make_tray_icon("green"), self.app)
        self.tray.setToolTip("fart.run & amazing Hasselhoff")
        self.tray.activated.connect(self._on_tray_click)
        self.menu = QMenu()
        self.a_stats = self.menu.addAction(get_string("quick_stats"))
        self.a_stats.triggered.connect(self._show)
        self.a_nag = self.menu.addAction(get_string("nag_me"))
        self.a_nag.triggered.connect(self._nag)
        self.a_hoff = self.menu.addAction(get_string("hoff_mode"))
        self.a_hoff.triggered.connect(self._hoff)
        self.menu.addSeparator()
        self.a_quit = self.menu.addAction(get_string("quit"))
        self.a_quit.triggered.connect(self._quit)
        self.tray.setContextMenu(self.menu)
        # Connect lang change from dashboard to retranslate tray menu
        self.dashboard.tab_overview.lang_combo.currentTextChanged.connect(self._retranslate_menu)
        self.tray.show()

        # Tray update every 5 min
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_tray)
        self.timer.start(300_000)
        self._update_tray()

        # Auto-nag timer: random popup every 20-40 min
        import random
        self._nag_timer = QTimer()
        self._nag_timer.timeout.connect(self._auto_nag)
        self._nag_timer.start(random.randint(20, 40) * 60_000)

        # Watcher: monitor for docker/build errors and test success
        self._watch_timer = QTimer()
        self._watch_timer.timeout.connect(self._watch_events)
        self._watch_timer.start(30_000)  # check every 30s
        self._last_session_count = 0
        self._last_billable = 0

    def _retranslate_menu(self):
        self.a_stats.setText(get_string("quick_stats"))
        self.a_nag.setText(get_string("nag_me"))
        self.a_hoff.setText(get_string("hoff_mode"))
        self.a_quit.setText(get_string("quit"))

    def _quit(self):
        self.tray.hide()
        self.app.quit()

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show()

    def _show(self):
        self.dashboard.refresh_data()
        self.dashboard.show()
        self.dashboard.raise_()

    def _nag(self):
        self.sounds.play_random("farts")
        self.dashboard.refresh_data()
        stats = self.dashboard._stats
        level = get_nag_level(stats.total_billable)
        msg = get_nag_message(level, stats.total_billable, len(stats.sessions))
        self._notify_popup("Claude Nagger", msg)

    def _hoff(self):
        phrase = get_hoff_phrase()
        v = get_victory_sound()
        if v:
            self.sounds.play(v)
        img = get_hoff_image()
        self._notify_popup("HASSELHOFF MODE!", phrase, icon=img)

    def _auto_nag(self):
        """Auto-popup nag on timer — checks if Claude is active."""
        import random, subprocess
        # Only nag if claude is running
        try:
            result = subprocess.run(["pgrep", "-f", "claude"], capture_output=True)
            if result.returncode != 0:
                return  # Claude not running, skip
        except FileNotFoundError:
            pass  # Windows, always nag

        self.dashboard.refresh_data()
        stats = self.dashboard._stats
        if stats.total_billable > 10000:
            self.sounds.play_random("farts")
            level = get_nag_level(stats.total_billable)
            msg = get_nag_message(level, stats.total_billable, len(stats.sessions))
            self._notify_popup("Claude Nagger", msg)

        # Randomize next interval (15-35 min)
        self._nag_timer.start(random.randint(15, 35) * 60_000)

    def _watch_events(self):
        """Monitor for errors (docker, tests) and successes."""
        import subprocess
        self.dashboard.refresh_data()
        stats = self.dashboard._stats

        # Detect new activity (billable jumped)
        if self._last_billable > 0 and stats.total_billable > self._last_billable:
            delta = stats.total_billable - self._last_billable
            # Big jump = heavy session activity
            if delta > 50000:
                self.sounds.play_random("farts")
                self._notify_popup("Claude Nagger",
                    f"+{_fmt(delta)} tokens since last check! Slow down, cowboy.")

        self._last_billable = stats.total_billable
        self._last_session_count = len(stats.sessions)

        # Check for docker errors (last 60s of docker logs)
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", "status=exited",
                 "--filter", "exited=1", "--format", "{{.Names}}: {{.Status}}",
                 "--since", "60s"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                failed = result.stdout.strip().split("\n")[0]
                self.sounds.play_random("farts")
                self._notify_popup("Docker FAIL!",
                    f"Container crashed: {failed}\nMaybe touch some grass instead?")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    def _notify_popup(self, title: str, body: str, timeout: int = 8, icon: str = None):
        """Show custom popup notification with large image."""
        popup = NaggerPopup(title, body, image_path=icon, timeout_ms=timeout * 1000)
        popup.show()
        if not hasattr(self, '_popups'):
            self._popups = []
        self._popups = [p for p in self._popups if p.isVisible()]
        self._popups.append(popup)

    def _update_tray(self):
        parser = TokenParser()
        stats = parser.parse_today()
        calc = CostCalculator()
        cost = calc.calculate_cost(stats)
        pct = cost.total_cost / self.dashboard.budget * 100 if self.dashboard.budget > 0 else 0
        color = "green" if pct < 33 else ("yellow" if pct < 66 else "red")
        self.tray.setIcon(_make_tray_icon(color))
        self.tray.setToolTip(f"Today: ${cost.total_cost:.2f} | {_fmt(stats.total_billable)} tokens")

    def run(self):
        return self.app.exec_()


def main():
    parser = argparse.ArgumentParser(description="Claude Nagger GUI")
    parser.add_argument("--lang", "-l", default="en", choices=["en", "ua"])
    args = parser.parse_args()
    set_language(args.lang)
    app = NaggerTrayApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
