"""Settings page — language, sound, notifications."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QComboBox, QCheckBox, QLabel, QPushButton, QSpinBox, QLineEdit,
)
from PyQt5.QtCore import pyqtSignal
from i18n import get_string as _t


class SettingsPage(QWidget):
    settings_changed = pyqtSignal(dict)  # emits changed config keys

    def __init__(self, config: dict):
        super().__init__()
        self._config = config
        layout = QVBoxLayout(self)

        # --- HaikuHoff ---
        haiku_group = QGroupBox("HaikuHoff")
        hg = QFormLayout()

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("sk-ant-...")
        current_key = config.get("haiku", {}).get("api_key", "")
        self.api_key_input.setText(current_key)
        hg.addRow("HaikuHoff Key:", self.api_key_input)

        haiku_hint = QLabel(_t("haiku_hint"))
        haiku_hint.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        haiku_hint.setWordWrap(True)
        hg.addRow(haiku_hint)

        test_row = QHBoxLayout()
        self.btn_test_haiku = QPushButton(_t("haiku_test"))
        self.btn_test_haiku.setFixedWidth(80)
        self.btn_test_haiku.clicked.connect(self._test_haiku)
        test_row.addWidget(self.btn_test_haiku)
        self.haiku_status = QLabel("")
        self.haiku_status.setStyleSheet("font-style: italic; padding-left: 8px;")
        test_row.addWidget(self.haiku_status)
        test_row.addStretch()
        hg.addRow(test_row)

        haiku_group.setLayout(hg)
        layout.addWidget(haiku_group)

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

        self.sound_mode = QComboBox()
        self.sound_mode.addItems(["classic", "fart"])
        current_mode = config.get("sounds", {}).get("mode", "classic")
        self.sound_mode.setCurrentText(current_mode)
        sg.addRow(_t("sound_mode") + ":", self.sound_mode)

        self.notif_enabled = QCheckBox(_t("enable_notif"))
        self.notif_enabled.setChecked(config.get("alerts", {}).get("desktop_notifications", True))
        sg.addRow(self.notif_enabled)

        sound_group.setLayout(sg)
        layout.addWidget(sound_group)

        # --- Alerts ---
        alerts_group = QGroupBox(_t("alerts_group"))
        ag = QFormLayout()

        filters = config.get("alert_filters", {})

        self.alert_docker = QCheckBox(_t("alert_docker"))
        self.alert_docker.setChecked(filters.get("docker", True))
        ag.addRow(self.alert_docker)

        self.alert_security = QCheckBox(_t("alert_security"))
        self.alert_security.setChecked(filters.get("security", True))
        ag.addRow(self.alert_security)

        self.alert_ports = QCheckBox(_t("alert_ports"))
        self.alert_ports.setChecked(filters.get("ports", True))
        ag.addRow(self.alert_ports)

        self.alert_usage = QCheckBox(_t("alert_usage"))
        self.alert_usage.setChecked(filters.get("usage", True))
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

    def _test_haiku(self):
        key = self.api_key_input.text().strip()
        if not key:
            self.haiku_status.setText(_t("haiku_no_key"))
            self.haiku_status.setStyleSheet("color: #cc0000; font-style: italic; padding-left: 8px;")
            return
        self.haiku_status.setText(_t("haiku_testing"))
        self.haiku_status.setStyleSheet("color: #808080; font-style: italic; padding-left: 8px;")
        from core.haiku_client import HaikuClient
        client = HaikuClient(api_key=key)
        client._min_interval = 0
        result = client.ask("Say OK", max_tokens=5)
        if result:
            self.haiku_status.setText(_t("haiku_connected"))
            self.haiku_status.setStyleSheet("color: #006600; font-style: italic; padding-left: 8px;")
        else:
            self.haiku_status.setText(_t("haiku_failed"))
            self.haiku_status.setStyleSheet("color: #cc0000; font-style: italic; padding-left: 8px;")

    def _apply(self):
        """Save settings to config.toml — cross-platform."""
        from core.platform import get_platform

        self._config.setdefault("haiku", {})
        self._config["haiku"]["api_key"] = self.api_key_input.text().strip()

        self._config["general"]["language"] = self.lang_combo.currentText()
        self._config["sounds"]["enabled"] = self.sound_enabled.isChecked()
        self._config["sounds"]["mode"] = self.sound_mode.currentText()
        self._config["alerts"]["desktop_notifications"] = self.notif_enabled.isChecked()
        self._config["alerts"]["cooldown_seconds"] = self.cooldown_spin.value()

        # Custom alert filters
        self._config.setdefault("alert_filters", {})
        self._config["alert_filters"]["docker"] = self.alert_docker.isChecked()
        self._config["alert_filters"]["security"] = self.alert_security.isChecked()
        self._config["alert_filters"]["ports"] = self.alert_ports.isChecked()
        self._config["alert_filters"]["usage"] = self.alert_usage.isChecked()

        # Write config — same location where it was loaded from
        from pathlib import Path
        from core.config import _project_root
        config_path = _project_root() / "config.toml"

        try:
            try:
                import tomli_w
                with open(config_path, "wb") as f:
                    tomli_w.dump(self._config, f)
            except ImportError:
                import toml
                with open(config_path, "w") as f:
                    toml.dump(self._config, f)
            self.status_label.setText(_t("saved_ok"))
            self.status_label.setStyleSheet("color: #006600; font-style: italic; padding: 4px;")
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
