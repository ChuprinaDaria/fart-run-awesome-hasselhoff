# Phase 5-8: Universal Installer, Haiku AI, Dynamic Discover, Persistence

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 5 — MCP/Skills installer with drop-link, security check, API key handling, Anthropic auto-discovery, curated lists from GitHub MD. Phase 6 — Claude Haiku for personalized tips, model advisor, security explanations. Phase 7 — Dynamic Discover tab from GitHub MD files with education links (Prometheus UA + Coursera EN). Phase 8 — SQLite persistence for trends, graphs, budget forecasting.

**Architecture:** MD fetcher (`core/md_fetcher.py`) shared across Phases 5/7. Haiku client (`core/haiku_client.py`) with caching. SQLite via `core/sqlite_db.py` (already exists, needs activation). Graphs via pyqtgraph or matplotlib embedded in PyQt5.

**Tech Stack:** Python 3.11+, PyQt5, httpx/urllib, anthropic SDK (optional), aiosqlite, pyqtgraph

**Depends on:** Phases 0-3 (platform, cleanup, overview redesign)

---

## Phase 5: Universal Installer + Discovery

### File Structure

**New files:**
- `core/md_fetcher.py` — Fetch + parse MD from GitHub raw URLs, with file cache
- `core/mcp_installer.py` — MCP server installer logic (settings.json manipulation)
- `core/skill_installer.py` — Skill installer logic (git clone + settings)
- `core/repo_scanner.py` — Security scan of a cloned repo before install
- `gui/pages/installer.py` — Replaces hasselhoff_wizard.py: drop-link UI with security check
- `data/curated.md` — Curated MCP/Skills list (lives on GitHub, fetched at runtime)
- `tests/test_md_fetcher.py`
- `tests/test_mcp_installer.py`

**Files to modify:**
- `gui/app.py` — Replace HasselhoffWizardPage with InstallerPage
- `gui/pages/hasselhoff_wizard.py` — Hasselhoff theme stays but content changes to MCP/Skills
- `i18n/en.py`, `i18n/ua.py` — New strings

**Files to delete:**
- `tools.json` — IDE installer data, no longer needed

---

### Task 1: MD Fetcher — shared infrastructure

**Files:**
- Create: `core/md_fetcher.py`
- Create: `tests/test_md_fetcher.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_md_fetcher.py
from core.md_fetcher import parse_resource_md, Section, Resource


def test_parse_sections():
    md = """## MCP Servers
- [Playwright](https://github.com/anthropics/playwright-mcp) — Browser automation
- [PostgreSQL](https://github.com/example/pg-mcp) — Database queries

## Skills
- [Superpowers](https://github.com/example/superpowers) — TDD, debugging
"""
    sections = parse_resource_md(md)
    assert len(sections) == 2
    assert sections[0].title == "MCP Servers"
    assert len(sections[0].items) == 2
    assert sections[0].items[0].title == "Playwright"
    assert sections[0].items[0].url == "https://github.com/anthropics/playwright-mcp"
    assert sections[0].items[0].description == "Browser automation"
    assert sections[1].title == "Skills"
    assert len(sections[1].items) == 1


def test_parse_empty_md():
    sections = parse_resource_md("")
    assert sections == []


def test_parse_education_md():
    from core.md_fetcher import parse_education_md
    md = """## Docker Security
### en
- [Coursera: Docker Security](https://coursera.org/docker) — Container hardening
### ua
- [Prometheus: Docker безпека](https://prometheus.org.ua/docker) — Контейнерна безпека
"""
    result = parse_education_md(md)
    assert "Docker Security" in result
    assert "en" in result["Docker Security"]
    assert "ua" in result["Docker Security"]
    assert result["Docker Security"]["en"][0].title == "Coursera: Docker Security"
    assert result["Docker Security"]["ua"][0].title == "Prometheus: Docker безпека"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_md_fetcher.py -v`
Expected: FAIL

- [ ] **Step 3: Implement md_fetcher**

```python
# core/md_fetcher.py
"""Fetch and parse Markdown resource files from GitHub or local cache."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

from core.platform import get_platform

log = logging.getLogger(__name__)

CACHE_TTL = 86400  # 24 hours


@dataclass
class Resource:
    title: str
    url: str
    description: str = ""


@dataclass
class Section:
    title: str
    items: list[Resource] = field(default_factory=list)


def fetch_md(url: str, cache_name: str | None = None) -> str:
    """Fetch MD from URL with local file cache. Returns content string."""
    platform = get_platform()
    cache_dir = platform.cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_file = cache_dir / (cache_name or _url_to_filename(url))

    # Check cache
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < CACHE_TTL:
            return cache_file.read_text(encoding="utf-8")

    # Fetch
    try:
        req = Request(url, headers={"User-Agent": "claude-monitor/3.0"})
        with urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
        cache_file.write_text(content, encoding="utf-8")
        return content
    except (URLError, OSError) as e:
        log.warning("Failed to fetch %s: %s", url, e)
        # Fallback to stale cache
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")
        return ""


def _url_to_filename(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", url)[-80:] + ".md"


# --- Line format: - [Title](url) — description ---
_ITEM_RE = re.compile(r"^-\s+\[(.+?)\]\((.+?)\)\s*[—–-]\s*(.*)$")


def parse_resource_md(content: str) -> list[Section]:
    """Parse MD with ## sections and - [Title](url) — desc items."""
    sections: list[Section] = []
    current: Section | None = None

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("## "):
            current = Section(title=line[3:].strip())
            sections.append(current)
            continue
        if current is None:
            continue
        m = _ITEM_RE.match(line)
        if m:
            current.items.append(Resource(
                title=m.group(1).strip(),
                url=m.group(2).strip(),
                description=m.group(3).strip(),
            ))

    return sections


def parse_education_md(content: str) -> dict[str, dict[str, list[Resource]]]:
    """Parse education MD: ## Category → ### lang → items.

    Returns: {category: {lang: [Resource, ...]}}
    """
    result: dict[str, dict[str, list[Resource]]] = {}
    current_cat: str | None = None
    current_lang: str | None = None

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("## "):
            current_cat = line[3:].strip()
            result[current_cat] = {}
            current_lang = None
            continue
        if line.startswith("### ") and current_cat:
            current_lang = line[4:].strip()
            result[current_cat][current_lang] = []
            continue
        if current_cat and current_lang:
            m = _ITEM_RE.match(line)
            if m:
                result[current_cat][current_lang].append(Resource(
                    title=m.group(1).strip(),
                    url=m.group(2).strip(),
                    description=m.group(3).strip(),
                ))

    return result
```

