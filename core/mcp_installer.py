"""MCP Server and Skill installer — adds to ~/.claude/settings.json."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"

_ENV_VAR_RE = re.compile(r"`([A-Z][A-Z0-9_]{2,})`")

_COMMON_NON_ENV = {"README", "LICENSE", "INSTALL", "TODO", "NOTE", "IMPORTANT",
                   "HTTPS", "HTTP", "JSON", "YAML", "TOML", "HTML", "CSS"}


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
    env_vars = _ENV_VAR_RE.findall(readme_content)
    return [v for v in set(env_vars) if v not in _COMMON_NON_ENV and len(v) >= 4]


def read_settings() -> dict:
    """Read ~/.claude/settings.json."""
    if _CLAUDE_SETTINGS.exists():
        return json.loads(_CLAUDE_SETTINGS.read_text())
    return {}


def write_settings(settings: dict) -> None:
    """Write ~/.claude/settings.json atomically."""
    import tempfile
    _CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(settings, indent=2)
    # Write to temp file first, then atomic rename
    fd, tmp_path = tempfile.mkstemp(
        dir=str(_CLAUDE_SETTINGS.parent), suffix=".tmp", prefix=".settings_"
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp_path, str(_CLAUDE_SETTINGS))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
    """Clone skill repo into ~/.claude/skills/."""
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
        log.info("Installed skill: %s -> %s", git_url, dest)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        log.error("Failed to clone skill: %s", e)
        return False
