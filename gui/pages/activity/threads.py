"""Background QThreads owned by ``ActivityPage`` — Haiku helpers."""
from __future__ import annotations

import logging

from PyQt5.QtCore import QThread, pyqtSignal

from core.models import ActivityEntry

log = logging.getLogger(__name__)


class HaikuPromptsThread(QThread):
    """Ask Haiku to summarize a list of user prompts ('what were you trying to do?')."""

    result_ready = pyqtSignal(str)

    def __init__(self, prompts_text: str, config: dict,
                 on_api_error=None, parent=None):
        super().__init__(parent)
        self._text = prompts_text
        # Shallow copy so a Settings save mid-run doesn't pull config
        # out from under us.
        self._config = dict(config or {})
        self._on_api_error = on_api_error

    def run(self):
        try:
            from core.haiku_client import HaikuClient
            client = HaikuClient(config=self._config,
                                 on_api_error=self._on_api_error)
            if not client.is_available():
                self.result_ready.emit("")
                return

            lang = self._config.get("general", {}).get("language", "en")
            if lang == "ua":
                prompt = (
                    "Ти — помічник для vibe-кодерів. Нижче — список промптів, "
                    "що юзер писав у Claude Code (від старих до нових). "
                    "Напиши 2-4 речення простою мовою: з чого почали, "
                    "що робили далі, де застрягли. Без технічного жаргону.\n\n"
                    + self._text
                )
            else:
                prompt = (
                    "You're a helper for vibe coders. Below is a list of "
                    "prompts the developer sent to Claude Code (oldest to "
                    "newest). Write 2-4 plain-English sentences: what they "
                    "started with, what they did next, where they got stuck. "
                    "No tech jargon.\n\n" + self._text
                )
            summary = client.ask(prompt, max_tokens=300)
            self.result_ready.emit(summary or "")
        except Exception as e:
            log.debug("HaikuPromptsThread error: %s", e)
            self.result_ready.emit("")


class HaikuContextThread(QThread):
    """Background thread — asks Haiku for 'where you stopped' and activity summary."""

    result_ready = pyqtSignal(str, str)  # (haiku_context, haiku_summary)

    def __init__(self, entry: ActivityEntry, config: dict, on_api_error=None, parent=None):
        super().__init__(parent)
        self._entry = entry
        self._config = dict(config or {})
        self._on_api_error = on_api_error

    def run(self):
        try:
            from core.haiku_client import HaikuClient
            client = HaikuClient(config=self._config, on_api_error=self._on_api_error)
            if not client.is_available():
                self.result_ready.emit("", "")
                return

            lang = self._config.get("general", {}).get("language", "en")

            # Build activity summary text for Haiku
            parts = []
            if self._entry.files:
                file_list = ", ".join(f.path for f in self._entry.files[:10])
                parts.append(f"Files changed: {file_list}")
            if self._entry.commits:
                parts.append(f"Recent commits: {'; '.join(self._entry.commits[:3])}")
            if self._entry.docker_changes:
                docker_list = ", ".join(
                    f"{d.name} ({d.status})" for d in self._entry.docker_changes
                )
                parts.append(f"Docker: {docker_list}")
            if self._entry.port_changes:
                port_list = ", ".join(
                    f":{p.port} {p.status}" for p in self._entry.port_changes
                )
                parts.append(f"Ports: {port_list}")

            if not parts:
                self.result_ready.emit("", "")
                return

            activity_text = "\n".join(parts)

            # "Where you stopped" context
            context_prompt = (
                f"You are a developer assistant. Based on the recent activity in a project, "
                f"write a short 2-3 sentence summary in {lang} of 'where the developer left off'. "
                f"Be practical and specific. No fluff.\n\nActivity:\n{activity_text}"
            )
            haiku_context = client.ask(context_prompt, max_tokens=200) or ""

            # Short activity summary
            summary_prompt = (
                f"Summarize this developer activity in one sentence ({lang}). "
                f"Just the facts, what changed.\n\nActivity:\n{activity_text}"
            )
            haiku_summary = client.ask(summary_prompt, max_tokens=100) or ""

            self.result_ready.emit(haiku_context, haiku_summary)

        except Exception as e:
            log.error("HaikuContextThread error: %s", e)
            self.result_ready.emit("", "")
