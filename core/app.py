"""Main Textual application with plugin registry."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static

from core.config import load_config
from core.sqlite_db import Database
from core.alerts import AlertManager
from core.plugin import Plugin


class DevMonitorApp(App):
    """Dev environment monitoring dashboard."""

    CSS = """
    Screen {
        background: $surface;
    }
    TabbedContent {
        height: 1fr;
    }
    .status-bar {
        dock: bottom;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
    ]

    def __init__(self, config_path: Path | str | None = None, db_path: Path | str = "monitor.db"):
        super().__init__()
        if config_path:
            self._config = load_config(Path(config_path))
        else:
            self._config = load_config()
        self._db = Database(db_path)
        self._alert_manager = AlertManager(self._config)
        self.plugins: dict[str, Plugin] = {}
        self._refresh_interval = self._config["general"]["refresh_interval"]

    def register_plugin(self, plugin: Plugin) -> None:
        self.plugins[plugin.name] = plugin

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            for plugin in self.plugins.values():
                with TabPane(f"{plugin.icon} {plugin.name}", id=f"tab-{plugin.name}"):
                    yield plugin.render()
        yield Static("dev-monitor | q: quit | r: refresh", classes="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        await self._db.connect()
        for plugin in self.plugins.values():
            await self._db.run_migration(plugin.migrate)
        self.set_interval(self._refresh_interval, self._collect_all)

    async def _collect_all(self) -> None:
        for plugin in self.plugins.values():
            try:
                async with self._db.connection() as conn:
                    await plugin.collect(conn)
                    alerts = await plugin.get_alerts(conn)
                    for alert in alerts:
                        self._alert_manager.process(alert)
            except Exception as e:
                self.notify(f"Plugin {plugin.name} error: {e}", severity="error")

    async def action_refresh(self) -> None:
        await self._collect_all()
        self.notify("Refreshed", severity="information")

    async def on_unmount(self) -> None:
        await self._db.close()


def main():
    """Entry point. Discovers and registers enabled plugins, then runs."""
    from plugins.docker_monitor.plugin import DockerMonitorPlugin
    from plugins.port_map.plugin import PortMapPlugin
    from plugins.security_scan.plugin import SecurityScanPlugin

    app = DevMonitorApp()
    config = app._config

    plugin_map = {
        "docker_monitor": DockerMonitorPlugin,
        "port_map": PortMapPlugin,
        "security_scan": SecurityScanPlugin,
    }

    for name, cls in plugin_map.items():
        plugin_cfg = config["plugins"].get(name, {})
        if plugin_cfg.get("enabled", True):
            app.register_plugin(cls(config))

    app.run()


if __name__ == "__main__":
    main()