- [ ] **Step 4: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_md_fetcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/md_fetcher.py tests/test_md_fetcher.py
git commit -m "feat: MD fetcher — parse GitHub resource/education files with cache"
```

---

### Task 2: MCP/Skill Installer core logic

**Files:**
- Create: `core/mcp_installer.py`
- Create: `core/repo_scanner.py`
- Create: `tests/test_mcp_installer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_mcp_installer.py
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from core.mcp_installer import (
    detect_mcp_type, parse_mcp_readme, install_mcp_server,
    MCPServerConfig,
)


def test_detect_mcp_type_npm():
    assert detect_mcp_type({"package.json": True, "requirements.txt": False}) == "npm"


def test_detect_mcp_type_pip():
    assert detect_mcp_type({"package.json": False, "requirements.txt": True}) == "pip"


def test_detect_mcp_type_unknown():
    assert detect_mcp_type({"package.json": False, "requirements.txt": False}) == "unknown"


def test_parse_mcp_readme_finds_env_vars():
    readme = """
# My MCP Server
Set `OPENAI_API_KEY` environment variable.
Also needs `DATABASE_URL`.
"""
    env_vars = parse_mcp_readme(readme)
    assert "OPENAI_API_KEY" in env_vars
    assert "DATABASE_URL" in env_vars


