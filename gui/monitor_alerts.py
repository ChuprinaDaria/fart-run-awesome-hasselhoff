"""Monitor alert manager for GUI — thin wrapper around core AlertManager."""

from __future__ import annotations

from core.alerts import AlertManager
from core.plugin import Alert


class MonitorAlertManager:
    def __init__(self, config: dict):
        self._manager = AlertManager(config)

    def process(self, alert: Alert) -> bool:
        return self._manager.process(alert)
