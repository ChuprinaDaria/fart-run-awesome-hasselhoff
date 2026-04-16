"""MCP server entrypoint — Server instance, dispatchers, lifecycle."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import mcp.types as mcp_types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# Import tools package for side-effect: every submodule @registers on import.
from core.mcp import tools as _tools  # noqa: F401
from core.mcp.helpers import err
from core.mcp.state import db
from core.mcp.tools._registry import TOOL_DEFS, TOOL_HANDLERS

log = logging.getLogger("fartrun.mcp")

server = Server("fartrun")


@server.list_tools()
async def list_tools() -> list[mcp_types.Tool]:
    # Defensive copy: callers shouldn't mutate the registry.
    return list(TOOL_DEFS)


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[mcp_types.TextContent]:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return err(f"Unknown tool: {name}")
    try:
        return await handler(arguments)
    except Exception as e:
        log.exception("tool %s failed", name)
        return err(f"{type(e).__name__}: {e}")


def _log_startup() -> None:
    """Best-effort startup banner to stderr — Claude Code captures it
    so when the server fails to load the user can actually see why."""
    try:
        try:
            import tomllib
            pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
            with open(pyproject, "rb") as f:
                version = tomllib.load(f).get("project", {}).get("version", "?")
        except Exception:
            version = "?"
        d = db()
        log.info(
            "fartrun MCP server starting (v%s, db=%s, tools=%d)",
            version, d.path, len(TOOL_DEFS),
        )
    except Exception as e:
        log.warning("startup banner failed: %s", e)


async def _run() -> None:
    _log_startup()
    async with stdio_server() as (read, write):
        await server.run(read, write,
                         server.create_initialization_options())


def main() -> None:
    """Run stdio MCP server. Used by `fartrun mcp` and Claude Code."""
    # stdout is reserved for JSON-RPC; diagnostics go to stderr.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    )
    asyncio.run(_run())
