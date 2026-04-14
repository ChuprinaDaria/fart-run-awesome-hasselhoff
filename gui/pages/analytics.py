"""Analytics page — model comparison and project breakdown."""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtCore import Qt


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class AnalyticsPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.cache_label = QLabel("Cache Efficiency: 0%")
        self.cache_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.cache_label)

        self.cache_bar = QProgressBar()
        self.cache_bar.setMaximum(100)
        layout.addWidget(self.cache_bar)

        self.savings_label = QLabel("Cache saved: $0.00")
        layout.addWidget(self.savings_label)

        self.model_table = QTableWidget()
        self.model_table.setColumnCount(3)
        self.model_table.setHorizontalHeaderLabels(["Model", "Tokens", "Cost"])
        self.model_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.model_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.model_table)

        self.project_table = QTableWidget()
        self.project_table.setColumnCount(3)
        self.project_table.setHorizontalHeaderLabels(["Project", "Billable", "Sessions"])
        self.project_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.project_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.project_table)

        layout.addStretch()

    def update_data(self, stats, cache_eff: float, savings: float,
                    comparison: dict, projects: list) -> None:
        self.cache_label.setText(f"Cache Efficiency: {cache_eff:.1f}%")
        self.cache_bar.setValue(int(cache_eff))
        self.savings_label.setText(f"Cache saved: ~${savings:.2f}")

        self.model_table.setRowCount(len(stats.model_totals))
        for i, (model, mu) in enumerate(stats.model_totals.items()):
            name = model.replace("claude-", "").upper()
            self.model_table.setItem(i, 0, QTableWidgetItem(name))
            self.model_table.setItem(i, 1, QTableWidgetItem(_fmt(mu.billable_tokens)))
            self.model_table.setItem(i, 2, QTableWidgetItem(f"${comparison.get('actual', 0):.2f}"))

        self.project_table.setRowCount(min(len(projects), 10))
        for i, p in enumerate(projects[:10]):
            self.project_table.setItem(i, 0, QTableWidgetItem(p.project))
            self.project_table.setItem(i, 1, QTableWidgetItem(_fmt(p.total_billable)))
            self.project_table.setItem(i, 2, QTableWidgetItem(str(p.sessions)))

    def set_no_claude(self) -> None:
        self.cache_label.setText("Claude not found — no analytics")
