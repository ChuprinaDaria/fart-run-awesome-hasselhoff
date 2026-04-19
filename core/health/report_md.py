"""Generate Markdown health report for Claude / AI agent consumption.

Produces a checklist-style .md file with:
- Actionable fixes grouped by priority
- Specific file:line references
- Context7 documentation snippets where available
- Known scanner limitations (possible false positives)
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core.health.models import HealthFinding, HealthReport


# Known false positive patterns — warn the user
_FP_WARNINGS: dict[str, str] = {
    "dead.unused_imports": (
        "Scanner may flag imports used only as type annotations in complex "
        "generics, or side-effect imports (e.g. model registration). "
        "Verify before deleting — check if the import is used in type hints, "
        "decorators, or has side effects on import."
    ),
    "dead.unused_definitions": (
        "Functions/methods called dynamically (getattr, signals, event handlers) "
        "or exposed as public API may be flagged. Also: celery tasks discovered "
        "by name, pytest fixtures in conftest.py, and Django/DRF auto-discovered "
        "methods. Verify the function isn't called via string name or framework magic."
    ),
    "map.modules": (
        "Orphan detection doesn't track dynamic imports (importlib, __import__), "
        "lazy imports inside functions, or framework auto-discovery (Django admin "
        "autodiscover, pytest conftest). If a file is loaded by framework convention "
        "— it's not really orphan."
    ),
    "debt.no_types": (
        "FastAPI/Flask endpoints with @router decorators get return types from "
        "the decorator (response_model=). Scanner skips these, but custom "
        "decorators may still trigger false alerts."
    ),
    "debt.no_reuse": (
        "Reusable pattern detection skips HTML/RN primitives, but custom design "
        "system components with className may be intentionally repeated "
        "(e.g. consistent spacing divs). Use judgment."
    ),
    "framework.django_secret_key": (
        "If SECRET_KEY is loaded via env (config(), env(), os.environ) with an "
        "insecure default — scanner flags as medium, not critical. The real fix "
        "is removing the default entirely so the app crashes without the env var."
    ),
}

_SEVERITY_EMOJI = {
    "critical": "🔴",
    "high": "🟠",
    "medium": "🟡",
    "low": "🔵",
    "warning": "🟡",
    "info": "ℹ️",
}

_SEVERITY_ORDER = ["critical", "high", "medium", "low", "warning", "info"]


def _group_findings(findings: list[HealthFinding]) -> dict[str, list[HealthFinding]]:
    """Group findings by severity, ordered by priority."""
    groups: dict[str, list[HealthFinding]] = {}
    for sev in _SEVERITY_ORDER:
        matched = [f for f in findings if f.severity == sev]
        if matched:
            groups[sev] = matched
    return groups


def _finding_to_checklist_item(f: HealthFinding) -> str:
    """Convert a finding to a markdown checklist item with fix info."""
    lines = [f"- [ ] **{f.title}**"]

    if f.message:
        # First sentence as description
        desc = f.message.split(". ")[0] + "."
        lines.append(f"  - {desc}")

    # File:line reference if available in title or message
    # Extract path from common patterns
    for field in [f.title, f.message]:
        if "/" in field and (":" in field or ".py" in field or ".tsx" in field):
            break

    # Context7 fix recommendation
    rec = f.details.get("fix_recommendation")
    if rec:
        source = f.details.get("context7_source", "docs")
        lines.append(f"  - **Fix ({source} docs):**")
        # Take first meaningful block (skip empty lines, limit to ~10 lines)
        rec_lines = [l for l in rec.split("\n") if l.strip()][:12]
        for rl in rec_lines:
            lines.append(f"    {rl}")

    return "\n".join(lines)


def _collect_fp_warnings(findings: list[HealthFinding]) -> list[str]:
    """Collect relevant FP warnings based on which check_ids appear."""
    seen_prefixes: set[str] = set()
    warnings = []
    for f in findings:
        for prefix, warning in _FP_WARNINGS.items():
            if f.check_id.startswith(prefix) or prefix in f.check_id:
                if prefix not in seen_prefixes:
                    seen_prefixes.add(prefix)
                    warnings.append(f"- **{prefix}**: {warning}")
    return warnings


def generate_report_md(report: HealthReport) -> str:
    """Generate a full Markdown health report."""
    project_name = Path(report.project_dir).name
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Filter out info-level findings for the checklist
    actionable = [f for f in report.findings if f.severity != "info"]
    grouped = _group_findings(actionable)

    # Severity counts
    counts = {}
    for f in report.findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1

    lines = []

    # Header
    lines.append(f"# Health Report: {project_name}")
    lines.append(f"")
    lines.append(f"Scanned: {now}")
    lines.append(f"Total findings: {len(report.findings)} "
                 f"(actionable: {len(actionable)})")
    lines.append("")

    # Summary bar
    summary_parts = []
    for sev in _SEVERITY_ORDER:
        if sev in counts:
            emoji = _SEVERITY_EMOJI.get(sev, "")
            summary_parts.append(f"{emoji} {sev}: {counts[sev]}")
    lines.append(" | ".join(summary_parts))
    lines.append("")

    # Project context
    if report.file_tree:
        total = report.file_tree.get("total_files", "?")
        lines.append(f"**Files:** {total}")
    if report.entry_points:
        ep_names = [ep.get("path", "?") for ep in report.entry_points[:3]]
        lines.append(f"**Entry points:** {', '.join(ep_names)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Checklist by severity
    for sev, findings in grouped.items():
        emoji = _SEVERITY_EMOJI.get(sev, "")
        lines.append(f"## {emoji} {sev.upper()} ({len(findings)})")
        lines.append("")
        for f in findings:
            lines.append(_finding_to_checklist_item(f))
            lines.append("")
        lines.append("")

    # False positive warnings
    fp_warnings = _collect_fp_warnings(report.findings)
    if fp_warnings:
        lines.append("---")
        lines.append("")
        lines.append("## ⚠️ Possible false positives")
        lines.append("")
        lines.append("The scanner uses static analysis and may flag valid code. "
                     "Check these before blindly fixing:")
        lines.append("")
        for w in fp_warnings:
            lines.append(w)
        lines.append("")

    # Info section (collapsed)
    info_findings = [f for f in report.findings if f.severity == "info"]
    if info_findings:
        lines.append("---")
        lines.append("")
        lines.append("<details>")
        lines.append(f"<summary>ℹ️ Info ({len(info_findings)} items)</summary>")
        lines.append("")
        for f in info_findings:
            lines.append(f"- **{f.title}**: {f.message[:150] if f.message else ''}")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Generated by [fartrun](https://github.com/ChuprinaDaria/fart-run-awesome-hasselhoff) health scanner*")

    return "\n".join(lines)


def save_report_md(report: HealthReport, output_path: str | None = None) -> str:
    """Generate and save MD report. Returns the file path."""
    md = generate_report_md(report)

    if output_path is None:
        project_name = Path(report.project_dir).name
        date = datetime.now().strftime("%Y-%m-%d")
        output_path = str(
            Path(report.project_dir) / f"HEALTH-REPORT-{date}.md"
        )

    Path(output_path).write_text(md, encoding="utf-8")
    return output_path
