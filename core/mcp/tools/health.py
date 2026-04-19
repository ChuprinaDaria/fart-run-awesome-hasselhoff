"""Health scan MCP tools — full project analysis for vibe coders."""
from __future__ import annotations

import mcp.types as mcp_types

from core.mcp.helpers import json_block, resolve_project_dir
from core.mcp.tools._registry import register


def _serialize_finding(f) -> dict:
    """Convert HealthFinding to dict for JSON output."""
    d = {
        "check_id": f.check_id,
        "severity": f.severity,
        "title": f.title,
        "message": f.message,
    }
    if f.details:
        # Include fix_recommendation from context7 if present
        if "fix_recommendation" in f.details:
            d["fix_recommendation"] = f.details["fix_recommendation"]
        if "context7_source" in f.details:
            d["context7_source"] = f.details["context7_source"]
    return d


def _serialize_report(report) -> dict:
    """Convert HealthReport to serializable dict."""
    findings = [_serialize_finding(f) for f in report.findings]

    # Group by severity for quick overview
    severity_counts = {}
    for f in report.findings:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

    return {
        "project_dir": report.project_dir,
        "total_findings": len(report.findings),
        "severity_counts": severity_counts,
        "file_tree": report.file_tree,
        "entry_points": report.entry_points[:5],
        "monsters": report.monsters[:10],
        "findings": findings,
    }


@register(mcp_types.Tool(
    name="run_health_scan",
    description=(
        "Full health scan of a project: file map, dead code, tech debt, "
        "git hygiene, test coverage, framework issues, and fix recommendations "
        "from Context7 docs. Returns all findings with severity levels. "
        "Use for comprehensive project audit."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project_dir": {
                "type": "string",
                "description": "Absolute path to project. Defaults to CWD.",
            },
        },
    },
))
async def run_health_scan(args):
    project_dir = resolve_project_dir(args.get("project_dir"))
    from core.health.project_map import run_all_checks
    report = run_all_checks(project_dir)
    return json_block(_serialize_report(report))


@register(mcp_types.Tool(
    name="get_health_summary",
    description=(
        "Quick health check — only critical and high severity issues. "
        "Faster than full scan, shows what needs fixing NOW. "
        "Includes fix recommendations from library docs when available."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project_dir": {
                "type": "string",
                "description": "Absolute path to project. Defaults to CWD.",
            },
            "include_medium": {
                "type": "boolean",
                "description": "Also include medium severity. Default false.",
            },
        },
    },
))
async def get_health_summary(args):
    project_dir = resolve_project_dir(args.get("project_dir"))
    include_medium = args.get("include_medium", False)

    from core.health.project_map import run_all_checks
    report = run_all_checks(project_dir)

    target = {"critical", "high"}
    if include_medium:
        target.add("medium")

    important = [f for f in report.findings if f.severity in target]
    findings = [_serialize_finding(f) for f in important]

    severity_counts = {}
    for f in important:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

    return json_block({
        "project_dir": project_dir,
        "total_findings": len(important),
        "total_all": len(report.findings),
        "severity_counts": severity_counts,
        "findings": findings,
    })


@register(mcp_types.Tool(
    name="get_unused_code",
    description=(
        "Find unused imports, functions, and dead code in a project. "
        "Returns only dead code findings — unused imports, unused "
        "functions/methods, orphan files, commented-out code."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project_dir": {
                "type": "string",
                "description": "Absolute path to project. Defaults to CWD.",
            },
        },
    },
))
async def get_unused_code(args):
    project_dir = resolve_project_dir(args.get("project_dir"))

    from core.health.project_map import run_all_checks
    report = run_all_checks(project_dir)

    dead_code_ids = {
        "dead.unused_imports", "dead.unused_definitions",
        "dead.orphan_files", "dead.commented_code", "dead.duplicates",
    }
    orphan_findings = [f for f in report.findings if "Orphan" in f.title]
    dead = [f for f in report.findings if f.check_id in dead_code_ids]
    dead.extend(orphan_findings)

    return json_block({
        "project_dir": project_dir,
        "unused_imports": [
            _serialize_finding(f) for f in dead
            if f.check_id == "dead.unused_imports"
        ],
        "unused_definitions": [
            _serialize_finding(f) for f in dead
            if f.check_id == "dead.unused_definitions"
        ],
        "orphan_files": [
            _serialize_finding(f) for f in dead
            if "Orphan" in f.title
        ],
        "duplicates": [
            _serialize_finding(f) for f in dead
            if f.check_id == "dead.duplicates"
        ],
        "commented_code": [
            _serialize_finding(f) for f in dead
            if f.check_id == "dead.commented_code"
        ],
        "total": len(dead),
    })


@register(mcp_types.Tool(
    name="get_tech_debt",
    description=(
        "Find tech debt: missing type hints, hardcoded values, "
        "TODO comments, error handling issues, outdated dependencies, "
        "overengineering. Returns only debt-related findings."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project_dir": {
                "type": "string",
                "description": "Absolute path to project. Defaults to CWD.",
            },
        },
    },
))
async def get_tech_debt(args):
    project_dir = resolve_project_dir(args.get("project_dir"))

    from core.health.project_map import run_all_checks
    report = run_all_checks(project_dir)

    debt_prefixes = ("debt.", "brake.overengineering")
    debt = [f for f in report.findings
            if any(f.check_id.startswith(p) for p in debt_prefixes)]

    return json_block({
        "project_dir": project_dir,
        "total": len(debt),
        "findings": [_serialize_finding(f) for f in debt],
    })


@register(mcp_types.Tool(
    name="get_security_issues",
    description=(
        "Find security issues: hardcoded secrets, insecure defaults, "
        "missing gitignore entries, framework misconfigurations. "
        "Returns only security-related findings."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "project_dir": {
                "type": "string",
                "description": "Absolute path to project. Defaults to CWD.",
            },
        },
    },
))
async def get_security_issues(args):
    project_dir = resolve_project_dir(args.get("project_dir"))

    from core.health.project_map import run_all_checks
    report = run_all_checks(project_dir)

    security_ids = {
        "framework.django_secret_key", "framework.django_debug",
        "framework.django_no_throttle",
        "git.gitignore",
    }
    security_prefixes = ("framework.",)
    security = [f for f in report.findings
                if f.check_id in security_ids
                or any(f.check_id.startswith(p) for p in security_prefixes)
                or f.severity == "critical"]

    return json_block({
        "project_dir": project_dir,
        "total": len(security),
        "findings": [_serialize_finding(f) for f in security],
    })
