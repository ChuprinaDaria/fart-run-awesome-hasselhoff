"""Security scanners for dev environment and system.

Combines Python scanners (Docker, git, deps, system config) with
Rust-powered sentinel (processes, network, filesystem, cron) for
cross-platform host-based IDS at native speed.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

try:
    from orjson import loads as _json_loads
except ImportError:
    from json import loads as _json_loads

log = logging.getLogger(__name__)


@dataclass
class Finding:
    type: str        # "docker", "config", "deps", "network", "process", "filesystem", "cron", "system"
    severity: str    # "critical", "high", "medium", "low"
    description: str
    source: str


# ---------------------------------------------------------------------------
# Sentinel (Rust) scanners — fast, cross-platform
# ---------------------------------------------------------------------------

_sentinel_available = False
try:
    import sentinel
    _sentinel_available = True
except ImportError:
    log.warning("sentinel not installed — Rust scanners disabled. pip install sentinel")


def scan_sentinel_processes() -> list[Finding]:
    """Detect cryptominers, reverse shells, suspicious processes."""
    if not _sentinel_available:
        return []
    findings = []
    for pf in sentinel.scan_processes():
        findings.append(Finding("process", pf.severity, pf.description, f"pid:{pf.pid}"))
    return findings


def scan_sentinel_network() -> list[Finding]:
    """Detect suspicious ESTABLISHED connections (C2, Tor, IRC, mining pools)."""
    if not _sentinel_available:
        return []
    findings = []
    for nf in sentinel.scan_network():
        findings.append(Finding("network", nf.severity, nf.description, nf.remote_addr))
    return findings


def scan_sentinel_filesystem(scan_paths: list[Path]) -> list[Finding]:
    """Single-pass filesystem scan: permissions, malware paths, SUID, /tmp executables."""
    if not _sentinel_available:
        return []
    path_strs = [str(p) for p in scan_paths]
    findings = []
    for ff in sentinel.scan_filesystem(path_strs):
        findings.append(Finding("filesystem", ff.severity, ff.description, ff.path))
    return findings


def scan_sentinel_cron() -> list[Finding]:
    """Audit crontab, systemd timers, launchd, Task Scheduler for suspicious commands."""
    if not _sentinel_available:
        return []
    findings = []
    for cf in sentinel.scan_scheduled_tasks():
        findings.append(Finding("cron", cf.severity, cf.description, cf.source))
    return findings


def scan_sentinel_secrets(scan_paths: list[Path]) -> list[Finding]:
    """Detect hardcoded API keys, tokens, passwords in source files."""
    if not _sentinel_available:
        return []
    path_strs = [str(p) for p in scan_paths]
    findings = []
    for sf in sentinel.scan_secrets(path_strs):
        findings.append(Finding("secrets", sf.severity, sf.description, sf.path))
    return findings


def scan_sentinel_autostart() -> list[Finding]:
    """Detect malicious persistence in shell RC, systemd, XDG autostart."""
    if not _sentinel_available:
        return []
    findings = []
    for af in sentinel.scan_autostart():
        findings.append(Finding("autostart", af.severity, af.description, af.path))
    return findings


# ---------------------------------------------------------------------------
# Suspicious package scanner — typosquatting + known malicious
# ---------------------------------------------------------------------------

_POPULAR_PYTHON = [
    "requests", "django", "flask", "numpy", "pandas", "tensorflow", "pytorch",
    "boto3", "pillow", "cryptography", "paramiko", "sqlalchemy", "celery",
    "redis", "psycopg2", "aiohttp", "fastapi", "pydantic", "scrapy",
    "beautifulsoup4", "selenium", "matplotlib", "scipy", "scikit-learn",
    "httpx", "uvicorn", "gunicorn", "alembic", "black", "mypy", "pytest",
    "setuptools", "pip", "wheel", "docker", "kubernetes", "anthropic",
    "openai", "langchain", "transformers", "torch", "pyyaml", "jinja2",
    "click", "attrs", "marshmallow", "arrow", "pendulum", "rich",
    "typer", "loguru", "tenacity",
]

_POPULAR_NPM = [
    "react", "express", "lodash", "axios", "webpack", "next", "vue",
    "angular", "typescript", "eslint", "prettier", "jest", "mocha",
    "chalk", "commander", "dotenv", "cors", "mongoose", "sequelize",
    "prisma", "socket.io", "tailwindcss", "vite", "esbuild", "rollup",
    "postcss", "sass", "nodemon", "babel", "webpack-cli",
]

_KNOWN_MALICIOUS_PYTHON: set[str] = {
    "colourama", "python-binance", "python3-dateutil", "jeIlyfish",
    "python-mongo", "pymongodb", "requesocks", "requesrs", "python-ftp",
    "beautifulsup4", "djanga", "djnago", "numppy", "pandaas",
    "urlib3", "urllib", "flaskk",
}

_KNOWN_MALICIOUS_NPM: set[str] = {
    "crossenv", "cross-env.js", "d3.js", "fabric-js", "ffmepg",
    "gruntcli", "http-proxy.js", "jquery.js", "mariadb", "mongose",
    "mssql.js", "mssql-node", "mysqljs", "nodecaffe", "nodefabric",
    "nodeffmpeg", "nodemailer-js", "nodemssql", "node-openssl",
    "noderequest", "nodesass", "nodesqlite", "node-tkinter",
    "opencv.js", "openssl.js", "proxy.js", "shadowsock", "smb",
    "sqlite.js", "sqliter", "sqlserver",
}

_SUSPICIOUS_SCRIPT_PATTERNS = [
    "curl", "wget", "eval", "exec", "child_process",
    "http.get", "net.connect",
]


def _levenshtein(s1: str, s2: str) -> int:
    """Simple Levenshtein distance, no external deps."""
    if s1 == s2:
        return 0
    len1, len2 = len(s1), len(s2)
    if len1 == 0:
        return len2
    if len2 == 0:
        return len1
    prev = list(range(len2 + 1))
    for i, c1 in enumerate(s1, 1):
        curr = [i]
        for j, c2 in enumerate(s2, 1):
            cost = 0 if c1 == c2 else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[len2]


def _is_typosquat(name: str, popular: list[str]) -> bool:
    """Return True if name is suspiciously close to a popular package but not equal."""
    if len(name) <= 3:
        return False
    name_lower = name.lower()
    for pkg in popular:
        if name_lower == pkg.lower():
            return False
        if _levenshtein(name_lower, pkg.lower()) <= 2:
            return True
    return False


def scan_suspicious_packages(scan_paths: list[Path]) -> list[Finding]:
    """Scan for known malicious packages and typosquatting attempts."""
    findings = []

    for base_path in scan_paths:
        # --- requirements*.txt ---
        for req_file in base_path.rglob("requirements*.txt"):
            try:
                content = req_file.read_text(errors="replace")
            except OSError:
                continue
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # strip version specifiers: requests>=2.0,<3 → requests
                pkg_name = line.split("=")[0].split(">")[0].split("<")[0].split("[")[0].strip()
                if not pkg_name:
                    continue
                pkg_lower = pkg_name.lower()
                if pkg_lower in {m.lower() for m in _KNOWN_MALICIOUS_PYTHON}:
                    findings.append(Finding(
                        "packages", "critical",
                        f"Known malicious Python package: {pkg_name}",
                        str(req_file),
                    ))
                elif _is_typosquat(pkg_name, _POPULAR_PYTHON):
                    findings.append(Finding(
                        "packages", "high",
                        f"Possible typosquat of a popular Python package: {pkg_name}",
                        str(req_file),
                    ))

        # --- pyproject.toml ---
        for toml_file in base_path.rglob("pyproject.toml"):
            try:
                content = toml_file.read_text(errors="replace")
            except OSError:
                continue
            in_deps = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and "dependencies" in stripped.lower():
                    in_deps = True
                    continue
                if stripped.startswith("[") and in_deps:
                    in_deps = False
                if not in_deps or not stripped or stripped.startswith("#"):
                    continue
                # grab package name: 'requests = "^2.0"' or '"requests"'
                pkg_name = stripped.split("=")[0].strip().strip('"').strip("'")
                if not pkg_name or pkg_name.startswith("["):
                    continue
                pkg_lower = pkg_name.lower()
                if pkg_lower in {m.lower() for m in _KNOWN_MALICIOUS_PYTHON}:
                    findings.append(Finding(
                        "packages", "critical",
                        f"Known malicious Python package: {pkg_name}",
                        str(toml_file),
                    ))
                elif _is_typosquat(pkg_name, _POPULAR_PYTHON):
                    findings.append(Finding(
                        "packages", "high",
                        f"Possible typosquat of a popular Python package: {pkg_name}",
                        str(toml_file),
                    ))

        # --- package.json ---
        for pkg_file in base_path.rglob("package.json"):
            # skip node_modules
            if "node_modules" in pkg_file.parts:
                continue
            try:
                data = _json_loads(pkg_file.read_bytes())
            except (OSError, ValueError):
                continue

            # check lifecycle scripts for suspicious commands
            scripts = data.get("scripts", {})
            for script_name in ("postinstall", "preinstall", "prepare"):
                script_val = scripts.get(script_name, "")
                if not script_val:
                    continue
                for pattern in _SUSPICIOUS_SCRIPT_PATTERNS:
                    if pattern in script_val:
                        findings.append(Finding(
                            "packages", "critical",
                            f"Suspicious npm {script_name} script uses '{pattern}': {script_val[:120]}",
                            str(pkg_file),
                        ))
                        break  # one finding per script is enough

            # check dependency names
            all_deps: dict = {}
            all_deps.update(data.get("dependencies", {}))
            all_deps.update(data.get("devDependencies", {}))
            for pkg_name in all_deps:
                pkg_lower = pkg_name.lower()
                if pkg_lower in {m.lower() for m in _KNOWN_MALICIOUS_NPM}:
                    findings.append(Finding(
                        "packages", "critical",
                        f"Known malicious npm package: {pkg_name}",
                        str(pkg_file),
                    ))
                elif _is_typosquat(pkg_name, _POPULAR_NPM):
                    findings.append(Finding(
                        "packages", "high",
                        f"Possible typosquat of a popular npm package: {pkg_name}",
                        str(pkg_file),
                    ))

    return findings


# ---------------------------------------------------------------------------
# Python scanners — Docker, git, deps, system config
# ---------------------------------------------------------------------------

def scan_docker_security(container_infos: list[dict]) -> list[Finding]:
    findings = []
    for c in container_infos:
        name = c["name"]

        if c.get("privileged"):
            findings.append(Finding("docker", "critical", f"{name}: runs in privileged mode", name))

        for bind in c.get("binds") or []:
            if "docker.sock" in bind:
                findings.append(Finding("docker", "critical", f"{name}: docker.sock mounted inside container", name))

        if c.get("network_mode") == "host":
            findings.append(Finding("docker", "high", f"{name}: uses host network mode", name))

        if not c.get("user"):
            findings.append(Finding("docker", "high", f"{name}: runs as root (no USER set)", name))

        image = c.get("image", "")
        if image.endswith(":latest") or ":" not in image:
            findings.append(Finding("docker", "medium", f"{name}: uses :latest tag ({image})", name))

    return findings


def scan_env_in_git(scan_paths: list[Path]) -> list[Finding]:
    findings = []
    for path in scan_paths:
        if not (path / ".git").exists():
            continue
        try:
            result = subprocess.run(
                ["git", "-C", str(path), "ls-files"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                continue
            for tracked_file in result.stdout.strip().split("\n"):
                tracked_file = tracked_file.strip()
                if not tracked_file:
                    continue
                name = Path(tracked_file).name
                if name.startswith(".env"):
                    findings.append(Finding(
                        "config", "critical",
                        f".env file committed in git: {tracked_file}",
                        str(path / tracked_file),
                    ))
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue
    return findings


def scan_exposed_ports(ports: list[dict]) -> list[Finding]:
    findings = []
    for p in ports:
        if p["ip"] == "0.0.0.0":
            findings.append(Finding(
                "network", "high",
                f"Port {p['port']} ({p['process']}) exposed on 0.0.0.0 instead of 127.0.0.1",
                f"port:{p['port']}",
            ))
    return findings


def scan_pip_audit(scan_paths: list[Path]) -> list[Finding]:
    findings = []
    for path in scan_paths:
        for req_file in path.rglob("requirements*.txt"):
            try:
                result = subprocess.run(
                    ["pip-audit", "-r", str(req_file), "--format", "json", "--progress-spinner", "off"],
                    capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    continue
                try:
                    data = _json_loads(result.stdout)
                    for vuln in data.get("dependencies", []):
                        for v in vuln.get("vulns", []):
                            severity = "critical" if "critical" in v.get("fix_versions", [""])[0].lower() else "high"
                            findings.append(Finding(
                                "deps", severity,
                                f"{vuln['name']}=={vuln['version']}: {v.get('id', 'CVE-?')} — {v.get('description', '')[:100]}",
                                str(req_file),
                            ))
                except (ValueError, KeyError):
                    pass
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    return findings


def scan_npm_audit(scan_paths: list[Path]) -> list[Finding]:
    findings = []
    for path in scan_paths:
        for pkg_file in path.rglob("package.json"):
            pkg_dir = pkg_file.parent
            if not (pkg_dir / "node_modules").exists():
                continue
            try:
                result = subprocess.run(
                    ["npm", "audit", "--json"],
                    capture_output=True, text=True, timeout=60, cwd=str(pkg_dir),
                )
                try:
                    data = _json_loads(result.stdout)
                    vulns = data.get("vulnerabilities", {})
                    for name, info in vulns.items():
                        sev = info.get("severity", "moderate")
                        severity_map = {"critical": "critical", "high": "high", "moderate": "medium", "low": "low"}
                        findings.append(Finding(
                            "deps", severity_map.get(sev, "medium"),
                            f"npm: {name} — {sev} severity",
                            str(pkg_dir),
                        ))
                except (ValueError, KeyError):
                    pass
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    return findings


# ---------------------------------------------------------------------------
# System-level scanners — cross-platform via platform backend
# ---------------------------------------------------------------------------

from core.platform import get_platform


def scan_firewall() -> list[Finding]:
    """Check if firewall is active — cross-platform."""
    platform = get_platform()
    result = platform.check_firewall()
    findings = []
    if not result["active"]:
        tool = result["tool"]
        details = result["details"]
        if tool == "none":
            findings.append(Finding(
                "system", "high",
                "No firewall detected — system is open to network attacks",
                "firewall",
            ))
        else:
            findings.append(Finding(
                "system", "high",
                f"Firewall ({tool}) is inactive — {details}",
                tool,
            ))
    return findings


def scan_ssh_config() -> list[Finding]:
    """Check SSH server configuration — cross-platform."""
    platform = get_platform()
    result = platform.check_ssh_config()
    findings = []
    if not result["exists"]:
        return findings
    for issue in result["issues"]:
        severity = "critical" if "empty passwords" in issue else (
            "high" if "root login" in issue else "medium"
        )
        findings.append(Finding("system", severity, f"SSH: {issue}", "sshd_config"))
    return findings


def scan_system_updates() -> list[Finding]:
    """Check for available security updates — cross-platform."""
    platform = get_platform()
    updates = platform.check_system_updates()
    findings = []
    for desc in updates:
        severity = "high" if "security" in desc.lower() else "medium"
        findings.append(Finding(
            "system", severity,
            f"{desc} — update your system",
            "updates",
        ))
    return findings


def scan_sudoers() -> list[Finding]:
    """Check for risky admin configurations — cross-platform."""
    platform = get_platform()
    result = platform.check_sudoers()
    findings = []
    if result["nopasswd_all"]:
        findings.append(Finding(
            "system", "medium",
            "Current user has passwordless admin access for ALL commands",
            "sudoers",
        ))
    return findings


def scan_world_writable() -> list[Finding]:
    """Check for world-writable directories in PATH."""
    findings = []
    sep = ";" if os.name == "nt" else ":"
    path_dirs = os.environ.get("PATH", "").split(sep)
    for d in path_dirs:
        p = Path(d)
        if not p.exists():
            continue
        try:
            mode = p.stat().st_mode & 0o777
            if mode & 0o002:
                findings.append(Finding(
                    "system", "high",
                    f"PATH directory {d} is world-writable ({oct(mode)}) — "
                    "attacker can place malicious binaries there",
                    str(p),
                ))
        except OSError:
            continue
    return findings
