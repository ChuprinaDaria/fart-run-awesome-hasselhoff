"""Accuracy tests for health scanner — false positive regression suite."""

from pathlib import Path
from core.health.project_map import run_all_checks


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "health_accuracy"


def _findings_by_check(report, check_id):
    return [f for f in report.findings if f.check_id == check_id]


def _finding_titles(report, check_id):
    return [f.title for f in _findings_by_check(report, check_id)]


class TestTypeCheckingImports:
    """Bug 2: imports under `if TYPE_CHECKING:` must not be flagged unused."""

    def test_type_checking_import_not_flagged(self, tmp_path):
        """Copy fixture to tmp_path and scan — User should not appear in unused imports."""
        import shutil
        src = FIXTURES_DIR / "type_checking_imports"
        dst = tmp_path / "project"
        shutil.copytree(src, dst)

        report = run_all_checks(str(dst))
        unused = _finding_titles(report, "dead.unused_imports")
        assert not any("User" in t for t in unused), (
            f"TYPE_CHECKING import 'User' should not be flagged unused. Got: {unused}"
        )

    def test_real_unused_still_caught(self, tmp_path):
        """Ensure TYPE_CHECKING fix doesn't suppress real unused imports."""
        (tmp_path / "app.py").write_text(
            "from __future__ import annotations\n"
            "from typing import TYPE_CHECKING\n"
            "import json\n"  # truly unused
            "\nif TYPE_CHECKING:\n"
            "    from os import PathLike\n"  # TYPE_CHECKING — not unused
            "\nx = 1\n"
        )
        report = run_all_checks(str(tmp_path))
        unused = _finding_titles(report, "dead.unused_imports")
        assert any("json" in t for t in unused), (
            f"Truly unused 'json' should still be flagged. Got: {unused}"
        )
        assert not any("PathLike" in t for t in unused), (
            f"TYPE_CHECKING import 'PathLike' should not be flagged. Got: {unused}"
        )


class TestSingleMethodClass:
    """Bug 4: QThread/QDialog subclasses with __init__+run should not be flagged."""

    def test_qthread_subclass_not_flagged(self, tmp_path):
        (tmp_path / "threads.py").write_text(
            "from PyQt5.QtCore import QThread, pyqtSignal\n\n"
            "class WorkerThread(QThread):\n"
            "    done = pyqtSignal(object)\n\n"
            "    def __init__(self, parent=None):\n"
            "        super().__init__(parent)\n\n"
            "    def run(self):\n"
            "        self.done.emit(42)\n"
        )
        import health as h
        result = h.scan_overengineering(str(tmp_path))
        flagged = [i.description for i in result.issues if i.kind == "single_method_class"]
        assert not any("WorkerThread" in d for d in flagged), (
            f"QThread subclass should not be flagged. Got: {flagged}"
        )

    def test_real_single_method_still_caught(self, tmp_path):
        (tmp_path / "utils.py").write_text(
            "class Wrapper:\n"
            "    def do_thing(self):\n"
            "        return 42\n"
        )
        import health as h
        result = h.scan_overengineering(str(tmp_path))
        flagged = [i.description for i in result.issues if i.kind == "single_method_class"]
        assert any("Wrapper" in d for d in flagged), (
            f"Real single-method class should be flagged. Got: {flagged}"
        )
