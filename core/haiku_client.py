"""Claude Haiku client for personalized tips and explanations.

Optional — requires anthropic SDK and API key.
~$0.001 per call, rate limited to max 1 call per 5 minutes.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time

log = logging.getLogger(__name__)

_MIN_INTERVAL = 300  # 5 minutes between API calls


class HaikuClient:
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._cache: dict[str, str] = {}
        self._last_call: float = 0
        self._client = None

    def is_available(self) -> bool:
        return self._api_key is not None

    def _get_client(self):
        if self._client is None and self._api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._api_key)
            except ImportError:
                log.warning("anthropic SDK not installed — Haiku features disabled")
                self._api_key = None
        return self._client

    def ask(self, prompt: str, max_tokens: int = 200) -> str | None:
        """Ask Haiku a question. Returns cached response if available."""
        cache_key = hashlib.md5(prompt.encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        if not self.is_available():
            return None

        now = time.time()
        if now - self._last_call < _MIN_INTERVAL:
            return None

        client = self._get_client()
        if not client:
            return None

        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            result = response.content[0].text
            self._cache[cache_key] = result
            self._last_call = now
            return result
        except Exception as e:
            log.error("Haiku API error: %s", e)
            return None

    def get_tip(self, stats_summary: str) -> str | None:
        """Get personalized tip based on usage stats."""
        prompt = (
            f"You are a Claude Code usage advisor. Based on these stats, give ONE specific, "
            f"actionable tip to save tokens or improve efficiency. Max 2 sentences.\n\n"
            f"Stats: {stats_summary}"
        )
        return self.ask(prompt)

    def recommend_model(self, task_description: str) -> str | None:
        """Recommend model based on task."""
        prompt = (
            f"You are a Claude model advisor. For this task, recommend Opus, Sonnet, or Haiku. "
            f"ONE sentence with estimated token savings.\n\n"
            f"Task: {task_description[:200]}"
        )
        return self.ask(prompt, max_tokens=100)

    def explain_finding(self, finding_description: str, project_context: str = "") -> str | None:
        """Explain a security finding in context."""
        prompt = (
            f"Explain this security finding in simple terms for a developer. "
            f"What is the risk? How to fix it? 3 sentences max.\n\n"
            f"Finding: {finding_description}\n"
            f"Project context: {project_context or 'general dev environment'}"
        )
        return self.ask(prompt, max_tokens=150)
