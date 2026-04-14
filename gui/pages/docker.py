"""Docker page — container list with Fart Off/Start/Restart/Logs/Remove."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QLabel, QPushButton, QMenu, QAction,
    QDialog, QTextEdit, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread, pyqtSlot
from PyQt5.QtGui import QColor
import logging

log = logging.getLogger(__name__)


def _fmt_bytes(n: int) -> str:
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f}GB"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.0f}MB"
    if n >= 1024:
        return f"{n / 1024:.0f}KB"
    return f"{n}B"


class DockerActionThread(QThread):
    finished = pyqtSignal(str, bool, str)  # action, success, message

    def __init__(self, client, container_name: str, action: str):
        super().__init__()
        self._client = client
        self._container_name = container_name
        self._action = action

    def run(self):
        try:
            container = self._client.containers.get(self._container_name)
            if self._action == "stop":
                container.stop(timeout=10)
                self.finished.emit("stop", True, f"{self._container_name} stopped")
            elif self._action == "start":
                container.start()
                self.finished.emit("start", True, f"{self._container_name} started")
            elif self._action == "restart":
                container.restart(timeout=10)
                self.finished.emit("restart", True, f"{self._container_name} restarted")
            elif self._action == "remove":
                container.remove(force=True)
                self.finished.emit("remove", True, f"{self._container_name} removed")
            elif self._action == "logs":
                logs = container.logs(tail=100).decode("utf-8", errors="replace")
                self.finished.emit("logs", True, logs)
        except Exception as e:
            self.finished.emit(self._action, False, str(e))


class LogsDialog(QDialog):
    def __init__(self, container_name: str, logs_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Logs: {container_name}")
        self.setMinimumSize(600, 400)
        layout = QVBoxLayout(self)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFontFamily("Courier New")
        text.setFontPointSize(10)
        text.setPlainText(logs_text)
        text.moveCursor(text.textCursor().End)
        layout.addWidget(text)

        btn = QPushButton("Close")
        btn.clicked.connect(self.close)
        layout.addWidget(btn)


class DockerPage(QWidget):
    fart_off_triggered = pyqtSignal(str)
    container_count_changed = pyqtSignal(int)

    def __init__(self, docker_client=None):
        super().__init__()
        self._client = docker_client
        self._containers: list[dict] = []
        self._action_threads: list[DockerActionThread] = []

        layout = QVBoxLayout(self)

        self.error_banner = QLabel("")
        self.error_banner.setWordWrap(True)
        self.error_banner.setStyleSheet(
            "background: #ffffcc; color: #000; padding: 8px; "
            "border: 2px inset #808080; font-weight: bold;"
        )
        self.error_banner.hide()
        layout.addWidget(self.error_banner)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["", "NAME", "STATUS", "CPU%", "RAM", "PORTS", "HEALTH", ""]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("QTableWidget { alternate-background-color: #e8e8e8; }")
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table)

        events_group = QGroupBox("Events")
        events_layout = QVBoxLayout()
        self.events_label = QLabel("No events yet")
        self.events_label.setWordWrap(True)
        self.events_label.setStyleSheet(
            "padding: 4px; background: white; border: 2px inset #808080; "
            "font-family: 'Courier New', monospace; font-size: 11px;"
        )
        self.events_label.setMinimumHeight(80)
        self.events_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        events_layout.addWidget(self.events_label)
        events_group.setLayout(events_layout)
        layout.addWidget(events_group)

        self._events: list[str] = []

    def set_docker_error(self, error: str) -> None:
        self.error_banner.setText(f"Docker: {error}")
        self.error_banner.show()

    def set_docker_client(self, client) -> None:
        self._client = client
        self.error_banner.hide()

    def update_data(self, containers: list[dict]) -> None:
        self._containers = containers
        running = sum(1 for c in containers if c.get("status") == "running")
        self.container_count_changed.emit(running)

        self.table.setRowCount(len(containers))
        for i, c in enumerate(containers):
            status = c.get("status", "unknown")

            if status == "running":
                icon, color = "\u25cf", QColor(0, 160, 0)
            elif status == "exited":
                icon, color = "\u25cb", QColor(128, 128, 128)
            else:
                icon, color = "\u25c9", QColor(200, 200, 0)

            cpu = c.get("cpu_percent", 0)
            if cpu > 80:
                color = QColor(255, 50, 50)

            icon_item = QTableWidgetItem(icon)
            icon_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, icon_item)
            self.table.setItem(i, 1, QTableWidgetItem(c.get("name", "?")))
            self.table.setItem(i, 2, QTableWidgetItem(status))

            cpu_str = f"{cpu:.1f}%" if status == "running" else "\u2014"
            cpu_item = QTableWidgetItem(cpu_str)
            cpu_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, cpu_item)

            mem = _fmt_bytes(c.get("mem_usage", 0)) if status == "running" else "\u2014"
            mem_item = QTableWidgetItem(mem)
            mem_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, mem_item)

            ports_list = c.get("ports", [])
            ports_str = ", ".join(f"{p['host_port']}\u2192{p['container_port']}" for p in ports_list[:3])
            self.table.setItem(i, 5, QTableWidgetItem(ports_str))

            health = c.get("health") or "\u2014"
            self.table.setItem(i, 6, QTableWidgetItem(health))

            if status == "running":
                btn = QPushButton("Fart Off")
                btn.setStyleSheet(
                    "background: #c0c0c0; border: 2px outset #dfdfdf; "
                    "padding: 2px 8px; font-size: 10px; font-weight: bold;"
                )
                btn.clicked.connect(lambda _, name=c["name"]: self._fart_off(name))
                self.table.setCellWidget(i, 7, btn)
            else:
                self.table.setCellWidget(i, 7, None)

            for col in range(7):
                item = self.table.item(i, col)
                if item:
                    item.setForeground(color)

    def _fart_off(self, container_name: str) -> None:
        self.fart_off_triggered.emit(container_name)
        self._run_action(container_name, "stop")

    def _show_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0 or row >= len(self._containers):
            return

        container = self._containers[row]
        name = container["name"]
        status = container["status"]

        menu = QMenu(self)
        if status == "running":
            menu.addAction("Stop", lambda: self._run_action(name, "stop"))
            menu.addAction("Restart", lambda: self._run_action(name, "restart"))
        else:
            menu.addAction("Start", lambda: self._run_action(name, "start"))
        menu.addAction("Logs", lambda: self._run_action(name, "logs"))
        menu.addSeparator()
        menu.addAction("Remove", lambda: self._confirm_remove(name))

        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _confirm_remove(self, name: str) -> None:
        reply = QMessageBox.question(
            self, "Remove Container",
            f"Remove container '{name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._run_action(name, "remove")

    def _run_action(self, container_name: str, action: str) -> None:
        if not self._client:
            return
        thread = DockerActionThread(self._client, container_name, action)
        thread.finished.connect(lambda act, ok, msg: self._on_action_done(container_name, act, ok, msg))
        self._action_threads.append(thread)
        thread.start()
        self.add_event(f"{action} \u2192 {container_name}...")

    def _on_action_done(self, container_name: str, action: str, success: bool, message: str) -> None:
        if action == "logs" and success:
            dialog = LogsDialog(container_name, message, self)
            dialog.show()
        elif success:
            self.add_event(f"{action} \u2192 {container_name}: OK")
        else:
            self.add_event(f"{action} \u2192 {container_name}: FAIL \u2014 {message}")
        self._action_threads = [t for t in self._action_threads if t.isRunning()]

    def add_event(self, message: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._events.append(f"{ts}  {message}")
        self._events = self._events[-10:]
        self.events_label.setText("\n".join(self._events))
