"""Tip generation for health check results."""

from __future__ import annotations


def tip_file_tree(total_files: int, top_ext: str, top_count: int) -> str:
    return (
        f"In your project: {total_files} files. "
        f"Most common: .{top_ext} ({top_count}). "
        f"This is just context — now you know what's inside."
    )


def tip_entry_points(count: int) -> str:
    if count == 0:
        return (
            "No entry points found. "
            "An entry point is where your app starts — like a front door. "
            "Usually main.py, index.js, or a package.json script."
        )
    return (
        f"Entry point = the file where everything starts. Like doors to a building. "
        f"You have {count}."
    )


def tip_hub_module(path: str, count: int) -> str:
    return (
        f"{path} is imported by {count} files. "
        f"This is your most important module. Break it — break everything."
    )


def tip_circular(a: str, b: str) -> str:
    return (
        f"{a} imports {b}, and {b} imports {a}. "
        f"A circular dependency — can break during refactoring."
    )


def tip_orphan(path: str) -> str:
    return (
        f"{path} — nobody imports it, not an entry point. "
        f"If you need it — move to archive/. If not — delete."
    )


def tip_monster(path: str, lines: int, functions: int) -> str:
    if lines > 3000:
        tone = "This isn't a file, it's a novel."
    elif lines > 1000:
        tone = "This file needs splitting."
    else:
        tone = "Getting big."
    return (
        f"{path} — {lines} lines, {functions} functions. "
        f"{tone} One file = one responsibility."
    )


def tip_env_files(count: int) -> str:
    if count > 1:
        return (
            f"You have {count} .env files in different directories. "
            f"That's chaos. Usually one .env in root is enough."
        )
    return "One .env file — that's clean."
