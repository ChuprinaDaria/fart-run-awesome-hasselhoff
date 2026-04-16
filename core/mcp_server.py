"""Fartrun MCP server — exposes every major GUI feature as an MCP tool.

Destructive operations (rollback, delete save points, uninstall hooks)
require an explicit ``confirm=True`` argument. Without confirmation they
return a human-readable explanation of what WILL happen, so the calling
agent has to explicitly ask the user before firing it off.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import mcp.types as mcp_types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from core.history import HistoryDB
from core.prompt_parser import get_recent_prompts
from core.activity_tracker import ActivityTracker, serialize_activity
from core.prompt_builder import build_prompt
from core.code_searcher import search_codebase
from core.stack_detector import detect_stack, docs_worthy
from core import context7_mcp as c7
from core import frozen_manager as fm

log = logging.getLogger("fartrun.mcp")

server = Server("fartrun")


# ------------------------------------------------------------ helpers

def _resolve_project_dir(project_dir: str | None) -> str:
    """If ``None``/empty, fall back to CWD — how agents will mostly invoke us."""
    if project_dir:
        return str(Path(project_dir).expanduser().resolve())
    return str(Path.cwd())


def _db() -> HistoryDB:
    db = HistoryDB()
    db.init()
    return db


def _ok(text: str) -> list[mcp_types.TextContent]:
    return [mcp_types.TextContent(type="text", text=text)]


def _err(text: str) -> list[mcp_types.TextContent]:
    return [mcp_types.TextContent(type="text", text=f"[fartrun error] {text}")]


def _json_block(data: Any) -> list[mcp_types.TextContent]:
    return [mcp_types.TextContent(
        type="text", text=json.dumps(data, indent=2, ensure_ascii=False),
    )]


# ------------------------------------------------------------ tool list

@server.list_tools()
async def list_tools() -> list[mcp_types.Tool]:
    return [
        mcp_types.Tool(
            name="get_status",
            description=(
                "Quick overview of a project: count of save points, frozen "
                "files, recent user prompts, detected stack. READ-ONLY."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {
                        "type": "string",
                        "description": "Absolute path. Defaults to CWD.",
                    },
                },
            },
        ),
        mcp_types.Tool(
            name="list_save_points",
            description="List Save Points for a project. READ-ONLY.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        mcp_types.Tool(
            name="list_frozen",
            description=(
                "List frozen (Don't Touch) files for a project. READ-ONLY."
            ),
            inputSchema={
                "type": "object",
                "properties": {"project_dir": {"type": "string"}},
            },
        ),
        mcp_types.Tool(
            name="list_prompts",
            description=(
                "Return the last N real user prompts this project received "
                "in Claude Code (tool results are filtered out). READ-ONLY."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
            },
        ),
        mcp_types.Tool(
            name="get_activity",
            description=(
                "Current uncommitted changes, recent commits, Docker/port "
                "diffs. READ-ONLY."
            ),
            inputSchema={
                "type": "object",
                "properties": {"project_dir": {"type": "string"}},
            },
        ),
        mcp_types.Tool(
            name="detect_project_stack",
            description=(
                "Parse manifests and return detected libraries with versions. "
                "READ-ONLY."
            ),
            inputSchema={
                "type": "object",
                "properties": {"project_dir": {"type": "string"}},
            },
        ),
        mcp_types.Tool(
            name="search_code",
            description=(
                "Run a grep-style keyword search across the project. "
                "READ-ONLY."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "max_per_keyword": {"type": "integer", "default": 5},
                },
                "required": ["keywords"],
            },
        ),
        mcp_types.Tool(
            name="build_prompt",
            description=(
                "Turn a vibe-coder's one-liner into a full structured prompt "
                "with concrete file:line hits, stack, frozen list, and a "
                "Context7 directive. READ-ONLY (uses Haiku if configured)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "text": {
                        "type": "string",
                        "description": "What the user wants, in any language",
                    },
                },
                "required": ["text"],
            },
        ),
        mcp_types.Tool(
            name="freeze_file",
            description=(
                "Lock a file so it gets listed in CLAUDE.md's DO NOT TOUCH "
                "section. WRITE, non-destructive."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "path": {"type": "string"},
                    "note": {"type": "string", "default": ""},
                },
                "required": ["path"],
            },
        ),
        mcp_types.Tool(
            name="unfreeze_file",
            description=(
                "Remove a file from the Don't Touch list. WRITE, reversible."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["path"],
            },
        ),
        mcp_types.Tool(
            name="install_context7",
            description=(
                "Add Context7 MCP to ~/.claude/settings.json (idempotent). "
                "WRITE, reversible via uninstall_context7."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        mcp_types.Tool(
            name="uninstall_context7",
            description=(
                "Remove Context7 MCP from ~/.claude/settings.json. "
                "WRITE, reversible."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        mcp_types.Tool(
            name="rollback_save_point",
            description=(
                "DESTRUCTIVE. Hard-reset the working tree to a save point. "
                "Creates a backup branch with your current work. Pass "
                "confirm=True to actually perform the rollback — without it "
                "we only explain the consequences."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "save_point_id": {"type": "integer"},
                    "keep_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": ("Paths to re-apply from the current "
                                         "state after rollback."),
                    },
                    "confirm": {"type": "boolean", "default": False},
                },
                "required": ["save_point_id"],
            },
        ),
        mcp_types.Tool(
            name="create_save_point",
            description=(
                "Make a new git-based Save Point. Commits all uncommitted "
                "changes under a tag. WRITE, reversible (rollback gives you "
                "back the prior state)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string"},
                    "label": {"type": "string"},
                },
                "required": ["label"],
            },
        ),
    ]


# ------------------------------------------------------------ dispatcher

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    try:
        if name == "get_status":
            return await _get_status(arguments)
        if name == "list_save_points":
            return await _list_save_points(arguments)
        if name == "list_frozen":
            return await _list_frozen(arguments)
        if name == "list_prompts":
            return await _list_prompts(arguments)
        if name == "get_activity":
            return await _get_activity(arguments)
        if name == "detect_project_stack":
            return await _detect_stack(arguments)
        if name == "search_code":
            return await _search_code(arguments)
        if name == "build_prompt":
            return await _build_prompt(arguments)
        if name == "freeze_file":
            return await _freeze_file(arguments)
        if name == "unfreeze_file":
            return await _unfreeze_file(arguments)
        if name == "install_context7":
            return await _install_context7(arguments)
        if name == "uninstall_context7":
            return await _uninstall_context7(arguments)
        if name == "rollback_save_point":
            return await _rollback(arguments)
        if name == "create_save_point":
            return await _create_save_point(arguments)
        return _err(f"Unknown tool: {name}")
    except Exception as e:
        log.exception("tool %s failed", name)
        return _err(f"{type(e).__name__}: {e}")


# ------------------------------------------------------------ tool impls

async def _get_status(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    db = _db()
    save_points = db.get_save_points(project_dir, limit=5)
    frozen = db.get_frozen_files(project_dir)
    prompts = get_recent_prompts(project_dir, limit=3)
    stack = detect_stack(project_dir)
    worthy = docs_worthy(stack)

    data = {
        "project_dir": project_dir,
        "save_points": {
            "count": len(save_points),
            "latest": save_points[0]["label"] if save_points else None,
        },
        "frozen_files": {
            "count": len(frozen),
            "paths": [f["path"] for f in frozen[:10]],
        },
        "recent_prompts": [
            {"when": p.timestamp[:16], "text": p.short} for p in prompts
        ],
        "stack": {
            "total": len(stack),
            "docs_worthy": [lib.name for lib in worthy],
        },
        "context7_installed": c7.is_context7_installed(),
        "frozen_hook_installed": fm.is_hook_installed(),
    }
    return _json_block(data)


async def _list_save_points(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    limit = int(args.get("limit") or 20)
    points = _db().get_save_points(project_dir, limit=limit)
    return _json_block(points)


async def _list_frozen(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    return _json_block(_db().get_frozen_files(project_dir))


async def _list_prompts(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    limit = int(args.get("limit") or 10)
    prompts = get_recent_prompts(project_dir, limit=limit)
    return _json_block([
        {
            "timestamp": p.timestamp,
            "session_id": p.session_id,
            "text": p.text,
        } for p in prompts
    ])


async def _get_activity(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    tracker = ActivityTracker(project_dir)
    entry = tracker.collect_activity()
    return _ok(serialize_activity(entry))


async def _detect_stack(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    stack = detect_stack(project_dir)
    return _json_block([
        {"name": l.name, "version": l.version, "ecosystem": l.ecosystem}
        for l in stack
    ])


async def _search_code(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    keywords = args.get("keywords") or []
    max_per = int(args.get("max_per_keyword") or 5)
    matches = search_codebase(project_dir, keywords, max_per_keyword=max_per)
    return _json_block([
        {"path": m.path, "line": m.line_number,
         "snippet": m.snippet, "keyword": m.keyword}
        for m in matches
    ])


async def _build_prompt(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    text = args.get("text") or ""
    if not text.strip():
        return _err("text is required")

    haiku = None
    try:
        from core.haiku_client import HaikuClient
        client = HaikuClient()
        if client.is_available():
            haiku = client
    except Exception:
        pass

    frozen = [f["path"] for f in _db().get_frozen_files(project_dir)]
    result = build_prompt(
        user_text=text, project_dir=project_dir,
        frozen_paths=frozen, haiku_client=haiku,
    )
    return _ok(result.final_prompt)


async def _freeze_file(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    path = args.get("path") or ""
    note = args.get("note") or ""
    if not path:
        return _err("path is required")
    _db().add_frozen_file(project_dir, path, note)
    frozen = [f["path"] for f in _db().get_frozen_files(project_dir)]
    fm.sync_claude_md(project_dir, frozen)
    return _ok(f"Frozen '{path}'. CLAUDE.md updated. "
                f"Total frozen: {len(frozen)}.")


async def _unfreeze_file(args) -> list[mcp_types.TextContent]:
    project_dir = _resolve_project_dir(args.get("project_dir"))
    path = args.get("path") or ""
    if not path:
        return _err("path is required")
    _db().remove_frozen_file(project_dir, path)
    frozen = [f["path"] for f in _db().get_frozen_files(project_dir)]
    fm.sync_claude_md(project_dir, frozen)
    return _ok(f"Unfrozen '{path}'. Total frozen: {len(frozen)}.")


async def _install_context7(args) -> list[mcp_types.TextContent]:
    changed = c7.install_context7()
    if changed:
        return _ok("Context7 MCP added to ~/.claude/settings.json. "
                    "Restart Claude Code to pick it up.")
    return _ok("Context7 is already installed.")


async def _uninstall_context7(args) -> list[mcp_types.TextContent]:
    changed = c7.uninstall_context7()
    return _ok("Context7 removed." if changed
                else "Context7 was not installed.")


async def _create_save_point(args) -> list[mcp_types.TextContent]:
    from core.safety_net import SafetyNet

    project_dir = _resolve_project_dir(args.get("project_dir"))
    label = args.get("label") or ""
    if not label:
        return _err("label is required")

    sn = SafetyNet(project_dir, _db())
    can, reason = sn.can_save()
    if not can:
        return _err(f"Can't save: {reason}")
    result = sn.create_save_point(label)
    return _ok(
        f"Save Point #{result.id} created.\n"
        f"  commit: {result.commit_hash[:8]}\n"
        f"  files: {result.file_count}, lines: {result.lines_total}"
    )


async def _rollback(args) -> list[mcp_types.TextContent]:
    from core.safety_net import SafetyNet

    project_dir = _resolve_project_dir(args.get("project_dir"))
    save_point_id = args.get("save_point_id")
    confirm = bool(args.get("confirm", False))
    keep_paths = list(args.get("keep_paths") or [])

    if save_point_id is None:
        return _err("save_point_id is required")

    sn = SafetyNet(project_dir, _db())
    can, reason = sn.can_rollback(int(save_point_id))
    if not can:
        return _err(f"Can't rollback: {reason}")

    preview = sn.rollback_preview(int(save_point_id))
    if not preview:
        return _err("Save point not found")

    if not confirm:
        changes = sn.get_changes_since(int(save_point_id))
        changed_names = ", ".join(c.path for c in changes[:8])
        if len(changes) > 8:
            changed_names += f", ... +{len(changes) - 8} more"
        return _ok(
            "[DESTRUCTIVE PREVIEW — not executed]\n"
            f"Rolling back to Save Point #{save_point_id} "
            f"(\"{preview.target_label}\") will:\n"
            f"  1. Reset the working tree to commit "
            f"{preview.target_commit[:8]}.\n"
            f"  2. Save your current {len(changes)} changed file(s) to a new "
            f"backup branch so nothing is lost.\n"
            f"  3. Optionally re-apply files listed in `keep_paths` from the "
            f"backup onto the rolled-back state.\n\n"
            f"Changed files that would be affected:\n  {changed_names}\n\n"
            f"To actually do it, call again with confirm=true."
        )

    result = sn.rollback_with_picks(int(save_point_id), keep_paths)
    return _ok(
        f"Rolled back to Save Point #{save_point_id}.\n"
        f"  backup branch: {result.backup_branch}\n"
        f"  files restored: {result.files_restored}\n"
        f"  kept after rollback: {len(keep_paths)}"
    )


# ------------------------------------------------------------ entrypoint

async def _run() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write,
                          server.create_initialization_options())


def main() -> None:
    """Run stdio MCP server. Used by `fartrun mcp` and Claude Code."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
