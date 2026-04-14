"""Fart Run & Awesome Hasselhoff — GUI Dashboard."""

import sys
from pathlib import Path

# Ensure project root is in sys.path for direct script execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QLabel, QSystemTrayIcon, QMenu, QAction,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QIcon, QPixmap, QColor, QPainter, QFont

from gui.docker_tab import DockerTab
from gui.ports_tab import PortsTab
from gui.security_tab import SecurityTab
from gui.monitor_alerts import MonitorAlertManager
from core.plugin import Alert
from core.config import load_config


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


class MonitorDashboard(QMainWindow):
    """Main monitoring dashboard window — Win95 style."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("fart.run & awesome Hasselhoff — Dev Monitor")
        self.setMinimumSize(850, 600)
        self.setStyleSheet(WIN95_STYLE)

        self._config = load_config()
        self._alerts = MonitorAlertManager(
            cooldown=self._config["alerts"]["cooldown_seconds"]
        )

        # Tabs
        self.tabs = QTabWidget()
        self.docker_tab = DockerTab()
        self.ports_tab = PortsTab()
        self.security_tab = SecurityTab()

        self.tabs.addTab(self.docker_tab, "🐳 Docker")
        self.tabs.addTab(self.ports_tab, "🔌 Ports")
        self.tabs.addTab(self.security_tab, "🛡 Security")

        self.setCentralWidget(self.tabs)

        # Status bar
        self.statusBar().showMessage("fart.run & awesome Hasselhoff — ready 💨")

        # Security scan button
        self.security_tab.scan_requested.connect(self._run_security_scan)

        # Docker client
        self._docker_client = None
        try:
            import docker
            self._docker_client = docker.from_env()
        except Exception:
            pass

        # Timers
        self._docker_timer = QTimer(self)
        self._docker_timer.timeout.connect(self._refresh_docker)
        self._docker_timer.start(5000)  # 5 sec

        self._ports_timer = QTimer(self)
        self._ports_timer.timeout.connect(self._refresh_ports)
        self._ports_timer.start(5000)

        self._security_timer = QTimer(self)
        self._security_timer.timeout.connect(self._run_security_scan)
        self._security_timer.start(3600000)  # 1 hour

        # Initial refresh
        self._refresh_docker()
        self._refresh_ports()
        self._run_security_scan()

    def _refresh_docker(self) -> None:
        if not self._docker_client:
            return
        try:
            from plugins.docker_monitor.collector import collect_containers
            containers = self._docker_client.containers.list(all=True)
            infos = collect_containers(containers)
            self.docker_tab.update_data(infos)

            # Check alerts
            cpu_thresh = self._config["plugins"]["docker_monitor"]["cpu_threshold"]
            ram_thresh = self._config["plugins"]["docker_monitor"]["ram_threshold"]
            for info in infos:
                if info["status"] == "exited":
                    self._alerts.process(Alert(
                        source="docker", severity="critical",
                        title=f"{info['name']} crashed (exit {info['exit_code']})",
                        message=f"Container {info['name']} exited with code {info['exit_code']}",
                        sound="fart3.mp3",
                    ))
                    self.docker_tab.add_event(f"{info['name']} exited (code {info['exit_code']})")
                elif info["status"] == "running":
                    if info["cpu_percent"] > cpu_thresh:
                        self._alerts.process(Alert(
                            source="docker", severity="warning",
                            title=f"{info['name']} CPU {info['cpu_percent']:.0f}%",
                            message=f"CPU at {info['cpu_percent']:.1f}%",
                            sound="fart1.mp3",
                        ))
                    if info["mem_limit"] > 0:
                        ram_pct = (info["mem_usage"] / info["mem_limit"]) * 100
                        if ram_pct > ram_thresh:
                            self._alerts.process(Alert(
                                source="docker", severity="critical",
                                title=f"{info['name']} RAM {ram_pct:.0f}%",
                                message=f"RAM at {ram_pct:.1f}%",
                                sound="fart3.mp3",
                            ))

            self.statusBar().showMessage(f"Docker: {len(infos)} containers | Last update: OK")
        except Exception as e:
            self.statusBar().showMessage(f"Docker error: {e}")

    def _refresh_ports(self) -> None:
        try:
            from plugins.port_map.collector import collect_ports
            ports = collect_ports()
            self.ports_tab.update_data(ports)

            for p in ports:
                if p.get("conflict"):
                    self._alerts.process(Alert(
                        source="ports", severity="warning",
                        title=f"Port {p['port']} conflict",
                        message=f"Port {p['port']} used by multiple processes",
                        sound="fart1.mp3",
                    ))
        except Exception as e:
            self.statusBar().showMessage(f"Ports error: {e}")

    def _run_security_scan(self) -> None:
        self.security_tab.set_scanning(True)
        try:
            from plugins.security_scan.scanners import (
                scan_docker_security, scan_env_in_git, scan_file_permissions,
                scan_exposed_ports, scan_pip_audit, scan_npm_audit,
            )
            findings = []

            # Docker security
            if self._docker_client:
                try:
                    from plugins.docker_monitor.collector import collect_containers
                    containers = self._docker_client.containers.list(all=True)
                    infos = collect_containers(containers)
                    findings.extend(scan_docker_security(infos))
                except Exception:
                    pass

            # .env in git + file permissions
            scan_paths = [Path(p).expanduser() for p in self._config["plugins"]["security_scan"].get("scan_paths", ["~"])]
            findings.extend(scan_env_in_git(scan_paths))
            findings.extend(scan_file_permissions(scan_paths))

            # Exposed ports
            try:
                from plugins.port_map.collector import collect_ports
                ports = collect_ports()
                findings.extend(scan_exposed_ports(ports))
            except Exception:
                pass

            # Convert Finding objects to dicts for the tab
            findings_dicts = [
                {"type": f.type, "severity": f.severity, "description": f.description, "source": f.source}
                for f in findings
            ]
            self.security_tab.update_data(findings_dicts)

            # Alert on critical/high
            for f in findings:
                if f.severity in ("critical", "high"):
                    self._alerts.process(Alert(
                        source="security", severity=f.severity,
                        title=f"[{f.type}] {f.description[:50]}",
                        message=f.description,
                        sound="fart3.mp3" if f.severity == "critical" else "fart1.mp3",
                    ))

            self.statusBar().showMessage(f"Security scan: {len(findings)} findings")
        except Exception as e:
            self.statusBar().showMessage(f"Security error: {e}")
        finally:
            self.security_tab.set_scanning(False)


class MonitorApp:
    """Application wrapper with system tray."""

    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        self.dashboard = MonitorDashboard()

        # System tray
        self.tray = QSystemTrayIcon(_make_tray_icon("green"), self.app)
        tray_menu = QMenu()

        show_action = QAction("Show Dashboard", self.app)
        show_action.triggered.connect(self.dashboard.show)
        tray_menu.addAction(show_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit", self.app)
        quit_action.triggered.connect(self.app.quit)
        tray_menu.addAction(quit_action)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._tray_clicked)
        self.tray.setToolTip("fart.run & awesome Hasselhoff")
        self.tray.show()

        self.dashboard.show()

    def _tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.dashboard.isVisible():
                self.dashboard.hide()
            else:
                self.dashboard.show()
                self.dashboard.raise_()
                self.dashboard.activateWindow()

    def run(self) -> int:
        return self.app.exec_()


def main():
    app = MonitorApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
