"""Fart Run & Awesome Hasselhoff — GUI Dashboard.

Extends the original NaggerDashboard with Docker/Ports/Security monitoring tabs.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path for direct script execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from PyQt5.QtWidgets import QAction, QMenu
from PyQt5.QtCore import QTimer

from claude_nagger.gui.app import (
    NaggerDashboard, NaggerTrayApp, _make_tray_icon, WIN95_STYLE,
)
from claude_nagger.i18n import get_string, set_language

from gui.docker_tab import DockerTab
from gui.ports_tab import PortsTab
from gui.security_tab import SecurityTab
from gui.monitor_alerts import MonitorAlertManager
from core.plugin import Alert
from core.config import load_config


class MonitorDashboard(NaggerDashboard):
    """NaggerDashboard + Docker/Ports/Security monitoring tabs."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("fart.run & awesome Hasselhoff — Dev Monitor")
        self.setMinimumSize(900, 650)

        self._monitor_config = load_config()
        self._monitor_alerts = MonitorAlertManager(
            cooldown=self._monitor_config["alerts"]["cooldown_seconds"]
        )

        # Add monitoring tabs to existing tab widget
        self.docker_tab = DockerTab()
        self.ports_tab = PortsTab()
        self.security_tab = SecurityTab()

        self.tabs.addTab(self.docker_tab, "🐳 Docker")
        self.tabs.addTab(self.ports_tab, "🔌 Ports")
        self.tabs.addTab(self.security_tab, "🛡 Security")

        # Security scan button
        self.security_tab.scan_requested.connect(self._run_security_scan)

        # Docker client
        self._docker_client = None
        try:
            import docker
            self._docker_client = docker.from_env()
        except Exception:
            pass

        # Monitoring timers
        self._docker_timer = QTimer(self)
        self._docker_timer.timeout.connect(self._refresh_docker)
        self._docker_timer.start(5000)

        self._ports_timer = QTimer(self)
        self._ports_timer.timeout.connect(self._refresh_ports)
        self._ports_timer.start(5000)

        self._security_timer = QTimer(self)
        self._security_timer.timeout.connect(self._run_security_scan)
        self._security_timer.start(3600000)

        # Initial monitoring refresh
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

            cpu_thresh = self._monitor_config["plugins"]["docker_monitor"]["cpu_threshold"]
            ram_thresh = self._monitor_config["plugins"]["docker_monitor"]["ram_threshold"]
            for info in infos:
                if info["status"] == "exited":
                    self._monitor_alerts.process(Alert(
                        source="docker", severity="critical",
                        title=f"{info['name']} crashed (exit {info['exit_code']})",
                        message=f"Container {info['name']} exited with code {info['exit_code']}",
                        sound="fart3.mp3",
                    ))
                    self.docker_tab.add_event(f"{info['name']} exited (code {info['exit_code']})")
                elif info["status"] == "running":
                    if info["cpu_percent"] > cpu_thresh:
                        self._monitor_alerts.process(Alert(
                            source="docker", severity="warning",
                            title=f"{info['name']} CPU {info['cpu_percent']:.0f}%",
                            message=f"CPU at {info['cpu_percent']:.1f}%",
                            sound="fart1.mp3",
                        ))
                    if info["mem_limit"] > 0:
                        ram_pct = (info["mem_usage"] / info["mem_limit"]) * 100
                        if ram_pct > ram_thresh:
                            self._monitor_alerts.process(Alert(
                                source="docker", severity="critical",
                                title=f"{info['name']} RAM {ram_pct:.0f}%",
                                message=f"RAM at {ram_pct:.1f}%",
                                sound="fart3.mp3",
                            ))

            self.statusBar().showMessage(f"Docker: {len(infos)} containers | 💨 ready")
        except Exception as e:
            self.statusBar().showMessage(f"Docker error: {e}")

    def _refresh_ports(self) -> None:
        try:
            from plugins.port_map.collector import collect_ports
            ports = collect_ports()
            self.ports_tab.update_data(ports)

            for p in ports:
                if p.get("conflict"):
                    self._monitor_alerts.process(Alert(
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
                scan_exposed_ports,
            )
            findings = []

            if self._docker_client:
                try:
                    from plugins.docker_monitor.collector import collect_containers
                    containers = self._docker_client.containers.list(all=True)
                    infos = collect_containers(containers)
                    findings.extend(scan_docker_security(infos))
                except Exception:
                    pass

            scan_paths = [Path(p).expanduser() for p in
                          self._monitor_config["plugins"]["security_scan"].get("scan_paths", ["~"])]
            findings.extend(scan_env_in_git(scan_paths))
            findings.extend(scan_file_permissions(scan_paths))

            try:
                from plugins.port_map.collector import collect_ports
                ports = collect_ports()
                findings.extend(scan_exposed_ports(ports))
            except Exception:
                pass

            findings_dicts = [
                {"type": f.type, "severity": f.severity, "description": f.description, "source": f.source}
                for f in findings
            ]
            self.security_tab.update_data(findings_dicts)

            for f in findings:
                if f.severity in ("critical", "high"):
                    self._monitor_alerts.process(Alert(
                        source="security", severity=f.severity,
                        title=f"[{f.type}] {f.description[:50]}",
                        message=f.description,
                        sound="fart3.mp3" if f.severity == "critical" else "fart1.mp3",
                    ))

            self.statusBar().showMessage(f"Security: {len(findings)} findings | 💨")
        except Exception as e:
            self.statusBar().showMessage(f"Security error: {e}")
        finally:
            self.security_tab.set_scanning(False)


class MonitorTrayApp(NaggerTrayApp):
    """Extended tray app that uses MonitorDashboard instead of NaggerDashboard."""

    def __init__(self):
        # Don't call super().__init__() — we replace the dashboard
        import argparse
        from PyQt5.QtWidgets import QApplication, QSystemTrayIcon
        from claude_nagger.core.sounds import SoundPlayer
        from claude_nagger.core.parser import TokenParser
        from claude_nagger.core.calculator import CostCalculator
        from claude_nagger.nagger.messages import get_nag_message, get_nag_level
        from claude_nagger.nagger.hasselhoff import get_hoff_phrase, get_hoff_image, get_victory_sound
        from claude_nagger.gui.popup import NaggerPopup

        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.dashboard = MonitorDashboard()  # Our extended dashboard
        self.sounds = SoundPlayer()
        self.tray = QSystemTrayIcon(_make_tray_icon("green"), self.app)
        self.tray.setToolTip("fart.run & awesome Hasselhoff")
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

        self.dashboard.tab_overview.lang_combo.currentTextChanged.connect(self._retranslate_menu)
        self.tray.show()
        self.dashboard.show()

        # Tray update every 5 min
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_tray)
        self.timer.start(300_000)
        self._update_tray()

        # Auto-nag timer
        import random
        self._nag_timer = QTimer()
        self._nag_timer.timeout.connect(self._auto_nag)
        self._nag_timer.start(random.randint(20, 40) * 60_000)

        # Watcher
        self._watch_timer = QTimer()
        self._watch_timer.timeout.connect(self._watch_events)
        self._watch_timer.start(30_000)
        self._last_session_count = 0
        self._last_billable = 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="fart.run & awesome Hasselhoff — Dev Monitor")
    parser.add_argument("--lang", "-l", default="en", choices=["en", "ua"])
    args = parser.parse_args()
    set_language(args.lang)
    app = MonitorTrayApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
