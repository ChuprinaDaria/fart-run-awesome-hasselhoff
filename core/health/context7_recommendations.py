"""Phase 9 — Context7 fix recommendations.

After scanning, enrich critical/high findings with real documentation
snippets from Context7 MCP. Runs context7 as subprocess (stdio MCP),
queries library docs relevant to each finding, and appends
fix_recommendation to finding.details.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess

from core.health.models import HealthFinding, HealthReport
from core.stack_detector import detect_stack

log = logging.getLogger(__name__)

# Map check_id → [(library_name, query_topic)]
_FINDING_TO_QUERY: dict[str, list[tuple[str, str]]] = {
    "framework.django_secret_key": [
        ("Django", "SECRET_KEY configuration security best practices environment variable"),
    ],
    "framework.django_debug": [
        ("Django", "DEBUG setting production deployment security configuration"),
    ],
    "framework.django_no_throttle": [
        ("Django REST Framework", "throttling rate limiting DEFAULT_THROTTLE_CLASSES setup"),
    ],
    "framework.docker_no_lockfile": [
        ("Docker", "npm ci package-lock.json Dockerfile best practices reproducible builds"),
    ],
    "brake.tests": [
        ("pytest", "getting started writing first test basic example"),
    ],
}

# Only enrich critical/high by default
_ENRICH_SEVERITIES = {"critical", "high"}


def _npx_path() -> str | None:
    return shutil.which("npx")


def _run_context7_session(messages: list[dict], timeout: int = 30) -> list[dict]:
    """Send multiple JSON-RPC messages to context7 MCP via stdio."""
    npx = _npx_path()
    if not npx:
        return []

    # MCP protocol: initialize first, then tool calls
    init_msg = {
        "jsonrpc": "2.0", "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "fartrun-health", "version": "1.0"},
        },
    }
    all_messages = [init_msg] + messages
    stdin_text = "\n".join(json.dumps(m) for m in all_messages) + "\n"

    try:
        result = subprocess.run(
            [npx, "-y", "@upstash/context7-mcp"],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            log.debug("context7 process failed: %s", result.stderr[:200])
            return []

        responses = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                responses.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return responses
    except (subprocess.TimeoutExpired, OSError) as e:
        log.debug("context7 session error: %s", e)
        return []


def _resolve_and_query(library: str, topic: str) -> str | None:
    """Resolve library ID and fetch docs in a single context7 session."""
    # Step 1: resolve library ID
    resolve_msg = {
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {
            "name": "resolve-library-id",
            "arguments": {
                "libraryName": library,
                "query": topic,
            },
        },
    }
    responses = _run_context7_session([resolve_msg], timeout=20)

    # Find resolve response (id=1)
    library_id = None
    for resp in responses:
        if resp.get("id") == 1 and "result" in resp:
            result = resp["result"]
            # MCP tools/call returns {"content": [{"text": "..."}]}
            if isinstance(result, dict) and "content" in result:
                for item in result["content"]:
                    if isinstance(item, dict) and "text" in item:
                        text = item["text"]
                        # Parse the response to find library ID
                        # It typically contains lines like "/org/project"
                        for line in text.split("\n"):
                            line = line.strip()
                            if line.startswith("/") and "/" in line[1:]:
                                library_id = line.split()[0] if " " in line else line
                                break
                        if not library_id and "/" in text:
                            # Try to extract from text
                            for word in text.split():
                                if word.startswith("/") and word.count("/") >= 2:
                                    library_id = word.rstrip(".,;)")
                                    break
            break

    if not library_id:
        log.debug("context7: could not resolve library ID for %s", library)
        return None

    # Step 2: query docs with resolved ID
    query_msg = {
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {
            "name": "query-docs",
            "arguments": {
                "libraryId": library_id,
                "query": topic,
            },
        },
    }
    responses = _run_context7_session([query_msg], timeout=25)

    for resp in responses:
        if resp.get("id") == 2 and "result" in resp:
            result = resp["result"]
            if isinstance(result, dict) and "content" in result:
                texts = []
                for item in result["content"]:
                    if isinstance(item, dict) and "text" in item:
                        texts.append(item["text"])
                if texts:
                    return "\n".join(texts)
    return None


def enrich_findings_with_context7(
    report: HealthReport,
    project_dir: str,
    severities: set[str] | None = None,
) -> None:
    """Enrich report findings with context7 documentation recommendations."""
    target_severities = severities or _ENRICH_SEVERITIES

    if not _npx_path():
        log.debug("npx not available, skipping context7 enrichment")
        return

    # Detect project libraries
    stack = detect_stack(project_dir)
    project_libs = {lib.name.lower() for lib in stack}

    # Always-available libraries (not project-specific)
    universal_libs = {"python", "docker", "pytest", "django", "django rest framework"}

    enriched_count = 0
    for finding in report.findings:
        if finding.severity not in target_severities:
            continue

        queries = _FINDING_TO_QUERY.get(finding.check_id)
        if not queries:
            continue

        for lib_name, topic in queries:
            # Check if library is relevant to this project
            if lib_name.lower() not in project_libs and lib_name.lower() not in universal_libs:
                continue

            docs = _resolve_and_query(lib_name, topic)
            if not docs:
                continue

            # Trim to reasonable size
            snippet = docs[:800].strip()
            if len(docs) > 800:
                snippet += "\n..."

            finding.details["fix_recommendation"] = snippet
            finding.details["context7_source"] = lib_name
            enriched_count += 1
            break

    if enriched_count:
        log.info("context7: enriched %d findings with documentation", enriched_count)
