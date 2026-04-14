from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.reactive import reactive

from claude_nagger.core.parser import TokenParser
from claude_nagger.core.calculator import CostCalculator
from claude_nagger.core.analyzer import Analyzer
from claude_nagger.core.tips import TipsEngine
from claude_nagger.core.sounds import SoundPlayer
from claude_nagger.nagger.messages import get_nag_message, get_nag_level
from claude_nagger.nagger.hasselhoff import get_hoff_phrase
from claude_nagger.i18n import get_language, set_language


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class StatsWidget(Static):
    def __init__(self, claude_dir: str | None = None):
        super().__init__()
        self.claude_dir = claude_dir
        self.budget = 5.0

    def refresh_data(self) -> None:
        parser = TokenParser(claude_dir=self.claude_dir)
        stats = parser.parse_today()
        calc = CostCalculator()
        cost = calc.calculate_cost(stats)
        cache_eff = Analyzer.cache_efficiency(stats)
        projects = Analyzer.project_breakdown(stats)
        comparison = Analyzer.model_comparison(stats)
        tips = TipsEngine.get_tips(stats, cost)
        savings = Analyzer.cache_savings_usd(stats)
        level = get_nag_level(stats.total_billable)

        lines = []

        # Budget bar
        pct = min(cost.total_cost / self.budget * 100, 100) if self.budget > 0 else 0
        filled = int(pct / 5)
        bar = f"{'█' * filled}{'░' * (20 - filled)}"
        lines.append(f"  Budget: [{bar}] {pct:.0f}% (${cost.total_cost:.2f} / ${self.budget:.2f})")
        lines.append("")

        # Stats
        lines.append(f"  Sessions: {len(stats.sessions):>8}   Cache Efficiency: {cache_eff:.1f}%")
        lines.append(f"  Input:    {_fmt(stats.total_input):>8}   Cache Read:  {_fmt(stats.total_cache_read):>8}")
        lines.append(f"  Output:   {_fmt(stats.total_output):>8}   Cache Write: {_fmt(stats.total_cache_write):>8}")
        lines.append(f"  Billable: {_fmt(stats.total_billable):>8}   Cache saved: ~${savings:.2f}")
        lines.append("")

        # Models
        if stats.model_totals:
            lines.append(f"  {'Model':<16} {'Tokens':>10} {'Cost':>10} {'If Sonnet':>12} {'If Haiku':>12}")
            for model, mu in stats.model_totals.items():
                name = model.replace("claude-", "").upper()
                lines.append(
                    f"  {name:<16} {_fmt(mu.billable_tokens):>10} "
                    f"${comparison.get('actual', 0):>9.4f} "
                    f"${comparison.get('claude-sonnet-4-6', 0):>11.4f} "
                    f"${comparison.get('claude-haiku-4-5', 0):>11.4f}"
                )
            lines.append("")

        # Projects
        if projects:
            lines.append("  Top Projects:")
            max_tok = max(p.total_billable for p in projects) if projects else 1
            for p in projects[:5]:
                bar_len = int(p.total_billable / max(max_tok, 1) * 15)
                lines.append(f"    {p.project:<15} {_fmt(p.total_billable):>8}  {'█' * bar_len}")
            lines.append("")

        # Tip
        if tips:
            lang_attr = "message_ua" if get_language() == "ua" else "message_en"
            lines.append(f"  \U0001f4a1 {getattr(tips[0], lang_attr)}")
            lines.append("")

        # Nag
        if stats.total_billable > 0:
            msg = get_nag_message(level, stats.total_billable, len(stats.sessions))
            lines.append(f'  "{msg}"')

        self.update("\n".join(lines))


class NaggerApp(App):
    CSS = """
    Screen { background: $surface; }
    #stats { height: 1fr; padding: 1; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("n", "nag", "Nag"),
        ("h", "hoff", "Hoff"),
        ("l", "toggle_lang", "Lang"),
    ]

    def __init__(self, claude_dir: str | None = None):
        super().__init__()
        self.claude_dir = claude_dir
        self._stats_widget = StatsWidget(claude_dir=claude_dir)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield self._stats_widget
        yield Footer()

    def on_mount(self) -> None:
        self.title = "fart.run & amazing Hasselhoff"
        self._stats_widget.refresh_data()
        self.set_interval(30, self._auto_refresh)

    def _auto_refresh(self) -> None:
        self._stats_widget.refresh_data()

    def action_refresh(self) -> None:
        self._stats_widget.refresh_data()

    def action_nag(self) -> None:
        SoundPlayer().play_random("farts")
        self._stats_widget.refresh_data()

    def action_hoff(self) -> None:
        from claude_nagger.nagger.hasselhoff import get_victory_sound
        v = get_victory_sound()
        if v:
            SoundPlayer().play(v)
        self._stats_widget.refresh_data()

    def action_toggle_lang(self) -> None:
        set_language("ua" if get_language() == "en" else "en")
        self._stats_widget.refresh_data()
