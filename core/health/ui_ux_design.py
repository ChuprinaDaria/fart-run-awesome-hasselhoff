"""Phase 7 — UI/UX Design Quality scanning.

Wraps external CLI tools via npx (auto-downloads on first run):
  - impeccable  → AI slop detection + design quality
  - stylelint   → CSS linting (170+ rules)
  - lighthouse  → accessibility + performance + SEO
  - pa11y       → WCAG compliance

Only requirement: Node.js installed (npx comes with it).
If the project has frontend files, Node.js is almost certainly already there.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from core.health.models import HealthFinding, HealthReport
from core.health import tips

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_npx() -> bool:
    return shutil.which("npx") is not None


def _run_json(cmd: list[str], cwd: str, timeout: int = 120) -> dict | list | None:
    """Run a command, parse JSON stdout. Returns None on any failure."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )
        if result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
        log.debug("ui_ux tool %s failed: %s", cmd[0], e)
    return None


def _has_frontend_files(project_dir: str) -> bool:
    """Quick check: does this project have CSS/HTML/JSX/TSX files?"""
    root = Path(project_dir)
    for ext in ("*.css", "*.scss", "*.html", "*.jsx", "*.tsx", "*.vue", "*.svelte"):
        if any(root.rglob(ext)):
            return True
    return False


def _no_node_finding(check_id: str) -> HealthFinding:
    """Common finding when Node.js/npx is not installed."""
    return HealthFinding(
        check_id=check_id,
        title="Node.js not found",
        severity="low",
        message=tips.tip_install_node(),
    )


# ---------------------------------------------------------------------------
# Scanner: impeccable (AI slop detection)
# ---------------------------------------------------------------------------

def _scan_impeccable(project_dir: str) -> list[HealthFinding]:
    """Run npx impeccable detect — auto-downloads on first run."""
    if not _has_npx():
        return [_no_node_finding("uiux.impeccable")]

    # npx auto-downloads impeccable if not cached yet
    data = _run_json(
        ["npx", "--yes", "impeccable", "detect", "--fast", "--json", "."],
        cwd=project_dir, timeout=120,
    )
    if not data:
        return []

    findings: list[HealthFinding] = []
    issues = data if isinstance(data, list) else data.get("issues", data.get("results", []))

    for issue in issues:
        if isinstance(issue, dict):
            category = issue.get("category", "design")
            rule = issue.get("rule", issue.get("id", "unknown"))
            message = issue.get("message", issue.get("description", str(issue)))
            file_path = issue.get("file", issue.get("path", ""))
            line = issue.get("line", "")

            is_slop = "slop" in category.lower() or "slop" in rule.lower()
            severity = "medium" if is_slop else "low"

            title_prefix = "AI Slop" if is_slop else "Design Quality"
            location = f"{file_path}:{line}" if file_path and line else file_path

            findings.append(HealthFinding(
                check_id="uiux.impeccable",
                title=f"{title_prefix}: {rule}" + (f" ({location})" if location else ""),
                severity=severity,
                message=tips.tip_impeccable(rule, message, is_slop),
                details=issue,
            ))

    if not issues and data:
        findings.append(HealthFinding(
            check_id="uiux.impeccable",
            title="AI Slop Check",
            severity="info",
            message="No AI slop patterns detected. Your design doesn't look like every other AI-generated site.",
        ))

    return findings


# ---------------------------------------------------------------------------
# Scanner: stylelint (CSS quality)
# ---------------------------------------------------------------------------

def _scan_stylelint(project_dir: str) -> list[HealthFinding]:
    """Run npx stylelint — auto-downloads on first run."""
    if not _has_npx():
        return [_no_node_finding("uiux.stylelint")]

    root = Path(project_dir)
    css_files = list(root.rglob("*.css")) + list(root.rglob("*.scss"))
    if not css_files:
        return []

    data = _run_json(
        ["npx", "--yes", "stylelint", "**/*.css", "**/*.scss",
         "--formatter", "json", "--allow-empty-input"],
        cwd=project_dir, timeout=60,
    )
    if not data:
        return []

    findings: list[HealthFinding] = []
    results = data if isinstance(data, list) else []

    error_count = 0
    warning_count = 0
    sample_issues: list[dict] = []

    for file_result in results:
        if not isinstance(file_result, dict):
            continue
        file_path = file_result.get("source", "")
        for warning in file_result.get("warnings", []):
            sev = warning.get("severity", "warning")
            if sev == "error":
                error_count += 1
            else:
                warning_count += 1
            if len(sample_issues) < 5:
                sample_issues.append({
                    "file": file_path,
                    "line": warning.get("line", ""),
                    "rule": warning.get("rule", ""),
                    "text": warning.get("text", ""),
                })

    if error_count + warning_count == 0:
        findings.append(HealthFinding(
            check_id="uiux.stylelint",
            title="CSS Quality",
            severity="info",
            message="CSS is clean — no stylelint issues found.",
        ))
        return findings

    severity = "medium" if error_count > 0 else "low"
    findings.append(HealthFinding(
        check_id="uiux.stylelint",
        title=f"CSS Quality: {error_count} errors, {warning_count} warnings",
        severity=severity,
        message=tips.tip_stylelint(error_count, warning_count),
        details={"errors": error_count, "warnings": warning_count},
    ))

    for issue in sample_issues:
        try:
            rel = str(Path(issue["file"]).relative_to(root))
        except ValueError:
            rel = issue["file"]
        findings.append(HealthFinding(
            check_id="uiux.stylelint",
            title=f"CSS: {issue['rule']} ({rel}:{issue['line']})",
            severity="low",
            message=issue["text"],
            details=issue,
        ))

    return findings


# ---------------------------------------------------------------------------
# Scanner: lighthouse (accessibility + performance)
# ---------------------------------------------------------------------------

def _scan_lighthouse(project_dir: str) -> list[HealthFinding]:
    """Lighthouse needs a running dev server — hint to run manually."""
    if not _has_npx():
        return [_no_node_finding("uiux.lighthouse")]

    pkg_json = Path(project_dir) / "package.json"
    if not pkg_json.exists():
        return []

    return [HealthFinding(
        check_id="uiux.lighthouse",
        title="Lighthouse — run manually",
        severity="info",
        message=tips.tip_lighthouse_available(),
        details={"hint": "npx lighthouse http://localhost:3000 --output=json"},
    )]


# ---------------------------------------------------------------------------
# Scanner: pa11y (WCAG accessibility)
# ---------------------------------------------------------------------------

def _scan_pa11y(project_dir: str) -> list[HealthFinding]:
    """pa11y needs a running dev server — hint to run manually."""
    if not _has_npx():
        return [_no_node_finding("uiux.pa11y")]

    pkg_json = Path(project_dir) / "package.json"
    if not pkg_json.exists():
        return []

    return [HealthFinding(
        check_id="uiux.pa11y",
        title="pa11y — run manually",
        severity="info",
        message=tips.tip_pa11y_available(),
        details={"hint": "npx pa11y http://localhost:3000 --reporter json"},
    )]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_ui_ux_checks(report: HealthReport, project_dir: str) -> None:
    """Phase 7 — UI/UX Design Quality checks."""
    if not _has_frontend_files(project_dir):
        log.debug("No frontend files found, skipping UI/UX checks")
        return

    for scanner in (_scan_impeccable, _scan_stylelint, _scan_lighthouse, _scan_pa11y):
        try:
            report.findings.extend(scanner(project_dir))
        except Exception as e:
            log.error("%s scan error: %s", scanner.__name__, e)
