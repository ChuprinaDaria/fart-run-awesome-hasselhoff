"""Settings page — language, sound, notifications."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QCheckBox, QLabel, QPushButton, QSpinBox,
)
from PyQt5.QtCore import pyqtSignal
from i18n import get_string as _t


class SettingsPage(QWidget):
    settings_changed = pyqtSignal(dict)  # emits changed config keys

    def __init__(self, config: dict):
        super().__init__()
        self._config = config
        layout = QVBoxLayout(self)

        # --- Language ---
        lang_group = QGroupBox(_t("lang_group"))
        lg = QFormLayout()
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["en", "ua"])
        current_lang = config.get("general", {}).get("language", "en")
        self.lang_combo.setCurrentText(current_lang)
        lg.addRow(_t("language") + ":", self.lang_combo)
        lang_group.setLayout(lg)
        layout.addWidget(lang_group)

        # --- Sound ---
        sound_group = QGroupBox(_t("sound_group"))
        sg = QFormLayout()

        self.sound_enabled = QCheckBox(_t("enable_fart"))
        self.sound_enabled.setChecked(config.get("sounds", {}).get("enabled", True))
        sg.addRow(self.sound_enabled)

        self.notif_enabled = QCheckBox(_t("enable_notif"))
        self.notif_enabled.setChecked(config.get("alerts", {}).get("desktop_notifications", True))
        sg.addRow(self.notif_enabled)

        sound_group.setLayout(sg)
        layout.addWidget(sound_group)

        # --- Alerts ---
        alerts_group = QGroupBox(_t("alerts_group"))
        ag = QFormLayout()

        self.alert_docker = QCheckBox(_t("alert_docker"))
        self.alert_docker.setChecked(True)
        ag.addRow(self.alert_docker)

        self.alert_security = QCheckBox(_t("alert_security"))
        self.alert_security.setChecked(True)
        ag.addRow(self.alert_security)

        self.alert_ports = QCheckBox(_t("alert_ports"))
        self.alert_ports.setChecked(True)
        ag.addRow(self.alert_ports)

        self.alert_usage = QCheckBox(_t("alert_usage"))
        self.alert_usage.setChecked(True)
        ag.addRow(self.alert_usage)

        self.cooldown_spin = QSpinBox()
        self.cooldown_spin.setRange(60, 3600)
        self.cooldown_spin.setSuffix(" sec")
        self.cooldown_spin.setValue(config.get("alerts", {}).get("cooldown_seconds", 300))
        ag.addRow(_t("alert_cooldown"), self.cooldown_spin)

        alerts_group.setLayout(ag)
        layout.addWidget(alerts_group)

        # --- Apply ---
        self.btn_apply = QPushButton(_t("apply_save"))
        self.btn_apply.setStyleSheet(
            "font-size: 14px; padding: 8px 24px; background: #000080; "
            "color: white; border: 2px outset #4040c0;"
        )
        self.btn_apply.clicked.connect(self._apply)
        layout.addWidget(self.btn_apply)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #006600; font-style: italic; padding: 4px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

    def _apply(self):
        """Save settings to config.toml."""
        import toml
        from pathlib import Path

        self._config["general"]["language"] = self.lang_combo.currentText()
        self._config["sounds"]["enabled"] = self.sound_enabled.isChecked()
        self._config["alerts"]["desktop_notifications"] = self.notif_enabled.isChecked()
        self._config["alerts"]["cooldown_seconds"] = self.cooldown_spin.value()

        # Custom alert filters
        self._config.setdefault("alert_filters", {})
        self._config["alert_filters"]["docker"] = self.alert_docker.isChecked()
        self._config["alert_filters"]["security"] = self.alert_security.isChecked()
        self._config["alert_filters"]["ports"] = self.alert_ports.isChecked()
        self._config["alert_filters"]["usage"] = self.alert_usage.isChecked()

        # Write config
        config_path = Path(__file__).resolve().parent.parent.parent / "config.toml"
        try:
            with open(config_path, "w") as f:
                toml.dump(self._config, f)
            self.status_label.setText(_t("saved_ok"))
            self.settings_changed.emit(self._config)
        except Exception as e:
            self.status_label.setText(_t("save_error").format(e))
            self.status_label.setStyleSheet("color: #cc0000; font-style: italic; padding: 4px;")

    def get_alert_filters(self) -> dict:
        return {
            "docker": self.alert_docker.isChecked(),
            "security": self.alert_security.isChecked(),
            "ports": self.alert_ports.isChecked(),
            "usage": self.alert_usage.isChecked(),
        }
