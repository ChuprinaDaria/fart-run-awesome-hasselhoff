"""Docker Monitor tab — Win95 style PyQt5 widget."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QLabel,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor


def _fmt_bytes(n: int) -> str:
    if n >= 1_073_741_824:
        return f"{n / 1_073_741_824:.1f}GB"
    if n >= 1_048_576:
        return f"{n / 1_048_576:.0f}MB"
    if n >= 1024:
        return f"{n / 1024:.0f}KB"
    return f"{n}B"


class DockerTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # Container table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["", "NAME", "STATUS", "CPU%", "RAM", "PORTS", "HEALTH"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget { alternate-background-color: #e8e8e8; }
        """)
        layout.addWidget(self.table)

        # Events panel
        events_group = QGroupBox("Events")
        events_layout = QVBoxLayout()
        self.events_label = QLabel("No events yet")
        self.events_label.setWordWrap(True)
        self.events_label.setStyleSheet("padding: 4px; background: white; border: 2px inset #808080; font-family: 'Courier New', monospace; font-size: 11px;")
        self.events_label.setMinimumHeight(80)
        self.events_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        events_layout.addWidget(self.events_label)
        events_group.setLayout(events_layout)
        layout.addWidget(events_group)

        self._events: list[str] = []

    def update_data(self, containers: list[dict]) -> None:
        self.table.setRowCount(len(containers))
        for i, c in enumerate(containers):
            status = c.get("status", "unknown")

            # Status icon
            if status == "running":
                icon = "●"
                color = QColor(0, 160, 0)
            elif status == "exited":
                icon = "○"
                color = QColor(128, 128, 128)
            else:
                icon = "◉"
                color = QColor(200, 200, 0)

            cpu = c.get("cpu_percent", 0)
            if cpu > 80:
                color = QColor(255, 50, 50)

            icon_item = QTableWidgetItem(icon)
            icon_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 0, icon_item)

            name_item = QTableWidgetItem(c.get("name", "?"))
            self.table.setItem(i, 1, name_item)

            status_item = QTableWidgetItem(status)
            self.table.setItem(i, 2, status_item)

            cpu_str = f"{cpu:.1f}%" if status == "running" else "—"
            cpu_item = QTableWidgetItem(cpu_str)
            cpu_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 3, cpu_item)

            mem = _fmt_bytes(c.get("mem_usage", 0)) if status == "running" else "—"
            mem_item = QTableWidgetItem(mem)
            mem_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(i, 4, mem_item)

            ports_list = c.get("ports", [])
            ports_str = ", ".join(f"{p['host_port']}→{p['container_port']}" for p in ports_list[:3])
            self.table.setItem(i, 5, QTableWidgetItem(ports_str))

            health = c.get("health") or "—"
            self.table.setItem(i, 6, QTableWidgetItem(health))

            # Color entire row
            for col in range(7):
                item = self.table.item(i, col)
                if item:
                    item.setForeground(color)

    def add_event(self, message: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._events.append(f"{ts}  {message}")
        self._events = self._events[-10:]  # keep last 10
        self.events_label.setText("\n".join(self._events))
