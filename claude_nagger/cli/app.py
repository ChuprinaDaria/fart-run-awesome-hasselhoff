import sys
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from claude_nagger.core.parser import TokenParser
from claude_nagger.core.calculator import CostCalculator
from claude_nagger.core.analyzer import Analyzer
from claude_nagger.core.tips import TipsEngine
from claude_nagger.core.sounds import SoundPlayer
from claude_nagger.nagger.messages import get_nag_message, get_nag_level
from claude_nagger.nagger.hasselhoff import get_hoff_phrase, get_hoff_image, get_victory_sound
from claude_nagger.i18n import get_string, set_language, get_language

console = Console()


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def one_shot_stats(claude_dir: str | None = None):
    parser = TokenParser(claude_dir=claude_dir)
    stats = parser.parse_today()
    calc = CostCalculator()
    cost = calc.calculate_cost(stats)

    table = Table(title=f"Claude Token Stats \u2014 {stats.date}", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")
    table.add_row(get_string("sessions"), str(len(stats.sessions)))
    table.add_row(get_string("input_tokens"), _fmt(stats.total_input))
    table.add_row(get_string("output_tokens"), _fmt(stats.total_output))
    table.add_row(get_string("cache_read"), _fmt(stats.total_cache_read))
    table.add_row(get_string("cache_write"), _fmt(stats.total_cache_write))
    table.add_row(get_string("billable"), _fmt(stats.total_billable))
    table.add_row(get_string("cost_today"), f"${cost.total_cost:.2f}")
    table.add_row(get_string("cache_efficiency"), f"{Analyzer.cache_efficiency(stats):.1f}%")
    console.print(table)

    if stats.model_totals:
        mt = Table(title="Models", box=box.SIMPLE)
        mt.add_column("Model", style="magenta")
        mt.add_column("Tokens", justify="right")
        mt.add_column("Calls", justify="right")
        for model, mu in stats.model_totals.items():
            name = model.replace("claude-", "").upper()
            mt.add_row(name, _fmt(mu.billable_tokens), str(mu.calls))
        console.print(mt)


def one_shot_nag(claude_dir: str | None = None):
    parser = TokenParser(claude_dir=claude_dir)
    stats = parser.parse_today()
    calc = CostCalculator()
    cost = calc.calculate_cost(stats)
    level = get_nag_level(stats.total_billable)
    msg = get_nag_message(level, stats.total_billable, len(stats.sessions))

    colors = {1: "yellow", 2: "dark_orange", 3: "red", 4: "bold red"}
    console.print(Panel(msg, title="fart.run", style=colors.get(level, "red")))
    console.print(f"  [dim]${cost.total_cost:.2f} today | {_fmt(stats.total_billable)} billable | {len(stats.sessions)} sessions[/dim]")

    sounds = SoundPlayer()
    sounds.play_random("farts")


def one_shot_hoff(claude_dir: str | None = None):
    phrase = get_hoff_phrase()
    console.print(Panel(phrase, title="HASSELHOFF MODE", style="bold gold1"))
    victory = get_victory_sound()
    if victory:
        SoundPlayer().play(victory)


def one_shot_summary(claude_dir: str | None = None):
    parser = TokenParser(claude_dir=claude_dir)
    stats = parser.parse_today()
    sub = parser.get_subscription()
    calc = CostCalculator()
    cost = calc.calculate_cost(stats)
    cache_eff = Analyzer.cache_efficiency(stats)
    projects = Analyzer.project_breakdown(stats)
    comparison = Analyzer.model_comparison(stats)
    tips = TipsEngine.get_tips(stats, cost, subscription=sub)
    savings = Analyzer.cache_savings_usd(stats)
    is_sub = sub.get("type") in ("pro", "max", "team")

    console.print()
    sub_badge = f" [{sub.get('type', '').upper()}]" if is_sub else ""
    console.print(Panel.fit(f"[bold]fart.run & amazing Hasselhoff{sub_badge}[/bold]", style="bold cyan"))

    # Budget bar
    if is_sub:
        # Subscription: show token usage, not dollars
        budget_tokens = 5_000_000  # rough daily token budget for Max plan
        pct = min(stats.total_billable / budget_tokens * 100, 100)
        bar_color = "green" if pct < 33 else ("yellow" if pct < 66 else "red")
        filled = int(pct / 5)
        bar = f"[{bar_color}]{'█' * filled}{'░' * (20 - filled)}[/{bar_color}]"
        console.print(f"  Tokens: {bar} {pct:.0f}% ({_fmt(stats.total_billable)} / {_fmt(budget_tokens)}) [dim]use /usage for exact limits[/dim]")
    else:
        budget = 5.0
        pct = min(cost.total_cost / budget * 100, 100) if budget > 0 else 0
        bar_color = "green" if pct < 33 else ("yellow" if pct < 66 else "red")
        filled = int(pct / 5)
        bar = f"[{bar_color}]{'█' * filled}{'░' * (20 - filled)}[/{bar_color}]"
        console.print(f"  Budget: {bar} {pct:.0f}% (${cost.total_cost:.2f} / ${budget:.2f})")
    console.print()

    # Stats grid
    grid = Table.grid(padding=(0, 3))
    grid.add_column(justify="right", style="cyan")
    grid.add_column(style="white")
    grid.add_column(justify="right", style="cyan")
    grid.add_column(style="white")
    grid.add_row(
        get_string("sessions") + ":", str(len(stats.sessions)),
        get_string("cache_efficiency") + ":", f"{cache_eff:.1f}%",
    )
    grid.add_row(
        get_string("input_tokens") + ":", _fmt(stats.total_input),
        get_string("cache_read") + ":", _fmt(stats.total_cache_read),
    )
    grid.add_row(
        get_string("output_tokens") + ":", _fmt(stats.total_output),
        get_string("cache_write") + ":", _fmt(stats.total_cache_write),
    )
    grid.add_row(
        get_string("billable") + ":", _fmt(stats.total_billable),
        "Cache saved:", f"~${savings:.2f}",
    )
    console.print(Panel(grid, title=stats.date, box=box.ROUNDED))

    # Models
    if stats.model_totals:
        mt = Table(title=get_string("model_comparison"), box=box.SIMPLE_HEAVY)
        mt.add_column("Model")
        mt.add_column("Tokens", justify="right")
        if is_sub:
            mt.add_column("API equiv.", justify="right", style="dim")
        else:
            mt.add_column("Cost", justify="right")
        mt.add_column("If Sonnet", justify="right", style="green")
        mt.add_column("If Haiku", justify="right", style="green")
        for model, mu in stats.model_totals.items():
            name = model.replace("claude-", "").upper()
            mt.add_row(
                name, _fmt(mu.billable_tokens),
                f"${comparison.get('actual', 0):.2f}",
                f"${comparison.get('claude-sonnet-4-6', 0):.2f}",
                f"${comparison.get('claude-haiku-4-5', 0):.2f}",
            )
        console.print(mt)

    # Projects
    if projects:
        pt = Table(title=get_string("top_projects"), box=box.SIMPLE)
        pt.add_column("Project", style="magenta")
        pt.add_column("Tokens", justify="right")
        pt.add_column("", width=30)
        max_tok = max(p.total_billable for p in projects) if projects else 1
        for p in projects[:5]:
            bar_len = int(p.total_billable / max(max_tok, 1) * 20)
            pt.add_row(p.project, _fmt(p.total_billable), "\u2588" * bar_len)
        console.print(pt)

    # Tip
    if tips:
        lang_attr = "message_ua" if get_language() == "ua" else "message_en"
        console.print(Panel(
            f"[yellow]\U0001f4a1[/yellow] {getattr(tips[0], lang_attr)}",
            title="Tip", box=box.ROUNDED,
        ))

    # Nag
    level = get_nag_level(stats.total_billable)
    if stats.total_billable > 0:
        msg = get_nag_message(level, stats.total_billable, len(stats.sessions))
        console.print(f"\n  [italic dim]{msg}[/italic dim]\n")


def run_watch(claude_dir: str | None = None):
    try:
        from claude_nagger.cli.tui import NaggerApp
        app = NaggerApp(claude_dir=claude_dir)
        app.run()
    except ImportError:
        console.print("[red]Textual not installed. Run: pip install textual[/red]")
        one_shot_summary(claude_dir=claude_dir)


def main():
    parser = argparse.ArgumentParser(description="Claude Nagger CLI")
    parser.add_argument("command", nargs="?", default="summary",
                        choices=["stats", "nag", "hoff", "summary", "watch"],
                        help="Command to run")
    parser.add_argument("--lang", "-l", default="en", choices=["en", "ua"])
    parser.add_argument("--claude-dir", default=None)
    args = parser.parse_args()

    set_language(args.lang)

    {"stats": one_shot_stats, "nag": one_shot_nag, "hoff": one_shot_hoff,
     "summary": one_shot_summary, "watch": run_watch}[args.command](claude_dir=args.claude_dir)


if __name__ == "__main__":
    main()
