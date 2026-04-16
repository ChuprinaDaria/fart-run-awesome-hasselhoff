"""Safety Net page — Save / Rollback / Pick for vibe coders."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QLineEdit, QFrame, QMessageBox,
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
)
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtGui import QFont

from i18n import get_string as _t, get_language
from core.history import HistoryDB
from core.safety_net import (
    SafetyNet, SavePointResult, RollbackResult,
    PickableFile, PickResult,
)
from core.git_educator import GitEducator, Hint
from gui.copyable_widgets import make_copy_all_button

log = logging.getLogger(__name__)


class HaikuHintThread(QThread):
    """Ask Haiku for contextual hint in background."""
    result_ready = pyqtSignal(str)

    def __init__(self, action: str, context: dict, config: dict, parent=None):
        super().__init__(parent)
        self._action = action
        self._context = context
        self._config = config

    def run(self):
        try:
            from core.haiku_client import HaikuClient
            client = HaikuClient(config=self._config)
            if not client.is_available():
                self.result_ready.emit("")
                return
            lang = self._config.get("general", {}).get("language", "en")
            educator = GitEducator("", None, haiku=client)
            detail = educator._ask_haiku(self._action, self._context, lang)
            self.result_ready.emit(detail or "")
        except Exception as e:
            log.debug("HaikuHintThread error: %s", e)
            self.result_ready.emit("")


class GitConfigDialog(QDialog):
    """Dialog for git config user.name + user.email."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("safety_git_config_title"))
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        explain = QLabel(_t("safety_git_config_explain"))
        explain.setWordWrap(True)
        explain.setStyleSheet("padding: 8px; background: #fffff0; border: 1px solid #cccc00;")
        layout.addWidget(explain)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Your Name")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("your@email.com")
        form.addRow("Name:", self.name_input)
        form.addRow("Email:", self.email_input)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self) -> tuple[str, str]:
        return self.name_input.text().strip(), self.email_input.text().strip()