def test_mcp_server_config_to_json():
    config = MCPServerConfig(
        name="playwright",
        command="npx",
        args=["-y", "@anthropic/playwright-mcp"],
        env={"DISPLAY": ":0"},
    )
    d = config.to_dict()
    assert d["command"] == "npx"
    assert d["args"] == ["-y", "@anthropic/playwright-mcp"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_mcp_installer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement mcp_installer**

```python
# core/mcp_installer.py
"""MCP Server and Skill installer — adds to ~/.claude/settings.json."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"

# Regex to find env var references in README
_ENV_VAR_RE = re.compile(r"`([A-Z][A-Z0-9_]{2,})`")


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d: dict = {"command": self.command, "args": self.args}
        if self.env:
            d["env"] = self.env
        return d


def detect_mcp_type(files: dict[str, bool]) -> str:
    """Detect MCP server type from repo file presence."""
    if files.get("package.json"):
        return "npm"
    if files.get("requirements.txt") or files.get("pyproject.toml") or files.get("setup.py"):
        return "pip"
    return "unknown"


def parse_mcp_readme(readme_content: str) -> list[str]:
    """Extract environment variable names from README."""
    # Find backtick-quoted ALL_CAPS names
    env_vars = _ENV_VAR_RE.findall(readme_content)
    # Filter to likely env vars (not commands)
    common_non_env = {"README", "LICENSE", "INSTALL", "TODO", "NOTE", "IMPORTANT"}
    return [v for v in set(env_vars) if v not in common_non_env and len(v) >= 4]


def read_settings() -> dict:
    """Read ~/.claude/settings.json."""
    if _CLAUDE_SETTINGS.exists():
        return json.loads(_CLAUDE_SETTINGS.read_text())
    return {}


def write_settings(settings: dict) -> None:
    """Write ~/.claude/settings.json."""
    _CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    _CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2))


def install_mcp_server(config: MCPServerConfig) -> bool:
    """Add MCP server to settings.json."""
    settings = read_settings()
    servers = settings.setdefault("mcpServers", {})
    servers[config.name] = config.to_dict()
    write_settings(settings)
    log.info("Installed MCP server: %s", config.name)
    return True


def uninstall_mcp_server(name: str) -> bool:
    """Remove MCP server from settings.json."""
    settings = read_settings()
    servers = settings.get("mcpServers", {})
    if name in servers:
        del servers[name]
        write_settings(settings)
        return True
    return False


def install_skill_from_url(git_url: str, name: str | None = None) -> bool:
    """Clone skill repo and register in settings."""
    skills_dir = Path.home() / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    repo_name = name or git_url.rstrip("/").split("/")[-1].replace(".git", "")
    dest = skills_dir / repo_name

    if dest.exists():
        log.warning("Skill already exists: %s", dest)
        return False

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", git_url, str(dest)],
            check=True, capture_output=True, timeout=60,
        )
        log.info("Installed skill: %s → %s", git_url, dest)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.error("Failed to clone skill: %s", e)
        return False
```

```python
# core/repo_scanner.py
"""Security scan of a repository before installing as MCP/Skill."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class RepoScanResult:
    safe: bool
    warnings: list[str]
    blockers: list[str]  # critical issues that should prevent install


def scan_repo(repo_path: Path) -> RepoScanResult:
    """Scan a cloned repo for security issues before install."""
    warnings = []
    blockers = []

    # Check package.json postinstall scripts
    pkg_json = repo_path / "package.json"
    if pkg_json.exists():
        import json
        try:
            data = json.loads(pkg_json.read_text())
            scripts = data.get("scripts", {})
            for hook in ("postinstall", "preinstall", "prepare"):
                val = scripts.get(hook, "")
                for bad in ("curl", "wget", "eval", "exec", "child_process", "| sh", "| bash"):
                    if bad in val:
                        blockers.append(f"npm {hook} script contains '{bad}': {val[:100]}")
        except (json.JSONDecodeError, OSError):
            warnings.append("Cannot parse package.json")

    # Check for suspicious files
    suspicious_extensions = {".exe", ".dll", ".so", ".dylib", ".bin"}
    for f in repo_path.rglob("*"):
        if f.suffix.lower() in suspicious_extensions:
            warnings.append(f"Binary file found: {f.relative_to(repo_path)}")

    # Check for obfuscated code
    for f in repo_path.rglob("*.js"):
        try:
            content = f.read_text(errors="replace")
            if len(content) > 1000 and content.count("\n") < 5:
                warnings.append(f"Possibly obfuscated JS: {f.relative_to(repo_path)}")
        except OSError:
            pass

    # Run typosquatting check on dependencies
    from plugins.security_scan.scanners import _KNOWN_MALICIOUS_NPM, _KNOWN_MALICIOUS_PYTHON, _is_typosquat, _POPULAR_NPM, _POPULAR_PYTHON

    req_files = list(repo_path.glob("requirements*.txt"))
    for req in req_files:
        for line in req.read_text(errors="replace").splitlines():
            pkg = line.strip().split("=")[0].split(">")[0].split("<")[0].strip()
            if pkg.lower() in {m.lower() for m in _KNOWN_MALICIOUS_PYTHON}:
                blockers.append(f"Known malicious Python package: {pkg}")
            elif _is_typosquat(pkg, _POPULAR_PYTHON):
                warnings.append(f"Possible typosquat: {pkg}")

    safe = len(blockers) == 0
    return RepoScanResult(safe=safe, warnings=warnings, blockers=blockers)
```

Wait — `RepoScanResult` needs `from dataclasses import dataclass`. Fix:

```python
# At top of core/repo_scanner.py:
from dataclasses import dataclass, field
```

- [ ] **Step 4: Run tests**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/test_mcp_installer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/mcp_installer.py core/repo_scanner.py tests/test_mcp_installer.py
git commit -m "feat: MCP/Skill installer core — settings.json manipulation, repo security scan"
```

---

### Task 3: Installer GUI page (replaces Hasselhoff Wizard content)

**Files:**
- Create: `gui/pages/installer.py`
- Modify: `gui/app.py`

- [ ] **Step 1: Create installer page with drop-link UI**

```python
# gui/pages/installer.py
"""Universal MCP/Skills Installer — drop a GitHub URL, security check, install."""

import subprocess
import tempfile
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QGroupBox, QScrollArea, QFormLayout,
    QMessageBox, QProgressBar, QTextEdit,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from i18n import get_string as _t, get_language
from core.md_fetcher import fetch_md, parse_resource_md
from core.mcp_installer import (
    MCPServerConfig, detect_mcp_type, parse_mcp_readme,
    install_mcp_server, install_skill_from_url,
)
from core.repo_scanner import scan_repo, RepoScanResult


# GitHub raw URL for curated list (update with actual repo URL)
CURATED_MD_URL = "https://raw.githubusercontent.com/YOUR_ORG/claude-monitor/master/data/curated.md"


class InstallThread(QThread):
    """Background thread for cloning and scanning repos."""
    finished = pyqtSignal(dict)  # {"success": bool, "message": str, "scan": RepoScanResult|None}

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            # Clone to temp dir
            tmp = Path(tempfile.mkdtemp(prefix="claude-monitor-"))
            repo_dir = tmp / "repo"
            subprocess.run(
                ["git", "clone", "--depth", "1", self._url, str(repo_dir)],
                check=True, capture_output=True, timeout=60,
            )

            # Security scan
            scan_result = scan_repo(repo_dir)

            # Detect type
            files = {
                "package.json": (repo_dir / "package.json").exists(),
                "requirements.txt": (repo_dir / "requirements.txt").exists(),
                "pyproject.toml": (repo_dir / "pyproject.toml").exists(),
                "setup.py": (repo_dir / "setup.py").exists(),
                "SKILL.md": (repo_dir / "SKILL.md").exists(),
            }

            # Read README for env vars
            readme = ""
            for name in ("README.md", "README.rst", "README"):
                readme_path = repo_dir / name
                if readme_path.exists():
                    readme = readme_path.read_text(errors="replace")
                    break

            env_vars = parse_mcp_readme(readme)
            mcp_type = detect_mcp_type(files)
            is_skill = files.get("SKILL.md", False)

            self.finished.emit({
                "success": True,
                "scan": scan_result,
                "repo_dir": str(repo_dir),
                "mcp_type": mcp_type,
                "is_skill": is_skill,
                "env_vars": env_vars,
                "url": self._url,
                "readme_preview": readme[:500],
            })
        except Exception as e:
            self.finished.emit({"success": False, "message": str(e), "scan": None})


class InstallerPage(QWidget):
    """MCP/Skills installer with security scanning."""

    hoff_event = pyqtSignal(str)  # Keep Hasselhoff for this page

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # --- Drop Link Section ---
        install_group = QGroupBox("Install MCP Server or Skill")
        ig = QVBoxLayout()

        url_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste GitHub URL here...")
        self.url_input.setStyleSheet(
            "background: white; border: 2px inset #808080; padding: 4px; font-size: 13px;"
        )
        url_layout.addWidget(self.url_input, stretch=1)

        self.scan_btn = QPushButton("Scan & Install")
        self.scan_btn.setStyleSheet(
            "background: #000080; color: white; border: 2px outset #4040c0; "
            "padding: 6px 16px; font-weight: bold;"
        )
        self.scan_btn.clicked.connect(self._start_scan)
        url_layout.addWidget(self.scan_btn)
        ig.addLayout(url_layout)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        ig.addWidget(self.progress)

        # Scan results
        self.scan_output = QTextEdit()
        self.scan_output.setReadOnly(True)
        self.scan_output.setMaximumHeight(150)
        self.scan_output.setStyleSheet("background: white; border: 2px inset #808080; font-size: 11px;")
        self.scan_output.setVisible(False)
        ig.addWidget(self.scan_output)

        # Env var inputs (dynamic)
        self.env_form = QFormLayout()
        self.env_inputs: dict[str, QLineEdit] = {}
        ig.addLayout(self.env_form)

        # Install button (shown after scan)
        self.install_btn = QPushButton("Install")
        self.install_btn.setStyleSheet(
            "background: #006600; color: white; border: 2px outset #40c040; "
            "padding: 6px 16px; font-weight: bold;"
        )
        self.install_btn.clicked.connect(self._do_install)
        self.install_btn.setVisible(False)
        ig.addWidget(self.install_btn)

        self.status_label = QLabel("")
        ig.addWidget(self.status_label)

        install_group.setLayout(ig)
        layout.addWidget(install_group)

        # --- Curated List ---
        curated_group = QGroupBox("Recommended")
        cg = QVBoxLayout()
        self.curated_scroll = QScrollArea()
        self.curated_scroll.setWidgetResizable(True)
        self.curated_container = QWidget()
        self.curated_layout = QVBoxLayout(self.curated_container)
        self.curated_layout.setAlignment(Qt.AlignTop)
        self.curated_scroll.setWidget(self.curated_container)
        cg.addWidget(self.curated_scroll)
        curated_group.setLayout(cg)
        layout.addWidget(curated_group)

        self._pending_result = None
        self._load_curated()

    def _load_curated(self):
        """Load curated MCP/Skills list from GitHub MD."""
        try:
            content = fetch_md(CURATED_MD_URL, cache_name="curated.md")
            sections = parse_resource_md(content)
            for section in sections:
                header = QLabel(f"<b>{section.title}</b>")
                header.setStyleSheet("font-size: 13px; padding: 4px; color: #000080;")
                self.curated_layout.addWidget(header)
                for item in section.items:
                    row = QHBoxLayout()
                    lbl = QLabel(f"<b>{item.title}</b> — {item.description}")
                    lbl.setWordWrap(True)
                    lbl.setStyleSheet("padding: 2px 4px;")
                    row.addWidget(lbl, stretch=1)
                    btn = QPushButton("Install")
                    btn.setFixedWidth(80)
                    btn.clicked.connect(lambda checked, url=item.url: self._quick_install(url))
                    row.addWidget(btn)
                    container = QWidget()
                    container.setLayout(row)
                    container.setStyleSheet(
                        "background: white; border: 2px groove #808080; margin: 1px;"
                    )
                    self.curated_layout.addWidget(container)
        except Exception as e:
            self.curated_layout.addWidget(QLabel(f"Could not load curated list: {e}"))

    def _quick_install(self, url: str):
        self.url_input.setText(url)
        self._start_scan()

    def _start_scan(self):
        url = self.url_input.text().strip()
        if not url:
            return
        self.progress.setVisible(True)
        self.scan_output.setVisible(False)
        self.install_btn.setVisible(False)
        self.scan_btn.setEnabled(False)
        self.status_label.setText("Scanning...")

        self._thread = InstallThread(url)
        self._thread.finished.connect(self._on_scan_done)
        self._thread.start()

    def _on_scan_done(self, result: dict):
        self.progress.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.scan_output.setVisible(True)

        if not result["success"]:
            self.scan_output.setPlainText(f"Error: {result['message']}")
            self.status_label.setText("Scan failed")
            return

        self._pending_result = result
        scan: RepoScanResult = result["scan"]

        # Show scan results
        output = []
        if scan.blockers:
            output.append("🚫 BLOCKERS (install not recommended):")
            for b in scan.blockers:
                output.append(f"  - {b}")
        if scan.warnings:
            output.append("⚠ Warnings:")
            for w in scan.warnings:
                output.append(f"  - {w}")
        if not scan.blockers and not scan.warnings:
            output.append("✓ No security issues found")

        output.append(f"\nType: {'Skill' if result['is_skill'] else f'MCP ({result[\"mcp_type\"]})'}")
        if result["env_vars"]:
            output.append(f"Required env vars: {', '.join(result['env_vars'])}")

        self.scan_output.setPlainText("\n".join(output))

        # Show env var inputs
        self._clear_env_form()
        for var in result.get("env_vars", []):
            inp = QLineEdit()
            inp.setPlaceholderText(f"Enter {var}...")
            inp.setStyleSheet("background: white; border: 2px inset #808080; padding: 2px;")
            self.env_inputs[var] = inp
            self.env_form.addRow(f"{var}:", inp)

        # Show install button if safe
        if scan.safe:
            self.install_btn.setVisible(True)
            self.status_label.setText("Ready to install")
        else:
            self.status_label.setText("Install blocked — fix security issues first")
            self.status_label.setStyleSheet("color: #cc0000;")

    def _clear_env_form(self):
        while self.env_form.count():
            item = self.env_form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.env_inputs.clear()

    def _do_install(self):
        if not self._pending_result:
            return

        result = self._pending_result
        env = {k: v.text() for k, v in self.env_inputs.items() if v.text()}

        if result["is_skill"]:
            ok = install_skill_from_url(result["url"])
        else:
            # Build MCP config
            name = result["url"].rstrip("/").split("/")[-1].replace(".git", "")
            mcp_type = result["mcp_type"]
            if mcp_type == "npm":
                config = MCPServerConfig(name=name, command="npx", args=["-y", result["url"]], env=env)
            elif mcp_type == "pip":
                config = MCPServerConfig(name=name, command="uvx", args=[result["url"]], env=env)
            else:
                config = MCPServerConfig(name=name, command="node", args=["index.js"], env=env)
            ok = install_mcp_server(config)

        if ok:
            self.status_label.setText("Installed successfully!")
            self.status_label.setStyleSheet("color: #006600;")
            self.hoff_event.emit(f"Installed {result['url'].split('/')[-1]}!")
        else:
            self.status_label.setText("Installation failed")
            self.status_label.setStyleSheet("color: #cc0000;")
```

- [ ] **Step 2: Wire into app.py**

Replace `HasselhoffWizardPage` with `InstallerPage` in imports and page creation. Keep the Hasselhoff Wizard page as a renamed tab but with new content.

- [ ] **Step 3: Run tests, commit**

```bash
git add gui/pages/installer.py core/mcp_installer.py core/repo_scanner.py gui/app.py
git commit -m "feat: Universal MCP/Skills Installer — drop link, security scan, API key fields"
```

---

### Task 4: Create data/curated.md

**Files:**
- Create: `data/curated.md`

- [ ] **Step 1: Create the curated list**

```markdown
## MCP Servers
- [Playwright](https://github.com/microsoft/playwright-mcp) — Browser automation, E2E testing, screenshots
- [PostgreSQL](https://github.com/modelcontextprotocol/servers/tree/main/src/postgres) — Database queries, schema inspection
- [Filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) — File operations, directory listing
- [GitHub](https://github.com/modelcontextprotocol/servers/tree/main/src/github) — Issues, PRs, repos, commits
- [Slack](https://github.com/modelcontextprotocol/servers/tree/main/src/slack) — Messages, channels, users
- [Sequential Thinking](https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking) — Structured reasoning for complex problems
- [Brave Search](https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search) — Web search via Brave API
- [Puppeteer](https://github.com/modelcontextprotocol/servers/tree/main/src/puppeteer) — Headless browser control

## Skills
- [Superpowers](https://github.com/anthropics/claude-code-superpowers) — TDD, debugging, planning, code review workflows
- [Firecrawl](https://github.com/anthropics/claude-code-firecrawl) — Web scraping, search, crawling
- [CodeRabbit](https://github.com/coderabbitai/claude-code-coderabbit) — AI code review
- [Fullstack Dev Skills](https://github.com/anthropics/claude-code-fullstack-skills) — 50+ framework-specific skills
```

- [ ] **Step 2: Commit**

```bash
git add data/curated.md
git commit -m "feat: curated MCP/Skills list — GitHub MD for dynamic updates"
```

---

## Phase 6: Claude Haiku AI Integration

### Task 5: Haiku client with caching

**Files:**
- Create: `core/haiku_client.py`
- Create: `tests/test_haiku_client.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_haiku_client.py
from unittest.mock import patch, MagicMock
from core.haiku_client import HaikuClient


def test_client_disabled_without_key():
    client = HaikuClient(api_key=None)
    assert not client.is_available()


def test_client_enabled_with_key():
    client = HaikuClient(api_key="sk-ant-test-key")
    assert client.is_available()


def test_ask_returns_cached():
    client = HaikuClient(api_key="sk-ant-test")
    client._cache["test_prompt"] = "cached_response"
    result = client.ask("test_prompt")
    assert result == "cached_response"
```

- [ ] **Step 2: Implement Haiku client**

```python
# core/haiku_client.py
"""Claude Haiku client for personalized tips and explanations."""

from __future__ import annotations

import hashlib
import logging
import os
import time

log = logging.getLogger(__name__)

_MIN_INTERVAL = 300  # 5 minutes between API calls


class HaikuClient:
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._cache: dict[str, str] = {}
        self._last_call: float = 0
        self._client = None

    def is_available(self) -> bool:
        return self._api_key is not None

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                log.warning("anthropic SDK not installed — Haiku features disabled")
                self._api_key = None
        return self._client

    def ask(self, prompt: str, max_tokens: int = 200) -> str | None:
        """Ask Haiku a question. Returns cached response if available."""
        cache_key = hashlib.md5(prompt.encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.is_available():
            return None

        # Rate limiting
        now = time.time()
        if now - self._last_call < _MIN_INTERVAL:
            return None

        client = self._get_client()
        if not client:
            return None

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            result = response.content[0].text
            self._cache[cache_key] = result
            self._last_call = now
            return result
        except Exception as e:
            log.error("Haiku API error: %s", e)
            return None

    def get_tip(self, stats_summary: str) -> str | None:
        """Get personalized tip based on usage stats."""
        prompt = (
            f"You are a Claude Code usage advisor. Based on these stats, give ONE specific, "
            f"actionable tip to save tokens or improve efficiency. Max 2 sentences.\n\n"
            f"Stats: {stats_summary}"
        )
        return self.ask(prompt)

    def recommend_model(self, task_description: str) -> str | None:
        """Recommend model based on task."""
        prompt = (
            f"You are a Claude model advisor. For this task, recommend Opus, Sonnet, or Haiku. "
            f"ONE sentence. Include estimated token savings.\n\n"
            f"Task: {task_description[:200]}"
        )
        return self.ask(prompt, max_tokens=100)

    def explain_finding(self, finding_description: str, project_context: str = "") -> str | None:
        """Explain a security finding in context."""
        prompt = (
            f"Explain this security finding in simple terms for a developer. "
            f"What is the risk? How to fix it? 3 sentences max.\n\n"
            f"Finding: {finding_description}\n"
            f"Project context: {project_context or 'general dev environment'}"
        )
        return self.ask(prompt, max_tokens=150)
```

- [ ] **Step 3: Run tests, commit**

```bash
git add core/haiku_client.py tests/test_haiku_client.py
git commit -m "feat: Claude Haiku client — personalized tips, model advisor, security explanations"
```

---

### Task 6: Wire Haiku into Tips and Security

**Files:**
- Modify: `core/tips.py`
- Modify: `gui/pages/security.py`
- Modify: `core/config.py`

- [ ] **Step 1: Add AI config defaults**

In `core/config.py` DEFAULTS:
```python
"ai": {
    "enabled": False,
    "api_key": "",  # or use ANTHROPIC_API_KEY env var
},
```

- [ ] **Step 2: Add Haiku tip to TipsEngine**

In `core/tips.py`, at the end of `get_tips` method, before sorting:

```python
# --- AI-powered tip (if available) ---
try:
    from core.haiku_client import HaikuClient
    haiku = HaikuClient()
    if haiku.is_available():
        summary = (
            f"Cache efficiency: {cache_eff:.0f}%, "
            f"Sessions: {len(stats.sessions)}, "
            f"Models: {list(stats.model_totals.keys())}, "
            f"Total billable: {stats.total_billable}, "
            f"Cost: ${cost.total_cost:.2f}"
        )
        ai_tip = haiku.get_tip(summary)
        if ai_tip:
            tips.append(Tip(
                category="ai", relevance=0.99,
                message_en=f"🤖 {ai_tip}",
                message_ua=f"🤖 {ai_tip}",
            ))
except ImportError:
    pass
```

- [ ] **Step 3: Add Haiku explanation in Security detail panel**

In `gui/pages/security.py`, when showing finding details:

```python
# After showing static explanation, try Haiku:
try:
    from core.haiku_client import HaikuClient
    haiku = HaikuClient()
    if haiku.is_available():
        ai_explanation = haiku.explain_finding(finding["description"])
        if ai_explanation:
            self.ai_label.setText(f"🤖 AI: {ai_explanation}")
            self.ai_label.setVisible(True)
except ImportError:
    pass
```

- [ ] **Step 4: Commit**

```bash
git add core/tips.py gui/pages/security.py core/config.py
git commit -m "feat: Haiku AI tips in Tips tab, AI security explanations"
```

---

## Phase 7: Dynamic Discover + Education

### Task 7: Discover tab from GitHub MD

**Files:**
- Modify: `gui/pages/discover.py`
- Create: `data/resources.md`
- Create: `data/education.md`

- [ ] **Step 1: Create data/resources.md**

```markdown
## Token Optimization
- [18 Token Management Hacks](https://www.mindstudio.ai/blog/claude-code-token-management-hacks-3/) — Practical tips for saving tokens
- [6 Ways to Cut Usage in Half](https://www.sabrina.dev/p/6-ways-i-cut-my-claude-token-usage) — CLAUDE.md, /compact, model switching
- [Prompt Caching Deep Dive](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) — Save 90% on repeated tokens

## Documentation
- [Claude Code Memory](https://docs.anthropic.com/en/docs/claude-code/memory) — CLAUDE.md project memory guide
- [Claude Code Hooks](https://docs.anthropic.com/en/docs/claude-code/hooks) — Pre/post tool hooks
- [Slash Commands](https://docs.anthropic.com/en/docs/claude-code/cli-usage) — /compact /model /review /pr /init
- [Claude Agent SDK](https://docs.anthropic.com/en/docs/agents-and-tools/claude-agent-sdk) — Build custom AI agents
- [IDE Extensions](https://docs.anthropic.com/en/docs/claude-code/ide-integrations) — VS Code, JetBrains

## Community
- [r/ClaudeCode](https://www.reddit.com/r/ClaudeCode/) — Active community
- [Awesome Claude Skills](https://github.com/ComposioHQ/awesome-claude-skills) — 30+ curated skills
- [MCP Servers Directory](https://github.com/modelcontextprotocol/servers) — 100+ MCP servers
- [Claude Code GitHub Issues](https://github.com/anthropics/claude-code/issues) — Bug reports, feature requests
```

- [ ] **Step 2: Create data/education.md**

```markdown
## Docker Security
### en
- [Coursera: Docker Security Essentials](https://www.coursera.org/learn/docker-security) — Container hardening fundamentals
- [TryHackMe: Docker Security](https://tryhackme.com/room/dvwa) — Hands-on labs

### ua
- [Prometheus: Кібербезпека](https://prometheus.org.ua/course/course-v1:Prometheus+CS50+2021_T1) — Основи кібербезпеки
- [DOU: Docker безпека](https://dou.ua/) — Практичні поради

## Network Security
### en
- [Coursera: Network Security](https://www.coursera.org/learn/network-security) — Firewalls, monitoring
- [HackTheBox: Network Challenges](https://www.hackthebox.com/) — Practical exercises

### ua
- [Prometheus: Мережеві технології](https://prometheus.org.ua/) — Основи мережевої безпеки
- [Projector: Кібербезпека для розробників](https://prjctr.com/) — Безпека в розробці

## System Security
### en
- [Coursera: OS Security](https://www.coursera.org/learn/os-security) — Linux hardening
- [TryHackMe: Linux Security](https://tryhackme.com/) — Hands-on challenges

### ua
- [Prometheus: Linux](https://prometheus.org.ua/) — Адміністрування Linux
- [Mate Academy: Основи безпеки](https://mate.academy/) — Базовий курс

## Supply Chain Security
### en
- [Coursera: Software Supply Chain Security](https://www.coursera.org/learn/software-supply-chain-security) — Dependencies, SBOMs
- [Snyk Learn](https://learn.snyk.io/) — Interactive security lessons

### ua
- [Prometheus: Розробка безпечного ПЗ](https://prometheus.org.ua/) — Безпека коду
- [DOU: Supply chain атаки](https://dou.ua/) — Атаки через залежності
```

- [ ] **Step 3: Rewrite discover.py to use MD fetcher**

Replace hardcoded `DISCOVER_RESOURCES` with:

```python
# gui/pages/discover.py
from core.md_fetcher import fetch_md, parse_resource_md, parse_education_md

RESOURCES_MD_URL = "https://raw.githubusercontent.com/YOUR_ORG/claude-monitor/master/data/resources.md"
EDUCATION_MD_URL = "https://raw.githubusercontent.com/YOUR_ORG/claude-monitor/master/data/education.md"


class DiscoverTab(QWidget):
    def __init__(self):
        super().__init__()
        # ... layout setup ...
        self._populate()

    def _populate(self):
        # Clear
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        lang = get_language()

        # Resources
        try:
            content = fetch_md(RESOURCES_MD_URL, cache_name="resources.md")
            sections = parse_resource_md(content)
            for section in sections:
                header = QLabel(f"<b>━━ {section.title} ━━</b>")
                header.setStyleSheet("font-size: 14px; padding: 8px 4px 2px 4px; color: #000080;")
                self.items_layout.addWidget(header)
                for item in section.items:
                    # ... render item ...
                    pass
        except Exception as e:
            self.items_layout.addWidget(QLabel(f"Error loading resources: {e}"))

        # Education section linked to security findings
        self._load_education()
```

- [ ] **Step 4: Commit**

```bash
git add gui/pages/discover.py data/resources.md data/education.md
git commit -m "feat: dynamic Discover tab — resources + education from GitHub MD, Prometheus UA"
```

---

## Phase 8: SQLite Persistence + Trends

### Task 8: Activate SQLite for history

**Files:**
- Modify: `core/sqlite_db.py`
- Create: `core/history.py`
- Create: `tests/test_history.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_history.py
import asyncio
from pathlib import Path
from core.history import HistoryDB


def test_save_and_load_daily_stats():
    db = HistoryDB(":memory:")
    asyncio.run(db.init())
    asyncio.run(db.save_daily_stats(
        date="2026-04-14",
        tokens=500000,
        cost=2.50,
        cache_efficiency=85.0,
        sessions=5,
        security_score=90,
    ))
    stats = asyncio.run(db.get_daily_stats(days=7))
    assert len(stats) == 1
    assert stats[0]["tokens"] == 500000
    assert stats[0]["cost"] == 2.50


def test_weekly_trend():
    db = HistoryDB(":memory:")
    asyncio.run(db.init())
    for i in range(7):
        asyncio.run(db.save_daily_stats(
            date=f"2026-04-{8+i:02d}",
            tokens=100000 * (i + 1),
            cost=0.50 * (i + 1),
            cache_efficiency=70 + i * 3,
            sessions=3 + i,
            security_score=80,
        ))
    stats = asyncio.run(db.get_daily_stats(days=7))
    assert len(stats) == 7
```

- [ ] **Step 2: Implement history DB**

```python
# core/history.py
"""SQLite persistence for usage trends and history."""

from __future__ import annotations

import aiosqlite
from pathlib import Path
from core.platform import get_platform


class HistoryDB:
    def __init__(self, db_path: str | None = None):
        if db_path is None or db_path == ":memory:":
            self._path = db_path or ":memory:"
        else:
            self._path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self):
        data_dir = get_platform().data_dir() if self._path != ":memory:" else None
        if data_dir:
            data_dir.mkdir(parents=True, exist_ok=True)
            self._path = str(data_dir / "history.db")

        self._conn = await aiosqlite.connect(self._path)
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                tokens INTEGER,
                cost REAL,
                cache_efficiency REAL,
                sessions INTEGER,
                security_score INTEGER
            )
        """)
        await self._conn.commit()

    async def save_daily_stats(self, date: str, tokens: int, cost: float,
                                cache_efficiency: float, sessions: int,
                                security_score: int) -> None:
        await self._conn.execute("""
            INSERT OR REPLACE INTO daily_stats
            (date, tokens, cost, cache_efficiency, sessions, security_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (date, tokens, cost, cache_efficiency, sessions, security_score))
        await self._conn.commit()

    async def get_daily_stats(self, days: int = 30) -> list[dict]:
        cursor = await self._conn.execute("""
            SELECT date, tokens, cost, cache_efficiency, sessions, security_score
            FROM daily_stats
            ORDER BY date DESC
            LIMIT ?
        """, (days,))
        rows = await cursor.fetchall()
        return [
            {"date": r[0], "tokens": r[1], "cost": r[2],
             "cache_efficiency": r[3], "sessions": r[4], "security_score": r[5]}
            for r in rows
        ]

    async def close(self):
        if self._conn:
            await self._conn.close()
```

- [ ] **Step 3: Run tests, commit**

```bash
git add core/history.py tests/test_history.py
git commit -m "feat: SQLite history DB for daily usage stats and trends"
```

---

### Task 9: Trends widget on Analytics page

**Files:**
- Modify: `gui/pages/analytics.py`

- [ ] **Step 1: Add trends display**

In `gui/pages/analytics.py`, add a "Trends" group showing last 7 days:

```python
# Trends section
self.trends_group = QGroupBox("Weekly Trends")
tl = QVBoxLayout()

self.trend_labels: list[QLabel] = []
for _ in range(7):
    lbl = QLabel("")
    lbl.setStyleSheet("padding: 2px 4px; font-size: 11px; font-family: monospace;")
    tl.addWidget(lbl)
    self.trend_labels.append(lbl)

self.trend_summary = QLabel("")
self.trend_summary.setStyleSheet("padding: 4px; font-weight: bold;")
tl.addWidget(self.trend_summary)

self.trends_group.setLayout(tl)
layout.addWidget(self.trends_group)
```

Add update method:

```python
def update_trends(self, history: list[dict]) -> None:
    """Show last 7 days as text-based bar chart."""
    if not history:
        return

    max_tokens = max(h["tokens"] for h in history) or 1
    for i, h in enumerate(history[:7]):
        if i >= len(self.trend_labels):
            break
        bar_len = int(h["tokens"] / max_tokens * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        self.trend_labels[i].setText(
            f"{h['date'][-5:]}  {bar}  {h['tokens']/1000:.0f}K  ${h['cost']:.2f}"
        )

    # Summary
    if len(history) >= 2:
        today = history[0]["tokens"]
        yesterday = history[1]["tokens"]
        if yesterday > 0:
            change = (today - yesterday) / yesterday * 100
            arrow = "↑" if change > 0 else "↓"
            self.trend_summary.setText(
                f"{arrow} {abs(change):.0f}% vs yesterday | "
                f"Avg cache: {sum(h['cache_efficiency'] for h in history) / len(history):.0f}%"
            )
```

- [ ] **Step 2: Wire history DB into app.py refresh loop**

In `gui/app.py`, save stats to history at end of each refresh:

```python
# In _refresh_all, after Claude stats:
import asyncio
from core.history import HistoryDB
from datetime import date

# Save to history (once per day)
if not getattr(self, "_history_saved_today", False):
    async def save():
        db = HistoryDB()
        await db.init()
        await db.save_daily_stats(
            date=date.today().isoformat(),
            tokens=stats.total_billable,
            cost=cost.total_cost,
            cache_efficiency=cache_eff,
            sessions=len(stats.sessions),
            security_score=getattr(self, "_last_security_score", 100),
        )
        history = await db.get_daily_stats(7)
        await db.close()
        return history
    try:
        history = asyncio.run(save())
        self.page_analytics.update_trends(history)
        self._history_saved_today = True
    except Exception as e:
        log.error("History save error: %s", e)
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/analytics.py gui/app.py
git commit -m "feat: weekly trends on Analytics page — text bar chart from SQLite history"
```

---

### Task 10: Budget forecast

**Files:**
- Modify: `gui/pages/overview.py`

- [ ] **Step 1: Add forecast to Overview**

```python
def update_forecast(self, history: list[dict], current_billable: int) -> None:
    """Show budget forecast based on historical data."""
    if not history or len(history) < 2:
        return

    avg_daily = sum(h["tokens"] for h in history) / len(history)
    if avg_daily > 0:
        # Estimate when quota might run out (rough: 10M/day typical Max plan)
        rate_msg = f"Avg: {avg_daily/1000:.0f}K tok/day"
        if current_billable > avg_daily * 1.5:
            rate_msg += " | ⚠ Today is 50%+ above average"
        self.forecast_label.setText(rate_msg)
```

- [ ] **Step 2: Add forecast label to Overview layout**

```python
self.forecast_label = QLabel("")
self.forecast_label.setStyleSheet(
    "padding: 4px 8px; font-size: 11px; color: #666; font-style: italic;"
)
layout.addWidget(self.forecast_label)
```

- [ ] **Step 3: Commit**

```bash
git add gui/pages/overview.py
git commit -m "feat: budget forecast on Overview — daily average, above-average warning"
```

---

### Task 11: Final validation — all phases

- [ ] **Step 1: Run full test suite**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 2: Verify no hardcoded discover resources**

```bash
grep -r "DISCOVER_RESOURCES" --include="*.py" . | grep -v __pycache__
```
Expected: No results (replaced by MD fetcher)

- [ ] **Step 3: Verify curated.md and resources.md exist**

```bash
ls data/curated.md data/resources.md data/education.md
```
Expected: All three exist

- [ ] **Step 4: Verify tools.json removed (if no longer needed)**

```bash
ls tools.json 2>&1
```
Decision: Keep for backward compat or remove

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: Phase 5-8 complete — installer, Haiku AI, dynamic discover, persistence"
```
