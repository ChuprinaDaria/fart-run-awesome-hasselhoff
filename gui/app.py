"""Claude Monitor — Dev Monitor GUI.

Win95 Explorer-style sidebar layout with unified refresh loop.
"""

import sys
import logging
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QStackedWidget, QLabel, QSystemTrayIcon, QMenu,
    QMessageBox,
)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPainter, QFont

# Ensure project root is in sys.path for direct script execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.config import load_config
from i18n import get_string as _t, set_language
from core.autodiscovery import discover_system, SystemState
from core.alerts import AlertManager
from core.plugin import Alert
from gui.sidebar import Sidebar, SidebarItem
from gui.pages.overview import OverviewPage
from gui.pages.security import SecurityPage, SecurityScanThread
from gui.pages.usage import UsagePage
from gui.pages.analytics import AnalyticsPage
from gui.pages.tips import TipsPage
from gui.pages.settings import SettingsPage
from gui.pages.hasselhoff_wizard import HasselhoffWizardPage
from gui.pages.discover import DiscoverTab
from gui.win95_popup import Win95Popup

log = logging.getLogger(__name__)


class DataCollectorThread(QThread):
    """Collect Docker + Ports data in background to avoid blocking GUI."""
    data_ready = pyqtSignal(dict)

    def __init__(self, docker_client, parent=None):
        super().__init__(parent)
        self._docker_client = docker_client

    def run(self):
        result = {"docker": [], "ports": []}

        if self._docker_client:
            try:
                from plugins.docker_monitor.collector import collect_containers
                containers = self._docker_client.containers.list(all=True)
                result["docker"] = collect_containers(containers)
            except Exception as e:
                log.error("Docker collect error: %s", e)

        try:
            from plugins.port_map.collector import collect_ports
            result["ports"] = collect_ports()
        except Exception as e:
            log.error("Ports collect error: %s", e)

        self.data_ready.emit(result)

WIN95_STYLE = """
QMainWindow, QWidget { background-color: #c0c0c0; font-family: "MS Sans Serif", "Liberation Sans", Arial, sans-serif; font-size: 12px; }
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
QMenuBar { background: #c0c0c0; border-bottom: 1px solid #808080; }
QMenuBar::item:selected { background: #000080; color: white; }
QMenu { background: #c0c0c0; border: 2px outset #dfdfdf; }
QMenu::item:selected { background: #000080; color: white; }
QStatusBar { background: #c0c0c0; border-top: 2px groove #808080; }
QCheckBox { spacing: 6px; }
QSpinBox { background: white; border: 2px inset #808080; padding: 2px; }
"""


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
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "M")
    painter.end()
    return QIcon(pixmap)


