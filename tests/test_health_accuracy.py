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


class TestHubCounting:
    """Bug 1: hub counting must show real number of importers."""

    def test_hub_module_count(self, tmp_path):
        """5 files import core/models.py — hub count must be 5."""
        import shutil
        src = FIXTURES_DIR / "hub_counting"
        dst = tmp_path / "project"
        shutil.copytree(src, dst)

        import health as h
        result = h.scan_module_map(str(dst), [])
        hub_dict = {path: count for path, count in result.hub_modules}
        models_count = hub_dict.get("core/models.py", 0)
        assert models_count == 5, (
            f"core/models.py should have 5 importers, got {models_count}. "
            f"Hub modules: {result.hub_modules}"
        )


class TestOrphanReexports:
    """Bug 3: files re-exported via __init__.py must not be flagged orphan."""

    def test_init_reexport_not_orphan(self, tmp_path):
        import shutil
        src = FIXTURES_DIR / "init_reexports"
        dst = tmp_path / "project"
        shutil.copytree(src, dst)

        import health as h
        result = h.scan_module_map(str(dst), [])
        orphans = result.orphan_candidates
        assert "pkg/submodule.py" not in orphans, (
            f"pkg/submodule.py re-exported via __init__.py should not be orphan. "
            f"Orphans: {orphans}"
        )
        assert "pkg/internal.py" not in orphans, (
            f"pkg/internal.py re-exported via __init__.py should not be orphan. "
            f"Orphans: {orphans}"
        )


class TestCommentedCode:
    """Bug 5: doc comments / prose must not be flagged as commented-out code."""

    def test_prose_comments_not_flagged(self, tmp_path):
        """English prose comments should not be flagged as commented code."""
        (tmp_path / "app.py").write_text(
            "x = 1\n"
            "# The confirm=True execution path is already covered end-to-end by\n"
            "# tests/test_safety_net.py::TestSmartRollback. Keeping a separate MCP\n"
            "# integration test for it would re-open the same SQLite file across\n"
            "# tool boundaries and hit locking issues, so we trust the underlying\n"
            "# primitive and verify only the preview branch here.\n"
            "y = 2\n"
        )
        report = run_all_checks(str(tmp_path))
        commented = _findings_by_check(report, "dead.commented_code")
        assert len(commented) == 0, (
            f"Prose comments should not be flagged as code. Got: {commented}"
        )

    def test_real_commented_code_still_caught(self, tmp_path):
        """Actually commented-out code should still be caught."""
        (tmp_path / "app.py").write_text(
            "x = 1\n"
            "# def old_function():\n"
            "#     x = 1\n"
            "#     y = 2\n"
            "#     z = x + y\n"
            "#     return z\n"
            "y = 2\n"
        )
        report = run_all_checks(str(tmp_path))
        commented = _findings_by_check(report, "dead.commented_code")
        assert len(commented) > 0, (
            "Real commented-out code should be flagged"
        )


class TestTestFileCounting:
    """Bug 7: test file counting should exclude fixture directories."""

    def test_fixture_test_files_excluded(self, tmp_path):
        """Test files inside fixtures/ should not be counted as project tests."""
        # Real test file
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_app.py").write_text("def test_one(): pass\n")
        (tests_dir / "test_utils.py").write_text("def test_two(): pass\n")

        # Fixture test file (should be excluded)
        fixtures_dir = tests_dir / "fixtures" / "sample_project" / "tests"
        fixtures_dir.mkdir(parents=True)
        (fixtures_dir / "test_dummy.py").write_text("def test_dummy(): pass\n")

        # Need pyproject.toml for framework detection
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n")

        report = run_all_checks(str(tmp_path))
        test_findings = [f for f in report.findings if f.check_id == "brake.tests"]
        assert len(test_findings) == 1
        # Should count 2 test files, NOT 3
        assert "2 test files" in test_findings[0].message, (
            f"Should count 2 test files (excluding fixture). Got: {test_findings[0].message}"
        )


class TestJsxImports:
    """Bug 1: JSX import resolution must work — components must not be orphans."""

    def test_jsx_imports_resolved(self, tmp_path):
        """App.jsx imports Home.jsx imports Header.jsx — none should be orphans."""
        import shutil
        src = FIXTURES_DIR / "jsx_imports"
        dst = tmp_path / "project"
        shutil.copytree(src, dst)

        import health as h
        result = h.scan_module_map(str(dst), [])
        orphans = result.orphan_candidates
        assert "src/components/Header.jsx" not in orphans, (
            f"Header.jsx is imported by Home.jsx, should not be orphan. Orphans: {orphans}"
        )
        assert "src/pages/Home.jsx" not in orphans, (
            f"Home.jsx is imported by App.jsx, should not be orphan. Orphans: {orphans}"
        )

    def test_jsx_hub_counting(self, tmp_path):
        """Imports from JSX files must be counted in hub modules."""
        import shutil
        src = FIXTURES_DIR / "jsx_imports"
        dst = tmp_path / "project"
        shutil.copytree(src, dst)

        import health as h
        result = h.scan_module_map(str(dst), [])
        # Header.jsx is imported by Home.jsx → imported_by >= 1
        modules_dict = {m.path: m.imported_by_count for m in result.modules}
        header_count = modules_dict.get("src/components/Header.jsx", 0)
        assert header_count >= 1, (
            f"Header.jsx should have >= 1 importer, got {header_count}. Modules: {modules_dict}"
        )
