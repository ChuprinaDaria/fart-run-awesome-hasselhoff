"""fart.run & awesome Hasselhoff — Dev Monitor GUI.

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
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPainter, QFont

# Ensure project root is in sys.path for direct script execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.config import load_config
from core.autodiscovery import discover_system, SystemState
from core.alerts import AlertManager
from core.plugin import Alert
from gui.sidebar import Sidebar, SidebarItem
from gui.pages.overview import OverviewPage
from gui.pages.docker import DockerPage
from gui.pages.ports import PortsPage
from gui.pages.security import SecurityPage, SecurityScanThread
from gui.pages.usage import UsagePage
from gui.pages.analytics import AnalyticsPage

log = logging.getLogger(__name__)

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
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "F")
    painter.end()
    return QIcon(pixmap)


class MonitorApp(QMainWindow):
    """Main application window — Win95 Explorer style."""

    def __init__(self, config: dict, system_state: SystemState):
        super().__init__()
        self._config = config
        self._state = system_state
        self._alert_manager = AlertManager(config)

        self.setWindowTitle("fart.run & awesome Hasselhoff — Dev Monitor")
        self.setMinimumSize(950, 650)
        self.setStyleSheet(WIN95_STYLE)

        # Menu bar
        self._create_menu_bar()

        # Central widget: sidebar + content stack
        central = QWidget()
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar_items = [
            SidebarItem("Overview", "overview"),
            SidebarItem("Docker", "docker"),
            SidebarItem("Ports", "ports"),
            SidebarItem("Security", "security"),
            SidebarItem("Usage", "usage"),
            SidebarItem("Analytics", "analytics"),
            SidebarItem("", "", is_separator=True),
            SidebarItem("Settings", "settings"),
        ]
        self.sidebar = Sidebar(sidebar_items)
        self.sidebar.page_selected.connect(self._on_page_selected)
        main_layout.addWidget(self.sidebar)

        # Content stack
        self.stack = QStackedWidget()
        self._pages: dict[str, QWidget] = {}

        # Create pages
        self.page_overview = OverviewPage()
        self.page_docker = DockerPage(system_state.docker_client)
        self.page_ports = PortsPage()
        self.page_security = SecurityPage()
        self.page_usage = UsagePage()
        self.page_analytics = AnalyticsPage()
        self.page_settings = QLabel("Settings — coming soon")
        self.page_settings.setAlignment(Qt.AlignCenter)

        for key, page in [
            ("overview", self.page_overview),
            ("docker", self.page_docker),
            ("ports", self.page_ports),
            ("security", self.page_security),
            ("usage", self.page_usage),
            ("analytics", self.page_analytics),
            ("settings", self.page_settings),
        ]:
            self.stack.addWidget(page)
            self._pages[key] = page

        main_layout.addWidget(self.stack)
        self.setCentralWidget(central)

        # Status bar
        self.statusBar().showMessage("Ready")

        # Connect signals
        self.page_overview.refresh_requested.connect(self._refresh_all)
        self.page_overview.nag_requested.connect(self._do_nag)
        self.page_overview.hoff_requested.connect(self._do_hoff)
        self.page_docker.fart_off_triggered.connect(self._on_fart_off)
        self.page_docker.container_count_changed.connect(
            lambda n: self.sidebar.update_counter("docker", n)
        )
        self.page_security.scan_requested.connect(self._run_security_scan)

        # Apply autodiscovery state
        if not system_state.docker_available:
            self.page_docker.set_docker_error(system_state.docker_error or "Docker not available")
        if not system_state.claude_dir:
            self.page_overview.set_no_claude()
            self.page_analytics.set_no_claude()
        if system_state.psutil_limited:
            self.page_ports.set_psutil_warning(True)

        # Unified refresh timer
        refresh_interval = config["general"]["refresh_interval"] * 1000
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_all)
        self._refresh_timer.start(refresh_interval)

        # Security scan timer (separate, longer interval)
        scan_interval = config["plugins"]["security_scan"]["scan_interval"] * 1000
        self._security_timer = QTimer(self)
        self._security_timer.timeout.connect(self._run_security_scan)
        self._security_timer.start(scan_interval)

        # Initial refresh
        self._refresh_all()
        self._run_security_scan()

    def _create_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        file_menu.addAction("Refresh", self._refresh_all, "Ctrl+R")
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close, "Ctrl+Q")

        tools_menu = menubar.addMenu("Tools")
        tools_menu.addAction("Scan Security", self._run_security_scan)
        tools_menu.addAction("Nag Me", self._do_nag)
        tools_menu.addAction("Hasselhoff!", self._do_hoff)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self._show_about)

    def _on_page_selected(self, key: str):
        if key in self._pages:
            self.stack.setCurrentWidget(self._pages[key])

    def _refresh_all(self):
        """Single refresh loop — collects data from all sources."""
        # Docker
        if self._state.docker_available and self._state.docker_client:
            try:
                from plugins.docker_monitor.collector import collect_containers
                containers = self._state.docker_client.containers.list(all=True)
                infos = collect_containers(containers)
                self.page_docker.update_data(infos)
                self._check_docker_alerts(infos)
            except Exception as e:
                log.error("Docker refresh error: %s", e)

        # Ports
        try:
            from plugins.port_map.collector import collect_ports
            ports = collect_ports()
            self.page_ports.update_data(ports)
            self.sidebar.update_counter("ports", len(ports))

            for p in ports:
                if p.get("conflict"):
                    self._alert_manager.process(Alert(
                        source="ports", severity="warning",
                        title=f"Port {p['port']} conflict",
                        message=f"Port {p['port']} used by multiple processes",
                    ))
        except Exception as e:
            log.error("Ports refresh error: %s", e)

        # Claude stats (if available)
        if self._state.claude_dir:
            try:
                from claude_nagger.core.parser import TokenParser
                from claude_nagger.core.calculator import CostCalculator
                from claude_nagger.core.analyzer import Analyzer
                from claude_nagger.nagger.messages import get_nag_message, get_nag_level

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

                self.page_overview.update_data(stats, cost, cache_eff, savings, nag_msg)
                self.page_analytics.update_data(stats, cache_eff, savings, comparison, projects)

                sub = parser.get_subscription()
                self.page_usage.update_data(stats, cost, sub)
            except Exception as e:
                log.error("Claude stats error: %s", e)

        self.statusBar().showMessage(
            f"Docker: {self.sidebar.item_text('docker')} | "
            f"Ports: {self.sidebar.item_text('ports')} | "
            f"Ready"
        )

    def _check_docker_alerts(self, infos: list[dict]):
        cpu_thresh = self._config["plugins"]["docker_monitor"]["cpu_threshold"]
        ram_thresh = self._config["plugins"]["docker_monitor"]["ram_threshold"]

        for info in infos:
            if info["status"] == "exited" and info.get("exit_code", 0) != 0:
                self._alert_manager.process(Alert(
                    source="docker", severity="critical",
                    title=f"{info['name']} crashed (exit {info['exit_code']})",
                    message=f"Container {info['name']} exited with code {info['exit_code']}",
                ))
            elif info["status"] == "running":
                if info["cpu_percent"] > cpu_thresh:
                    self._alert_manager.process(Alert(
                        source="docker", severity="warning",
                        title=f"{info['name']} CPU {info['cpu_percent']:.0f}%",
                        message=f"CPU at {info['cpu_percent']:.1f}%",
                    ))
                if info["mem_limit"] > 0:
                    ram_pct = (info["mem_usage"] / info["mem_limit"]) * 100
                    if ram_pct > ram_thresh:
                        self._alert_manager.process(Alert(
                            source="docker", severity="critical",
                            title=f"{info['name']} RAM {ram_pct:.0f}%",
                            message=f"RAM at {ram_pct:.1f}%",
                        ))

    def _run_security_scan(self):
        self.page_security.set_scanning(True)

        def scan():
            from plugins.security_scan.scanners import (
                scan_docker_security, scan_env_in_git,
                scan_file_permissions, scan_exposed_ports,
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
            findings.extend(scan_file_permissions(scan_paths))

            try:
                from plugins.port_map.collector import collect_ports
                ports = collect_ports()
                findings.extend(scan_exposed_ports(ports))
            except Exception:
                pass

            return [
                {"type": f.type, "severity": f.severity,
                 "description": f.description, "source": f.source}
                for f in findings
            ]

        self._scan_thread = SecurityScanThread(scan)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_done(self, findings: list[dict]):
        self.page_security.update_data(findings)
        self.page_security.set_scanning(False)

        critical = self.page_security.critical_count()
        self.sidebar.update_alert("security", critical)

        for f in findings:
            if f["severity"] in ("critical", "high"):
                self._alert_manager.process(Alert(
                    source="security", severity=f["severity"],
                    title=f"[{f['type']}] {f['description'][:50]}",
                    message=f["description"],
                ))

    def _on_fart_off(self, container_name: str):
        self._alert_manager.play_sound(Alert(
            source="docker", severity="warning",
            title=f"Fart Off: {container_name}",
            message=f"Stopping {container_name}",
        ))

    def _do_nag(self):
        self._alert_manager.play_sound(Alert(
            source="nag", severity="critical", title="Nag", message="nag",
        ))

    def _do_hoff(self):
        try:
            from claude_nagger.nagger.hasselhoff import get_hoff_phrase, get_hoff_image, get_victory_sound
            img_path = get_hoff_image()
            if img_path:
                self.page_overview.set_hoff_image(img_path)
            victory = get_victory_sound()
            if victory:
                self._alert_manager._play_file(Path(victory))
            phrase = get_hoff_phrase()
            self.statusBar().showMessage(f"HASSELHOFF: {phrase}", 5000)
        except ImportError:
            self.statusBar().showMessage("Hasselhoff requires claude_nagger module", 3000)

    def _show_about(self):
        QMessageBox.about(
            self, "About",
            "fart.run & awesome Hasselhoff\n"
            "Dev Environment Monitor v3.0\n\n"
            "Win95 style, fart-powered alerts,\n"
            "and David Hasselhoff supervision."
        )


class MonitorTrayApp:
    """System tray application wrapping MonitorApp."""

    def __init__(self, config: dict, system_state: SystemState):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.dashboard = MonitorApp(config, system_state)

        self.tray = QSystemTrayIcon(_make_tray_icon("green"), self.app)
        self.tray.setToolTip("fart.run & awesome Hasselhoff")
        self.tray.activated.connect(self._on_tray_click)

        self.menu = QMenu()
        self.menu.addAction("Show Dashboard", self._show)
        self.menu.addAction("Nag Me", self.dashboard._do_nag)
        self.menu.addAction("Hasselhoff!", self.dashboard._do_hoff)
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