class PickDialog(QDialog):
    """Dialog to pick files from backup branch."""

    def __init__(self, files: list[PickableFile], backup_branch: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("safety_pick_title").format(backup_branch))
        self.setMinimumSize(600, 400)
        self._checkboxes: list[tuple[QCheckBox, str]] = []

        layout = QVBoxLayout(self)

        desc = QLabel(_t("safety_pick_desc"))
        desc.setWordWrap(True)
        desc.setStyleSheet("padding: 8px; color: #333;")
        layout.addWidget(desc)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px inset #808080; background: white; }")

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setAlignment(Qt.AlignTop)

        status_icons = {"added": "+", "modified": "~", "deleted": "-"}
        status_colors = {"added": "#006600", "modified": "#cc6600", "deleted": "#cc0000"}

        for f in files:
            row = QHBoxLayout()
            cb = QCheckBox()
            row.addWidget(cb)
            self._checkboxes.append((cb, f.path))

            icon = status_icons.get(f.status, "?")
            color = status_colors.get(f.status, "#333")

            stat_text = f.path
            if f.status == "added":
                stat_text = f"{icon} {f.path} (NEW, {f.additions} lines)"
            elif f.status == "deleted":
                stat_text = f"{icon} {f.path} (DELETED)"
            else:
                stat_text = f"{icon} {f.path} (+{f.additions} -{f.deletions})"

            path_lbl = QLabel(stat_text)
            path_lbl.setStyleSheet(f"color: {color}; font-family: monospace;")
            row.addWidget(path_lbl)
            row.addStretch()

            wrapper = QWidget()
            wrapper.setLayout(row)
            cl.addWidget(wrapper)

            # Explanation line
            if f.explanation and f.explanation != "Project file":
                exp_lbl = QLabel(f"    {f.explanation}")
                exp_lbl.setStyleSheet("color: #808080; font-size: 11px; padding-left: 24px;")
                cl.addWidget(exp_lbl)

        cl.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._btn_apply = QPushButton(_t("safety_pick_apply"))
        self._btn_apply.setStyleSheet(
            "QPushButton { background: #000080; color: white; padding: 6px 16px; "
            "border: 2px outset #4040c0; font-weight: bold; }"
        )
        self._btn_apply.clicked.connect(self.accept)
        btn_layout.addWidget(self._btn_apply)

        btn_cancel = QPushButton(_t("cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

    def selected_paths(self) -> list[str]:
        return [path for cb, path in self._checkboxes if cb.isChecked()]


class SafetyNetPage(QWidget):
    """Safety Net — save code, rollback, pick working parts."""

    save_point_created = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._db: HistoryDB | None = None
        self._config: dict = {}
        self._safety_net: SafetyNet | None = None
        self._educator: GitEducator | None = None
        self._haiku_thread: HaikuHintThread | None = None
        self._build_ui()

    def set_config(self, config: dict) -> None:
        self._config = config

    def hide_dir_picker(self) -> None:
        if hasattr(self, '_dir_label'):
            self._dir_label.hide()

    def hide_save_section(self) -> None:
        """Hide internal save UI — used when embedded under a unified save button."""
        if hasattr(self, '_save_group'):
            self._save_group.hide()

    def _get_db(self) -> HistoryDB:
        if self._db is None:
            self._db = HistoryDB()
            self._db.init()
        return self._db

    def _get_safety_net(self) -> SafetyNet:
        if self._safety_net is None or self._safety_net._dir != self._project_dir:
            self._safety_net = SafetyNet(
                self._project_dir, self._get_db(), self._config
            )
        return self._safety_net

    def _get_educator(self) -> GitEducator:
        if self._educator is None or self._educator._dir != self._project_dir:
            haiku = None
            try:
                from core.haiku_client import HaikuClient
                haiku = HaikuClient(config=self._config)
                if not haiku.is_available():
                    haiku = None
            except Exception:
                pass
            self._educator = GitEducator(self._project_dir, self._get_db(), haiku)
        return self._educator

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header
        header = QHBoxLayout()
        title = QLabel(_t("safety_title"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        header.addWidget(title)
        header.addStretch()

        self._dir_label = QLabel("")
        self._dir_label.setStyleSheet("color: #808080;")
        header.addWidget(self._dir_label)

        copy_btn = make_copy_all_button(self._get_all_text)
        header.addWidget(copy_btn)

        layout.addLayout(header)

        # Save section
        save_group = QGroupBox(_t("safety_save_label"))
        save_group.setStyleSheet(
            "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
            "padding-top: 16px; font-weight: bold; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
        )
        sg_layout = QVBoxLayout(save_group)

        label_row = QHBoxLayout()
        self._label_input = QLineEdit()
        self._label_input.setPlaceholderText(_t("safety_save_placeholder"))
        self._label_input.setStyleSheet(
            "QLineEdit { border: 2px inset #808080; padding: 4px; background: white; }"
        )
        label_row.addWidget(self._label_input)

        self._btn_save = QPushButton(_t("safety_save_btn"))
        self._btn_save.setEnabled(False)
        self._btn_save.setStyleSheet(
            "QPushButton { background: #000080; color: white; padding: 6px 16px; "
            "border: 2px outset #4040c0; font-weight: bold; }"
            "QPushButton:pressed { border: 2px inset #000080; }"
            "QPushButton:disabled { background: #c0c0c0; color: #808080; }"
        )
        self._btn_save.clicked.connect(self._on_save)
        label_row.addWidget(self._btn_save)
        sg_layout.addLayout(label_row)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #808080; font-size: 11px;")
        sg_layout.addWidget(self._status_label)

        layout.addWidget(save_group)
        self._save_group = save_group

        # Scroll area for save points + backups + what happened
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px inset #808080; background: white; }")

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._content_widget)

        layout.addWidget(scroll)

    def _get_all_text(self) -> str:
        texts = []
        for i in range(self._content_layout.count()):
            item = self._content_layout.itemAt(i)
            if item and item.widget():
                for lbl in item.widget().findChildren(QLabel):
                    text = lbl.text().strip()
                    if text:
                        texts.append(text)
        return "\n".join(texts)

    def _clear_content(self) -> None:
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def set_project_dir(self, path: str) -> None:
        self._project_dir = path
        display = path if len(path) <= 50 else "..." + path[-47:]
        self._dir_label.setText(display)
        self._dir_label.setStyleSheet("color: #000000;")
        self._safety_net = None
        self._educator = None
        self._refresh()

    def _refresh(self) -> None:
        if not self._project_dir:
            self._btn_save.setEnabled(False)
            return

        sn = self._get_safety_net()

        # Update status line
        if not sn._has_git():
            self._status_label.setText(_t("safety_status_no_git"))
            self._status_label.setStyleSheet("color: #cc0000; font-size: 11px;")
            self._btn_save.setEnabled(False)
        elif not sn._is_repo():
            self._status_label.setText(_t("safety_status_no_git"))
            self._status_label.setStyleSheet("color: #cc6600; font-size: 11px;")
            self._btn_save.setEnabled(True)  # will offer git init
        elif not sn._has_changes():
            file_count = sn._count_tracked_files()
            branch = sn._current_branch()
            self._status_label.setText(
                f"{file_count} files tracked | branch: {branch} | {_t('safety_status_clean')}"
            )
            self._status_label.setStyleSheet("color: #006600; font-size: 11px;")
            self._btn_save.setEnabled(False)
            self._btn_save.setToolTip(_t("safety_status_no_changes"))
        else:
            r = sn._git("status", "--porcelain", check=False)
            dirty = len([l for l in r.stdout.splitlines() if l.strip()])
            branch = sn._current_branch()
            file_count = sn._count_tracked_files()
            self._status_label.setText(
                f"{file_count} files tracked | branch: {branch} | "
                f"{_t('safety_status_dirty').format(dirty)}"
            )
            self._status_label.setStyleSheet("color: #cc6600; font-size: 11px;")
            self._btn_save.setEnabled(True)
            self._btn_save.setToolTip("")

        self._render_content()

    def _render_content(self) -> None:
        self._clear_content()
        if not self._project_dir:
            return

        sn = self._get_safety_net()

        # Save Points list
        save_points = sn.get_save_points()
        if save_points:
            sp_group = QGroupBox(_t("safety_save_points_header"))
            sp_group.setStyleSheet(
                "QGroupBox { border: 2px groove #808080; margin-top: 8px; "
                "padding-top: 16px; font-weight: bold; background: white; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
            )
            sp_layout = QVBoxLayout(sp_group)

            for sp in save_points:
                row = self._make_save_point_row(sp)
                sp_layout.addWidget(row)

            self._content_layout.addWidget(sp_group)

        # Backups list
        backups = self._get_db().get_rollback_backups(self._project_dir)
        if backups:
            bk_group = QGroupBox(_t("safety_backups_header"))
            bk_group.setStyleSheet(
                "QGroupBox { border: 2px groove #808080; margin-top: 8px; "
                "padding-top: 16px; font-weight: bold; background: white; }"
                "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }"
            )
            bk_layout = QVBoxLayout(bk_group)

            for bk in backups:
                row = self._make_backup_row(bk)
                bk_layout.addWidget(row)

            self._content_layout.addWidget(bk_group)

        self._content_layout.addStretch()

    def _make_save_point_row(self, sp: dict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; background: white; }"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)

        id_lbl = QLabel(f"#{sp['id']}")
        id_lbl.setStyleSheet("color: #000080; font-weight: bold; font-family: monospace;")
        id_lbl.setFixedWidth(40)
        layout.addWidget(id_lbl)

        time_str = sp["timestamp"][:16].replace("T", " ")
        time_lbl = QLabel(time_str)
        time_lbl.setStyleSheet("color: #333; font-family: monospace;")
        time_lbl.setFixedWidth(130)
        layout.addWidget(time_lbl)

        label_lbl = QLabel(f'"{sp["label"]}"')
        label_lbl.setStyleSheet("color: #333; font-style: italic;")
        layout.addWidget(label_lbl)

        layout.addStretch()

        info_lbl = QLabel(f"{sp['branch']} | {sp['file_count']} files | {sp['commit_hash']}")
        info_lbl.setStyleSheet("color: #808080; font-size: 11px;")
        layout.addWidget(info_lbl)

        btn_rollback = QPushButton(_t("safety_rollback_btn"))
        btn_rollback.setFixedWidth(80)
        btn_rollback.setStyleSheet("QPushButton { font-size: 11px; padding: 2px 8px; }")
        btn_rollback.clicked.connect(lambda _, sid=sp["id"]: self._on_rollback(sid))
        layout.addWidget(btn_rollback)

        return frame

    def _make_backup_row(self, bk: dict) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; background: white; }"
        )
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)

        branch_lbl = QLabel(bk["backup_branch"])
        branch_lbl.setStyleSheet("color: #000080; font-family: monospace; font-weight: bold;")
        layout.addWidget(branch_lbl)

        layout.addStretch()

        info = _t("safety_backup_info").format(
            bk["files_changed"], bk["save_point_id"]
        )
        info_lbl = QLabel(info)
        info_lbl.setStyleSheet("color: #808080; font-size: 11px;")
        layout.addWidget(info_lbl)

        btn_pick = QPushButton(_t("safety_pick_btn"))
        btn_pick.setFixedWidth(110)
        btn_pick.setStyleSheet("QPushButton { font-size: 11px; padding: 2px 8px; }")
        btn_pick.clicked.connect(lambda _, bid=bk["id"]: self._on_pick(bid))
        layout.addWidget(btn_pick)

        return frame

    def _show_what_happened(self, hint: Hint | None, result_text: str,
                            hoff_line: str | None = None) -> None:
        """Show result + teaching moment at the bottom of content."""
        # Remove previous "what happened" block
        for i in range(self._content_layout.count() - 1, -1, -1):
            item = self._content_layout.itemAt(i)
            if item and item.widget() and hasattr(item.widget(), "_is_what_happened"):
                item.widget().deleteLater()
                self._content_layout.removeItem(item)

        frame = QFrame()
        frame._is_what_happened = True
        frame.setStyleSheet(
            "QFrame { border: 2px solid #cccc00; background: #ffffcc; "
            "border-radius: 4px; padding: 6px; margin-top: 8px; }"
        )
        gl = QVBoxLayout(frame)
        gl.setContentsMargins(8, 6, 8, 6)
        gl.setSpacing(4)

        title_lbl = QLabel(f"-- {_t('safety_what_happened')} --")
        title_lbl.setStyleSheet("font-weight: bold; color: #806600; font-size: 12px;")
        gl.addWidget(title_lbl)

        # Result text
        result_lbl = QLabel(result_text)
        result_lbl.setWordWrap(True)
        result_lbl.setStyleSheet("color: #333; font-size: 12px; padding: 4px;")
        gl.addWidget(result_lbl)

        # Teaching hint
        if hint:
            hint_lbl = QLabel(hint.text)
            hint_lbl.setWordWrap(True)
            hint_lbl.setStyleSheet("color: #333; font-size: 11px; padding: 2px 8px;")
            gl.addWidget(hint_lbl)

            cmd_lbl = QLabel(f"({hint.git_command})")
            cmd_lbl.setStyleSheet("color: #808080; font-size: 10px; padding-left: 8px;")
            gl.addWidget(cmd_lbl)

            if hint.detail:
                detail_lbl = QLabel(hint.detail)
                detail_lbl.setWordWrap(True)
                detail_lbl.setStyleSheet(
                    "color: #5500aa; font-style: italic; font-size: 11px; "
                    "padding: 4px 8px; background: #f8f0ff; "
                    "border: 1px solid #d0c0e0; border-radius: 2px;"
                )
                gl.addWidget(detail_lbl)

        # Hasselhoff
        if hoff_line:
            hoff_lbl = QLabel(hoff_line)
            hoff_lbl.setStyleSheet(
                "color: #808080; font-style: italic; padding: 4px 8px; font-size: 11px;"
            )
            gl.addWidget(hoff_lbl)

        self._content_layout.addWidget(frame)

    # --- Actions ---

    def _on_save(self) -> None:
        if not self._project_dir:
            return

        sn = self._get_safety_net()

        # Check if git repo exists
        if not sn._is_repo():
            if not sn._has_git():
                QMessageBox.warning(self, "Git", _t("safety_git_not_found"))
                return
            reply = QMessageBox.question(
                self, _t("safety_git_init_title"),
                _t("safety_git_init_explain"),
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            if not sn.ensure_git():
                QMessageBox.warning(self, "Error", "Could not initialize git.")
                return

        # Pre-save warnings
        warnings = sn.pre_save_warnings()
        if warnings and self._config.get("safety_net", {}).get("auto_gitignore", True):
            patterns_to_fix = []
            for w in warnings:
                reply = QMessageBox.question(
                    self, "Warning",
                    _t(w["message"]),
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    patterns_to_fix.append(w["pattern"])
            if patterns_to_fix:
                sn.fix_gitignore(patterns_to_fix)

        label = self._label_input.text().strip()
        if not label:
            label = _t("safety_save_btn")

        try:
            result = sn.create_save_point(label)
        except RuntimeError as e:
            err = str(e)
            if err == "git_config_missing":
                dlg = GitConfigDialog(self)
                if dlg.exec_() == QDialog.Accepted:
                    name, email = dlg.get_values()
                    if name and email:
                        sn.set_git_user(name, email)
                        try:
                            result = sn.create_save_point(label)
                        except RuntimeError as e2:
                            QMessageBox.warning(self, "Error", str(e2))
                            return
                    else:
                        return
                else:
                    return
            elif err == "no_changes":
                QMessageBox.information(self, "Info", _t("safety_warn_no_changes"))
                return
            else:
                QMessageBox.warning(self, "Error", err)
                return

        self._label_input.clear()
        self.save_point_created.emit()

        # Teaching moment
        educator = self._get_educator()
        counters = educator._get_counters()
        is_first = counters["saves_count"] <= 1
        action = "save_first" if is_first else "save"
        lang = get_language()
        hint = educator.get_hint(action, {
            "file_count": result.file_count,
            "top_files": [],
        }, lang=lang)
        hoff = GitEducator.get_hoff_line("save")

        result_text = (
            f"{_t('safety_saved_msg').format(result.id, label)}\n\n"
            f"{_t('safety_saved_detail').format(result.file_count, result.lines_total)}\n"
            f"Branch: {sn._current_branch()}\n"
            f"Commit: {result.commit_hash}"
        )

        self._refresh()
        self._show_what_happened(hint, result_text, hoff)

    def _on_rollback(self, save_point_id: int) -> None:
        if not self._project_dir:
            return

        sn = self._get_safety_net()
        can, reason = sn.can_rollback(save_point_id)
        if not can:
            if reason == "already_at_save_point":
                msg = _t("safety_rollback_no_changes").format(save_point_id)
                QMessageBox.information(self, "Info", msg)
            elif reason == "merge_in_progress":
                QMessageBox.warning(self, "Error", _t("safety_merge_in_progress"))
            return

        preview = sn.rollback_preview(save_point_id)
        if not preview:
            return

        # Smart Rollback flow: if there are actual file changes, let user
        # pick which features to keep via the dialog. Otherwise fall back
        # to the simple confirm.
        changes = sn.get_changes_since(save_point_id)
        keep_paths: list[str] = []

        if changes:
            from gui.dialogs.smart_rollback import SmartRollbackDialog
            dlg = SmartRollbackDialog(
                save_point_label=preview.target_label,
                save_point_id=save_point_id,
                files=changes,
                config=self._config,
                parent=self,
            )
            if dlg.exec_() != dlg.Accepted:
                return
            keep_paths = dlg.get_kept_paths()

            # Always keep frozen files — user explicitly marked them as
            # "don't touch", shouldn't be reverted by rollback either
            try:
                frozen = self._get_db().get_frozen_files(self._project_dir)
                frozen_paths = {f["path"] for f in frozen}
                changed_paths = {c.path for c in changes}
                auto_keep = list(frozen_paths & changed_paths)
                if auto_keep:
                    merged = list({*keep_paths, *auto_keep})
                    keep_paths = merged
            except Exception:
                pass
        else:
            reply = QMessageBox.question(
                self,
                _t("safety_rollback_btn"),
                _t("safety_rollback_confirm").format(
                    save_point_id, preview.target_label, preview.files_affected
                ),
                QMessageBox.Ok | QMessageBox.Cancel,
            )
            if reply != QMessageBox.Ok:
                return

        result = sn.rollback_with_picks(save_point_id, keep_paths)

        educator = self._get_educator()
        lang = get_language()
        hint = educator.get_hint("rollback", {
            "file_count": result.files_restored,
        }, lang=lang)
        hoff = GitEducator.get_hoff_line("rollback")

        if keep_paths:
            result_text = (
                f"{_t('sr_done_keep').format(save_point_id, len(keep_paths))}\n\n"
                f"Your recent changes saved to: {result.backup_branch}"
            )
        else:
            result_text = (
                f"{_t('safety_rollback_done').format(save_point_id)}\n\n"
                f"Your recent changes saved to: {result.backup_branch}\n"
                f"Files restored: {result.files_restored}"
            )

        self._refresh()
        self._show_what_happened(hint, result_text, hoff)

    def _on_pick(self, backup_id: int) -> None:
        if not self._project_dir:
            return

        sn = self._get_safety_net()
        files = sn.list_pickable_files(backup_id)

        if not files:
            QMessageBox.information(self, "Info", _t("safety_pick_empty"))
            return

        # Find backup branch name
        backups = self._get_db().get_rollback_backups(self._project_dir)
        branch_name = ""
        for b in backups:
            if b["id"] == backup_id:
                branch_name = b["backup_branch"]
                break

        dlg = PickDialog(files, branch_name, self)
        if dlg.exec_() != QDialog.Accepted:
            return

        selected = dlg.selected_paths()
        if not selected:
            return

        try:
            result = sn.pick_files(backup_id, selected)
        except RuntimeError as e:
            QMessageBox.warning(self, "Error", str(e))
            return

        educator = self._get_educator()
        lang = get_language()
        hint = educator.get_hint("pick", {
            "file_count": len(result.files_applied),
            "top_files": result.files_applied[:5],
        }, lang=lang)
        hoff = GitEducator.get_hoff_line("pick")

        file_list = "\n".join(f"+ {f}" for f in result.files_applied)
        result_text = (
            f"{_t('safety_pick_done').format(len(result.files_applied))}\n\n"
            f"{file_list}"
        )

        self._refresh()
        self._show_what_happened(hint, result_text, hoff)

    def create_save_point_quick(self, label: str = "") -> None:
        """Called from Activity/Snapshots page quick-access buttons."""
        if not self._project_dir:
            return

        sn = self._get_safety_net()
        can, reason = sn.can_save()
        if not can:
            caller = self.window() or self
            if reason == "no_changes":
                QMessageBox.information(caller, "Info", _t("safety_warn_no_changes"))
            elif reason == "no_git_repo":
                QMessageBox.information(caller, "Info", _t("safety_git_init_title"))
            elif reason == "git_not_installed":
                QMessageBox.warning(caller, "Git", _t("safety_git_not_found"))
            return

        self._label_input.setText(label)
        self._on_save()
