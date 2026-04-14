"""Security scanners for dev environment."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Finding:
    type: str        # "docker", "config", "deps", "network"
    severity: str    # "critical", "high", "medium", "low"
    description: str
    source: str


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


def scan_file_permissions(scan_paths: list[Path]) -> list[Finding]:
    findings = []
    sensitive_patterns = [".env", "credentials", "secret", ".pem", ".key"]
    for path in scan_paths:
        if not path.is_dir():
            continue
        for pattern in sensitive_patterns:
            for f in path.rglob(f"*{pattern}*"):
                if not f.is_file():
                    continue
                try:
                    mode = f.stat().st_mode & 0o777
                    if mode & 0o077:
                        findings.append(Finding(
                            "config", "high",
                            f"Broad permissions ({oct(mode)}) on sensitive file: {f}",
                            str(f),
                        ))
                except OSError:
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
                import json
                try:
                    data = json.loads(result.stdout)
                    for vuln in data.get("dependencies", []):
                        for v in vuln.get("vulns", []):
                            severity = "critical" if "critical" in v.get("fix_versions", [""])[0].lower() else "high"
                            findings.append(Finding(
                                "deps", severity,
                                f"{vuln['name']}=={vuln['version']}: {v.get('id', 'CVE-?')} — {v.get('description', '')[:100]}",
                                str(req_file),
                            ))
                except (json.JSONDecodeError, KeyError):
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
                import json
                try:
                    data = json.loads(result.stdout)
                    vulns = data.get("vulnerabilities", {})
                    for name, info in vulns.items():
                        sev = info.get("severity", "moderate")
                        severity_map = {"critical": "critical", "high": "high", "moderate": "medium", "low": "low"}
                        findings.append(Finding(
                            "deps", severity_map.get(sev, "medium"),
                            f"npm: {name} — {sev} severity",
                            str(pkg_dir),
                        ))
                except (json.JSONDecodeError, KeyError):
                    pass
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    return findings
