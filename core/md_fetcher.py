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


def fetch_local_md(path: Path) -> str:
    """Read MD from local file."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _url_to_filename(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", url)[-80:] + ".md"


# --- Line format: - [Title](url) — description ---
_ITEM_RE = re.compile(r"^-\s+\[(.+?)\]\((.+?)\)\s*[—–\-]\s*(.*)$")


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
    """Parse education MD: ## Category -> ### lang -> items.

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