class MonitorApp(QMainWindow):
    """Main application window — Win95 Explorer style."""

    def __init__(self, config: dict, system_state: SystemState):
        super().__init__()
        self._config = config
        self._state = system_state
        self._alert_manager = AlertManager(config)

        self.setWindowTitle(_t("window_title"))
        self.setMinimumSize(950, 650)
        self.setStyleSheet(WIN95_STYLE)

        set_language(config.get("general", {}).get("language", "en"))

        self._create_menu_bar()

        # Central widget: sidebar + content stack
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar — no Docker/Ports, Hoff Wizard at end
        sidebar_items = [
            SidebarItem(_t("side_overview"), "overview"),
            SidebarItem(_t("side_security"), "security"),
            SidebarItem(_t("side_usage"), "usage"),
            SidebarItem(_t("side_analytics"), "analytics"),
            SidebarItem("", "", is_separator=True),
            SidebarItem(_t("side_tips"), "tips"),
            SidebarItem(_t("side_discover"), "discover"),
            SidebarItem(_t("side_settings"), "settings"),
            SidebarItem("", "", is_separator=True),
            SidebarItem("Hoff Wizard", "hoff_wizard"),
        ]
        self.sidebar = Sidebar(sidebar_items)
        self.sidebar.page_selected.connect(self._on_page_selected)
        main_layout.addWidget(self.sidebar)

        # Content stack
        self.stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}

        # Create pages (no Docker/Ports pages)
        self.page_overview = OverviewPage()
        self.page_security = SecurityPage()
        self.page_usage = UsagePage()
        self.page_analytics = AnalyticsPage()
        self.page_hoff_wizard = HasselhoffWizardPage()
        self.page_tips = TipsPage()
        self.page_discover = DiscoverTab()
        self.page_settings = SettingsPage(config)

        for key, page in [
            ("overview", self.page_overview),
            ("security", self.page_security),
            ("usage", self.page_usage),
            ("analytics", self.page_analytics),
            ("hoff_wizard", self.page_hoff_wizard),
            ("tips", self.page_tips),
            ("discover", self.page_discover),
            ("settings", self.page_settings),
        ]:
            self.stack.addWidget(page)
            self._pages[key] = page

        main_layout.addWidget(self.stack)
        self.setCentralWidget(central)

        self.statusBar().showMessage(_t("ready"))

        # Connect signals
        self.page_overview.refresh_requested.connect(self._refresh_all)
        self.page_overview.nag_requested.connect(self._do_nag)
        self.page_overview.hoff_requested.connect(self._do_hoff)
        self.page_security.scan_requested.connect(self._run_security_scan)
        self.page_hoff_wizard.hoff_event.connect(self._trigger_hasselhoff)
        self.page_settings.settings_changed.connect(self._on_settings_changed)

        # Apply autodiscovery state
        if not system_state.docker_available:
            self.page_overview.set_docker_error(
                system_state.docker_error or "Docker not available")
        if not system_state.claude_dir:
            self.page_overview.set_no_claude()
            self.page_analytics.set_no_claude()

        # Unified refresh timer
        refresh_interval = config["general"]["refresh_interval"] * 1000
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_all)
        self._refresh_timer.start(refresh_interval)

        # Security scan timer
        scan_interval = config["plugins"]["security_scan"]["scan_interval"] * 1000
        self._security_timer = QTimer(self)
        self._security_timer.timeout.connect(self._run_security_scan)
        self._security_timer.start(scan_interval)

        # Collector thread
        self._collector_thread = None
        self._collecting = False

        # Initial refresh
        self._refresh_all()
        self._run_security_scan()

    def _create_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu(_t("menu_file"))
        file_menu.addAction(_t("menu_refresh"), self._refresh_all, "Ctrl+R")
        file_menu.addSeparator()
        file_menu.addAction(_t("menu_quit"), self.close, "Ctrl+Q")

        tools_menu = menubar.addMenu(_t("menu_tools"))
        tools_menu.addAction(_t("menu_scan_security"), self._run_security_scan)
        tools_menu.addAction(_t("menu_nag_me"), self._do_nag)
        tools_menu.addAction(_t("menu_hasselhoff"), self._do_hoff)

        help_menu = menubar.addMenu(_t("menu_help"))
        help_menu.addAction(_t("menu_about"), self._show_about)

    def _on_page_selected(self, key: str):
        if key in self._pages:
            self.stack.setCurrentWidget(self._pages[key])

    def _on_settings_changed(self, new_config: dict):
        self._config = new_config
        self._alert_manager = AlertManager(new_config)
        set_language(new_config.get("general", {}).get("language", "en"))
        self.statusBar().showMessage("Settings applied", 3000)

    def _is_alert_enabled(self, source: str) -> bool:
        filters = self._config.get("alert_filters", {})
        return filters.get(source, True)

    def _refresh_all(self):
        if self._collecting:
            return
        self._collecting = True

        # Docker + Ports in background thread
        client = self._state.docker_client if self._state.docker_available else None
        self._collector_thread = DataCollectorThread(client, self)
        self._collector_thread.data_ready.connect(self._on_data_ready)
        self._collector_thread.start()

        # Claude stats
        if self._state.claude_dir:
            try:
                from core.token_parser import TokenParser
                from core.calculator import CostCalculator
                from core.usage_analyzer import Analyzer
                from core.nagger.messages import get_nag_message, get_nag_level

                parser = TokenParser()
                stats = parser.parse_today()
                calc = CostCalculator()
                cost = calc.calculate_cost(stats)
                cache_eff = Analyzer.cache_efficiency(stats)
                savings = Analyzer.cache_savings_usd(stats)
                comparison = Analyzer.model_comparison(stats)
                projects = Analyzer.project_breakdown(stats)

                level = get_nag_level(stats.total_billable)
                nag_msg = get_nag_message(level, stats.total_billable, len(stats.sessions))

                sub = parser.get_subscription()
                self.page_overview.set_subscription(sub)
                self.page_overview.update_data(stats, cost, cache_eff, savings, nag_msg)
                self.page_analytics.update_data(stats, cache_eff, savings, comparison, projects)
                self.page_usage.update_data(stats, cost, sub)
                self.page_tips.update_tips(stats, cost, sub)

                if self._is_alert_enabled("usage"):
                    self._check_usage_alerts(stats, sub)
            except Exception as e:
                log.error("Claude stats error: %s", e)

    def _on_data_ready(self, data: dict):
        self._collecting = False

        # Docker → compact widget on Overview
        infos = data.get("docker", [])
        self.page_overview.update_docker_compact(infos)
        if self._is_alert_enabled("docker"):
            self._check_docker_alerts(infos)

        # Ports → compact widget on Overview
        ports = data.get("ports", [])
        self.page_overview.update_ports_compact(ports)
        if self._is_alert_enabled("ports"):
            for p in ports:
                if p.get("conflict"):
                    self._alert_manager.process(Alert(
                        source="ports", severity="warning",
                        title=f"Port {p['port']} conflict",
                        message=f"Port {p['port']} used by multiple processes",
                    ))

        self.statusBar().showMessage(_t("ready"))

    def _check_docker_alerts(self, infos: list[dict]):
        """Docker alerts — no Hasselhoff, just problems."""
        cpu_thresh = self._config["plugins"]["docker_monitor"]["cpu_threshold"]
        ram_thresh = self._config["plugins"]["docker_monitor"]["ram_threshold"]

        for info in infos:
            name = info["name"]

            if info["status"] == "exited" and info.get("exit_code", 0) != 0:
                self._alert_manager.process(Alert(
                    source="docker", severity="critical",
                    title=f"{name} crashed (exit {info['exit_code']})",
                    message=f"Container {name} exited with code {info['exit_code']}",
                ))
            elif info["status"] == "running":
                if info["cpu_percent"] > cpu_thresh:
                    self._alert_manager.process(Alert(
                        source="docker", severity="warning",
                        title=f"{name} CPU {info['cpu_percent']:.0f}%",
                        message=f"CPU at {info['cpu_percent']:.1f}%",
                    ))
                if info["mem_limit"] > 0:
                    ram_pct = (info["mem_usage"] / info["mem_limit"]) * 100
                    if ram_pct > ram_thresh:
                        self._alert_manager.process(Alert(
                            source="docker", severity="critical",
                            title=f"{name} RAM {ram_pct:.0f}%",
                            message=f"RAM at {ram_pct:.1f}%",
                        ))

    def _check_usage_alerts(self, stats, sub: dict):
        """Alert on high token usage — no Hasselhoff."""
        is_api = sub.get("is_paid_tokens")
        if is_api:
            return

        if stats.total_billable > 800_000:
            self._alert_manager.process(Alert(
                source="usage", severity="warning",
                title=f"High usage: {stats.total_billable / 1_000_000:.1f}M tokens",
                message=f"You've used {stats.total_billable:,} billable tokens today. "
                        "Consider using /compact or switching to a lighter model.",
            ))
        if stats.total_billable > 2_000_000:
            self._alert_manager.process(Alert(
                source="usage", severity="critical",
                title=f"Very high usage: {stats.total_billable / 1_000_000:.1f}M tokens!",
                message=f"Burned through {stats.total_billable:,} tokens today. "
                        "Rate limits may hit soon!",
            ))

    def _run_security_scan(self):
        self.page_security.set_scanning(True)

        def scan():
            from plugins.security_scan.scanners import (
                Finding,
                scan_docker_security, scan_env_in_git,
                scan_exposed_ports,
                scan_firewall, scan_ssh_config, scan_system_updates,
                scan_sudoers, scan_world_writable,
                scan_sentinel_processes, scan_sentinel_network,
                scan_sentinel_filesystem, scan_sentinel_cron,
            )
            findings = []

            if self._state.docker_available and self._state.docker_client:
                try:
                    from plugins.docker_monitor.collector import collect_containers
                    containers = self._state.docker_client.containers.list(all=True)
                    infos = collect_containers(containers)
                    findings.extend(scan_docker_security(infos))
                except Exception:
                    pass

            scan_paths = [Path(p).expanduser() for p in
                          self._config["plugins"]["security_scan"].get("scan_paths", ["~"])]
            findings.extend(scan_env_in_git(scan_paths))

            try:
                from plugins.port_map.collector import collect_ports
                ports = collect_ports()
                findings.extend(scan_exposed_ports(ports))
                # Port conflicts as security findings
                for p in ports:
                    if p.get("conflict"):
                        findings.append(Finding(
                            "network", "warning",
                            f"Port {p['port']} conflict — multiple processes listening",
                            f"port:{p['port']}",
                        ))
            except Exception:
                pass

            findings.extend(scan_sentinel_processes())
            findings.extend(scan_sentinel_network())
            findings.extend(scan_sentinel_filesystem(scan_paths))
            findings.extend(scan_sentinel_cron())

            findings.extend(scan_firewall())
            findings.extend(scan_ssh_config())
            findings.extend(scan_system_updates())
            findings.extend(scan_sudoers())
            findings.extend(scan_world_writable())

            return [
                {"type": f.type, "severity": f.severity,
                 "description": f.description, "source": f.source}
                for f in findings
            ]

        self._scan_thread = SecurityScanThread(scan)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_done(self, findings: list[dict]):
        prev_keys = getattr(self, "_prev_security_keys", set())
        curr_keys = {f"{f['type']}:{f['description']}" for f in findings}
        new_keys = curr_keys - prev_keys
        self._prev_security_keys = curr_keys

        self.page_security.update_data(findings)
        self.page_security.set_scanning(False)

        critical_count = self.page_security.critical_count()
        self.sidebar.update_alert("security", critical_count)

        # Win95 popups for new critical/high findings
        if self._is_alert_enabled("security"):
            for f in findings:
                key = f"{f['type']}:{f['description']}"
                if key in new_keys and f["severity"] in ("critical", "high"):
                    self._alert_manager.process(Alert(
                        source="security", severity=f["severity"],
                        title=f"[{f['type']}] {f['description'][:50]}",
                        message=f["description"],
                    ))

    def _show_win95_alert(self, title: str, message: str, severity: str):
        """Show Win95-style popup for important alerts."""
        popup = Win95Popup(title, message, severity=severity, parent=self)
        popup.show()

    def _trigger_hasselhoff(self, message: str):
        """Hasselhoff — only from Wizard page and manual trigger."""
        try:
            from core.nagger.hasselhoff import get_hoff_phrase, get_hoff_image, get_victory_sound
            img_path = get_hoff_image()
            if img_path:
                self.page_overview.set_hoff_image(img_path)
            victory = get_victory_sound()
            if victory:
                self._alert_manager.play_file(Path(victory))
            phrase = get_hoff_phrase()
            self.statusBar().showMessage(f"HASSELHOFF: {message} — {phrase}", 8000)
        except ImportError:
            self.statusBar().showMessage(f"HASSELHOFF: {message}", 5000)

    def _do_nag(self):
        self._alert_manager.play_sound(Alert(
            source="nag", severity="critical", title="Nag", message="nag",
        ))

    def _do_hoff(self):
        self._trigger_hasselhoff("Manual Hasselhoff!")

    def _show_about(self):
        QMessageBox.about(
            self, _t("menu_about"),
            _t("about_text")
        )


class MonitorTrayApp:
    """System tray application wrapping MonitorApp."""

    def __init__(self, config: dict, system_state: SystemState):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.dashboard = MonitorApp(config, system_state)

        self.tray = QSystemTrayIcon(_make_tray_icon("green"), self.app)
        self.tray.setToolTip("Claude Monitor")
        self.tray.activated.connect(self._on_tray_click)

        self.menu = QMenu()
        self.menu.addAction("Show Dashboard", self._show)
        self.menu.addAction(_t("menu_nag_me"), self.dashboard._do_nag)
        self.menu.addAction(_t("menu_hasselhoff"), self.dashboard._do_hoff)
        self.menu.addSeparator()
        self.menu.addAction("Quit", self._quit)
        self.tray.setContextMenu(self.menu)

        self.tray.show()
        self.dashboard.show()

    def _on_tray_click(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show()

    def _show(self):
        self.dashboard.show()
        self.dashboard.raise_()

    def _quit(self):
        self.tray.hide()
        self.app.quit()

    def run(self):
        return self.app.exec_()


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    config = load_config()
    system_state = discover_system(config.get("paths", {}))

    app = MonitorTrayApp(config, system_state)
    sys.exit(app.run())


if __name__ == "__main__":
    main()
