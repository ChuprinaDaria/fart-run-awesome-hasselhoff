from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ModelUsage:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input + self.output + self.cache_read + self.cache_write

    @property
    def billable_tokens(self) -> int:
        return self.input + self.output + self.cache_write


@dataclass
class SessionStats:
    session_id: str
    project: str
    model_stats: dict[str, ModelUsage] = field(default_factory=dict)
    start_time: datetime | None = None


@dataclass
class TokenStats:
    date: str
    sessions: list[SessionStats] = field(default_factory=list)
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    total_billable: int = 0
    model_totals: dict[str, ModelUsage] = field(default_factory=dict)


@dataclass
class CostBreakdown:
    input_cost: float = 0.0
    output_cost: float = 0.0
    cache_read_cost: float = 0.0
    cache_write_cost: float = 0.0
    total_cost: float = 0.0


@dataclass
class DayStats:
    date: str
    total_tokens: int = 0
    total_billable: int = 0
    tokens_by_model: dict[str, int] = field(default_factory=dict)


@dataclass
class ProjectUsage:
    project: str
    total_tokens: int = 0
    total_billable: int = 0
    sessions: int = 0


@dataclass
class Tip:
    category: str
    message_en: str
    message_ua: str
    relevance: float = 0.5
    action: str | None = None
