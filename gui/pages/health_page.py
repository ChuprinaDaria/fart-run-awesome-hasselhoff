"""Dev Health page — project health scanner with human-language results."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFileDialog, QFrame,
)
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtGui import QFont

from i18n import get_string as _t
from core.health.models import HealthReport, HealthFinding


class HealthScanThread(QThread):
    """Run health scan in background thread."""
    scan_done = pyqtSignal(object)

    def __init__(self, project_dir: str, parent=None):
        super().__init__(parent)
        self._dir = project_dir

    def run(self):
        from core.health.project_map import run_all_checks
        report = run_all_checks(self._dir)
        self.scan_done.emit(report)


class HealthPage(QWidget):
    """Dev Health — scan project and show health check results."""

    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._scan_thread: HealthScanThread | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header
        header = QHBoxLayout()
        title = QLabel(_t("health_header"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        header.addWidget(title)
        header.addStretch()

        self._dir_label = QLabel(_t("health_no_dir"))
        self._dir_label.setStyleSheet("color: #808080;")
        header.addWidget(self._dir_label)

        self._btn_select = QPushButton(_t("health_btn_select"))
        self._btn_select.clicked.connect(self._on_select_dir)
        header.addWidget(self._btn_select)

        self._btn_scan = QPushButton(_t("health_btn_scan"))
        self._btn_scan.clicked.connect(self._on_scan)
        self._btn_scan.setEnabled(False)
        self._btn_scan.setStyleSheet(
            "QPushButton { background: #000080; color: white; padding: 6px 16px; "
            "border: 2px outset #4040c0; font-weight: bold; font-size: 13px; }"
            "QPushButton:pressed { border: 2px inset #000080; }"
            "QPushButton:disabled { background: #808080; color: #c0c0c0; }"
        )
        header.addWidget(self._btn_scan)

        layout.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px inset #808080; background: white; }")

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._content_widget)

        layout.addWidget(scroll)

        self._show_placeholder(_t("health_select_dir"))

    def _show_placeholder(self, text: str) -> None:
        self._clear_content()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #808080; font-size: 14px; padding: 40px;")
        self._content_layout.addWidget(lbl)

    def _clear_content(self) -> None:
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _on_select_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, _t("health_btn_select"), str(Path.home()),
        )
        if dir_path:
            self._project_dir = dir_path
            display = dir_path if len(dir_path) <= 50 else "..." + dir_path[-47:]
            self._dir_label.setText(display)
            self._dir_label.setStyleSheet("color: #000000;")
            self._btn_scan.setEnabled(True)
            self._show_placeholder(_t("health_no_results"))

    def _on_scan(self) -> None:
        if not self._project_dir:
            return
        self._btn_scan.setEnabled(False)
        self._btn_scan.setText(_t("health_scanning"))
        self._show_placeholder(_t("health_scanning"))

        self._scan_thread = HealthScanThread(self._project_dir, self)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_done(self, report: HealthReport) -> None:
        self._btn_scan.setEnabled(True)
        self._btn_scan.setText(_t("health_btn_scan"))
        self._render_report(report)

    def _render_report(self, report: HealthReport) -> None:
        self._clear_content()

        if not report.findings:
            self._show_placeholder(_t("health_empty_project"))
            return

        # Group findings by check_id
        sections: dict[str, tuple[str, list[HealthFinding]]] = {
            "map.file_tree": (_t("health_section_tree"), []),
            "map.entry_points": (_t("health_section_entry"), []),
            "map.modules": (_t("health_section_modules"), []),
            "map.monsters": (_t("health_section_monsters"), []),
            "map.configs": (_t("health_section_configs"), []),
            "dead.unused_imports": (_t("health_section_unused_imports"), []),
            "dead.unused_definitions": (_t("health_section_unused_defs"), []),
            "dead.orphan_files": (_t("health_section_orphans"), []),
            "dead.commented_code": (_t("health_section_commented"), []),
            "debt.no_types": (_t("health_section_missing_types"), []),
            "debt.error_handling": (_t("health_section_error_gaps"), []),
            "debt.hardcoded": (_t("health_section_hardcoded"), []),
            "debt.todos": (_t("health_section_todos"), []),
            "debt.outdated_deps": (_t("health_section_outdated_deps"), []),
            "brake.unfinished": (_t("health_section_unfinished"), []),
            "brake.tests": (_t("health_section_tests"), []),
            "brake.scope_creep": (_t("health_section_scope"), []),
            "brake.overengineering": (_t("health_section_overeng"), []),
            "git.status": (_t("health_section_git_status"), []),
            "git.commits": (_t("health_section_git_commits"), []),
            "git.branches": (_t("health_section_git_branches"), []),
            "git.gitignore": (_t("health_section_git_ignore"), []),
            "git.cheatsheet": (_t("health_section_git_cheat"), []),
            "docs.readme": (_t("health_section_readme"), []),
            "docs.deps": (_t("health_section_deps"), []),
            "docs.devtools": (_t("health_section_devtools"), []),
            "docs.llm_context": (_t("health_section_llm_context"), []),
            "system": ("System", []),
        }

        for finding in report.findings:
            key = finding.check_id
            if key in sections:
                sections[key][1].append(finding)

        # File tree summary
        if report.file_tree:
            tree = report.file_tree
            group = self._make_group(
                f"{_t('health_section_tree')} \u2014 "
                f"{tree['total_files']} {_t('health_files_label')} | "
                f"{tree['total_dirs']} {_t('health_dirs_label')} | "
                f"{self._format_size(tree['total_size_bytes'])} | "
                f"{_t('health_depth_label')} {tree['max_depth']}"
            )
            gl = group.layout()
            ext_sorted = sorted(
                tree["files_by_ext"].items(), key=lambda x: x[1], reverse=True
            )
            ext_str = "  ".join(f".{ext}: {count}" for ext, count in ext_sorted[:8])
            ext_lbl = QLabel(ext_str)
            ext_lbl.setStyleSheet("font-family: monospace; color: #333; padding: 4px;")
            gl.addWidget(ext_lbl)
            tree_findings = sections.get("map.file_tree", ("", []))[1]
            if tree_findings:
                tip = QLabel(f"  {tree_findings[0].message}")
                tip.setStyleSheet("color: #666; font-size: 11px;")
                tip.setWordWrap(True)
                gl.addWidget(tip)
            self._content_layout.addWidget(group)

        # Entry points
        if report.entry_points:
            ep_findings = sections.get("map.entry_points", ("", []))[1]
            group = self._make_group(
                f"{_t('health_section_entry')} ({len(report.entry_points)})"
            )
            gl = group.layout()
            for ep in report.entry_points:
                row = QLabel(f"  \u25cf {ep['path']} \u2014 {ep['description']}")
                row.setStyleSheet("color: #333; padding: 2px;")
                gl.addWidget(row)
            if ep_findings:
                tip = QLabel(f"  {ep_findings[0].message}")
                tip.setStyleSheet("color: #666; font-size: 11px;")
                tip.setWordWrap(True)
                gl.addWidget(tip)
            self._content_layout.addWidget(group)

        # Module hubs / circular / orphans
        module_findings = sections.get("map.modules", ("", []))[1]
        if module_findings:
            group = self._make_group(_t("health_section_modules"))
            gl = group.layout()
            for f in module_findings:
                row = self._make_finding_row(f)
                gl.addWidget(row)
            self._content_layout.addWidget(group)

        # Monsters
        if report.monsters:
            group = self._make_group(_t("health_section_monsters"))
            gl = group.layout()
            for m in report.monsters:
                sev_icon = self._severity_icon(m["severity"])
                row = QLabel(
                    f"  {sev_icon} {m['path']} \u2014 {m['lines']} lines, "
                    f"{m['functions']} functions, {m['classes']} classes"
                )
                color = self._severity_color(m["severity"])
                row.setStyleSheet(f"color: {color}; font-weight: bold; padding: 2px;")
                gl.addWidget(row)
            monster_findings = sections.get("map.monsters", ("", []))[1]
            for f in monster_findings[:3]:
                tip = QLabel(f"  {f.message}")
                tip.setStyleSheet("color: #666; font-size: 11px;")
                tip.setWordWrap(True)
                gl.addWidget(tip)
            self._content_layout.addWidget(group)

        # Configs
        if report.configs:
            group = self._make_group(
                f"{_t('health_section_configs')} ({len(report.configs)})"
            )
            gl = group.layout()
            for c in report.configs:
                icon = "\u26a0\ufe0f" if c["severity"] == "warning" else "\u2139\ufe0f"
                row = QLabel(f"  {icon} {c['path']} \u2014 {c['description']}")
                row.setStyleSheet("color: #333; padding: 2px;")
                gl.addWidget(row)
            config_findings = sections.get("map.configs", ("", []))[1]
            for f in config_findings:
                tip = QLabel(f"  {f.message}")
                tip.setStyleSheet("color: #666; font-size: 11px;")
                tip.setWordWrap(True)
                gl.addWidget(tip)
            self._content_layout.addWidget(group)

        # Dead Code sections
        for dead_key in [
            "dead.unused_imports", "dead.unused_definitions", "dead.orphan_files", "dead.commented_code",
            "debt.no_types", "debt.error_handling", "debt.hardcoded", "debt.todos", "debt.outdated_deps",
            "brake.unfinished", "brake.tests", "brake.scope_creep", "brake.overengineering",
            "git.status", "git.commits", "git.branches", "git.gitignore", "git.cheatsheet",
            "docs.readme", "docs.deps", "docs.devtools", "docs.llm_context",
        ]:
            dead_findings = sections.get(dead_key, ("", []))[1]
            if dead_findings:
                section_title = sections[dead_key][0]
                group = self._make_group(f"{section_title} ({len(dead_findings)})")
                gl = group.layout()
                for f in dead_findings[:15]:
                    row = self._make_finding_row(f)
                    gl.addWidget(row)
                if len(dead_findings) > 15:
                    more = QLabel(f"  ... and {len(dead_findings) - 15} more")
                    more.setStyleSheet("color: #808080; font-style: italic;")
                    gl.addWidget(more)
                self._content_layout.addWidget(group)

        # System warnings
        sys_findings = sections.get("system", ("", []))[1]
        for f in sys_findings:
            row = self._make_finding_row(f)
            self._content_layout.addWidget(row)

        # Summary bar
        self._add_summary_bar(report)

        self._content_layout.addStretch()

    def _add_summary_bar(self, report: HealthReport) -> None:
        counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in report.findings:
            if f.severity in counts:
                counts[f.severity] += 1

        parts = []
        icons = {
            "critical": "\U0001f480",
            "high": "\U0001f534",
            "medium": "\U0001f7e1",
            "low": "\U0001f535",
            "info": "\u2139\ufe0f",
        }
        for sev in ["critical", "high", "medium", "low", "info"]:
            if counts[sev] > 0:
                parts.append(f"{icons[sev]} {counts[sev]} {_t(f'health_severity_{sev}')}")

        if parts:
            summary = QLabel("  " + " | ".join(parts))
            summary.setStyleSheet(
                "background: #e0e0e0; border: 2px groove #808080; "
                "padding: 6px; font-weight: bold; margin-top: 8px;"
            )
            self._content_layout.addWidget(summary)

    def _make_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(
            "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
            "padding-top: 16px; font-weight: bold; background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        layout = QVBoxLayout(group)
        layout.setSpacing(2)
        return group

    def _make_finding_row(self, finding: HealthFinding) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(1)

        color = self._severity_color(finding.severity)
        icon = self._severity_icon(finding.severity)

        title_lbl = QLabel(f"{icon} {finding.title}")
        title_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(title_lbl)

        msg_lbl = QLabel(f"  {finding.message}")
        msg_lbl.setStyleSheet("color: #666; font-size: 11px;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl)

        return frame

    @staticmethod
    def _severity_color(severity: str) -> str:
        return {
            "critical": "#8b0000",
            "high": "#cc0000",
            "medium": "#cc6600",
            "low": "#000080",
            "info": "#333333",
            "warning": "#cc6600",
        }.get(severity, "#808080")

    @staticmethod
    def _severity_icon(severity: str) -> str:
        return {
            "critical": "\U0001f480",
            "high": "\U0001f534",
            "medium": "\U0001f7e1",
            "low": "\U0001f535",
            "info": "\u2139\ufe0f",
            "warning": "\u26a0\ufe0f",
        }.get(severity, "")

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
