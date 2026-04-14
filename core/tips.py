from core.models import TokenStats, CostBreakdown, Tip
from core.usage_analyzer import Analyzer


class TipsEngine:
    @staticmethod
    def get_tips(stats: TokenStats, cost: CostBreakdown, subscription: dict | None = None) -> list[Tip]:
        tips: list[Tip] = []
        cache_eff = Analyzer.cache_efficiency(stats)
        sub = subscription or {}
        is_sub = sub.get("type") in ("pro", "max", "team")

        # ===== DYNAMIC TIPS (based on actual usage patterns) =====

        # --- Heavy single session (one session eating >60% of tokens) ---
        if stats.sessions:
            session_tokens = []
            for s in stats.sessions:
                st = sum(mu.billable_tokens for mu in s.model_stats.values())
                session_tokens.append((s, st))
            session_tokens.sort(key=lambda x: x[1], reverse=True)
            top_session = session_tokens[0]
            if stats.total_billable > 0 and top_session[1] / stats.total_billable > 0.6:
                proj = top_session[0].project
                pct = top_session[1] / stats.total_billable * 100
                tips.append(Tip(
                    category="session", relevance=0.97,
                    message_en=f'Project "{proj}" is eating {pct:.0f}% of your tokens! Use /compact in long sessions, or split into smaller tasks',
                    message_ua=f'Проєкт "{proj}" з\'їдає {pct:.0f}% токенів! Юзай /compact в довгих сесіях, або розбий на менші задачі',
                ))

        # --- Cache efficiency analysis ---
        if cache_eff > 90:
            saved = Analyzer.cache_savings_usd(stats)
            tips.append(Tip(
                category="cache", relevance=0.6,
                message_en=f"Great cache hit rate ({cache_eff:.0f}%)! You're saving ~${saved:.2f} today through caching. Keep sessions alive!",
                message_ua=f"Класний кеш ({cache_eff:.0f}%)! Ти економиш ~${saved:.2f} сьогодні через кешування. Тримай сесії живими!",
            ))
        elif cache_eff < 60:
            tips.append(Tip(
                category="cache", relevance=0.95,
                message_en="Low cache hit rate ({eff:.0f}%)! Use CLAUDE.md for stable system prompts. Keep tasks in one session. Guide: https://docs.anthropic.com/en/docs/claude-code/memory".format(eff=cache_eff),
                message_ua="Низький кеш ({eff:.0f}%)! Юзай CLAUDE.md для стабільних system prompts. Тримай задачі в одній сесії. Гайд: https://docs.anthropic.com/en/docs/claude-code/memory".format(eff=cache_eff),
            ))
            tips.append(Tip(
                category="cache", relevance=0.9,
                message_en="Each new session = cold start (no cache). Use /continue to resume previous sessions instead of starting fresh",
                message_ua="Кожна нова сесія = холодний старт (без кешу). Юзай /continue замість нового старту",
            ))
        elif cache_eff < 80:
            tips.append(Tip(
                category="cache", relevance=0.8,
                message_en="Cache hit rate is {eff:.0f}% \u2014 decent but could be better. Put static content (tools, system) first in prompts".format(eff=cache_eff),
                message_ua="Кеш хіт рейт {eff:.0f}% \u2014 непогано, але можна краще. Ставь статичний контент на початок промптів".format(eff=cache_eff),
            ))

        # --- Model selection (based on what models are actually used) ---
        opus_only = all("opus" in m for m in stats.model_totals) and len(stats.model_totals) > 0
        uses_multiple = len(stats.model_totals) > 1

        if opus_only and stats.total_output > 10000:
            # Calculate potential savings
            calc_savings = 0
            if cost.total_cost > 0:
                from core.calculator import CostCalculator
                sonnet_cost = CostCalculator().what_if_model(stats, "claude-sonnet-4-6")
                calc_savings = cost.total_cost - sonnet_cost.total_cost

            if is_sub:
                tips.append(Tip(
                    category="model", relevance=0.92,
                    message_en="100% Opus today. Use /model sonnet for routine tasks \u2014 saves ~{pct:.0f}% of token quota. Keep Opus for complex work".format(pct=calc_savings/max(cost.total_cost,0.01)*100),
                    message_ua="100% Opus сьогодні. Юзай /model sonnet для рутини \u2014 економить ~{pct:.0f}% квоти токенів. Opus для складного".format(pct=calc_savings/max(cost.total_cost,0.01)*100),
                ))
            else:
                tips.append(Tip(
                    category="model", relevance=0.92,
                    message_en="100% Opus today = ${cost:.2f}. With Sonnet: ${alt:.2f} (save ${save:.2f}). Use /model sonnet".format(cost=cost.total_cost, alt=cost.total_cost-calc_savings, save=calc_savings),
                    message_ua="100% Opus сьогодні = ${cost:.2f}. Якби Sonnet: ${alt:.2f} (економія ${save:.2f}). Юзай /model sonnet".format(cost=cost.total_cost, alt=cost.total_cost-calc_savings, save=calc_savings),
                ))
            tips.append(Tip(
                category="model", relevance=0.85,
                message_en="Quick rule: Opus for architecture/debugging, Sonnet for coding/edits, Haiku for questions/explanations",
                message_ua="Просте правило: Opus для архітектури/дебагу, Sonnet для коду/правок, Haiku для питань/пояснень",
            ))
        elif uses_multiple:
            tips.append(Tip(
                category="model", relevance=0.5,
                message_en="Good job using multiple models! Smart model switching is the #1 way to save tokens",
                message_ua="Молодець \u2014 юзаєш різні моделі! Розумне перемикання моделей \u2014 спосіб #1 економити токени",
            ))

        # --- Output/input ratio (verbosity detection) ---
        if stats.total_input > 0:
            ratio = stats.total_output / stats.total_input
            if ratio > 100:
                tips.append(Tip(
                    category="prompt", relevance=0.88,
                    message_en=f"Output/input ratio is {ratio:.0f}x \u2014 Claude is very verbose! Add 'be concise' or 'no explanations' to save output tokens (5x more expensive)",
                    message_ua=f"Output/input ratio {ratio:.0f}x \u2014 Claude надто балакучий! Додай 'be concise' або 'no explanations' (output в 5 разів дорожчий)",
                ))
            elif ratio > 30:
                tips.append(Tip(
                    category="prompt", relevance=0.78,
                    message_en=f"Output/input ratio is {ratio:.0f}x. Be more specific in prompts \u2014 'fix auth.py:42' is cheaper than 'fix bugs'",
                    message_ua=f"Output/input ratio {ratio:.0f}x. Будь конкретнішим \u2014 'fix auth.py:42' дешевше ніж 'fix bugs'",
                ))

        # --- Too many sessions (context re-reading) ---
        num_sessions = len(stats.sessions)
        if num_sessions > 8:
            tips.append(Tip(
                category="session", relevance=0.82,
                message_en=f"{num_sessions} sessions today! Each new session re-reads full context from scratch. Batch related tasks with /continue",
                message_ua=f"{num_sessions} сесій сьогодні! Кожна нова перечитує контекст з нуля. Об'єднуй задачі через /continue",
            ))
        elif num_sessions > 5:
            tips.append(Tip(
                category="session", relevance=0.7,
                message_en=f"{num_sessions} sessions today. Consider grouping related tasks \u2014 fewer sessions = more cache hits",
                message_ua=f"{num_sessions} сесій. Групуй пов'язані задачі \u2014 менше сесій = більше кеш-хітів",
            ))

        # --- Heavy usage (long day) ---
        if stats.total_billable > 500_000:
            tips.append(Tip(
                category="prompt", relevance=0.85,
                message_en="500K+ tokens today! Use /compact to compress history. Consider wrapping up \u2014 diminishing returns after long sessions",
                message_ua="500K+ токенів сьогодні! Юзай /compact для стиснення. Може вже пора перерву \u2014 після довгих сесій ефективність падає",
            ))
        elif stats.total_billable > 200_000:
            tips.append(Tip(
                category="prompt", relevance=0.72,
                message_en="200K+ tokens today. Use /compact in long sessions to keep context window manageable",
                message_ua="200K+ токенів. Юзай /compact в довгих сесіях щоб контекст не розпухав",
            ))

        # --- Multi-project switching ---
        unique_projects = {s.project for s in stats.sessions}
        if len(unique_projects) > 3:
            tips.append(Tip(
                category="session", relevance=0.75,
                message_en=f"Switching between {len(unique_projects)} projects today. Each switch loses cached context \u2014 batch work per project",
                message_ua=f"Стрибаєш між {len(unique_projects)} проєктами. Кожен свіч втрачає кеш \u2014 групуй роботу по проєктах",
            ))

        # --- Subscription-specific ---
        if is_sub:
            plan = sub.get("type", "").title()
            tips.append(Tip(
                category="subscription", relevance=0.6,
                message_en=f"{plan} plan: monthly fee, not per-token. But limits exist! Use /usage to check remaining quota",
                message_ua=f"План {plan}: оплата щомісячна, не за токен. Але ліміти є! /usage для перевірки залишку",
            ))

        # ===== STATIC TIPS (always relevant, lower priority) =====

        tips.append(Tip(
            category="skills", relevance=0.45,
            message_en="\U0001f517 Awesome Claude Skills \u2014 30+ skills: https://github.com/ComposioHQ/awesome-claude-skills",
            message_ua="\U0001f517 Awesome Claude Skills \u2014 30+ скілів: https://github.com/ComposioHQ/awesome-claude-skills",
        ))
        tips.append(Tip(
            category="docs", relevance=0.42,
            message_en="\U0001f517 CLAUDE.md = project memory. Use /init to auto-generate: https://docs.anthropic.com/en/docs/claude-code/memory",
            message_ua="\U0001f517 CLAUDE.md = пам'ять проєкту. /init для автогенерації: https://docs.anthropic.com/en/docs/claude-code/memory",
        ))
        tips.append(Tip(
            category="docs", relevance=0.40,
            message_en="\U0001f517 Token hacks (18 tips): https://www.mindstudio.ai/blog/claude-code-token-management-hacks-3/",
            message_ua="\U0001f517 18 хаків для токенів: https://www.mindstudio.ai/blog/claude-code-token-management-hacks-3/",
        ))
        tips.append(Tip(
            category="docs", relevance=0.38,
            message_en="\U0001f517 Slash commands: /compact /model /review /pr /init /clear /cost /usage",
            message_ua="\U0001f517 Слеш-команди: /compact /model /review /pr /init /clear /cost /usage",
        ))
        tips.append(Tip(
            category="skills", relevance=0.35,
            message_en="\U0001f517 MCP Servers \u2014 connect Claude to DBs, APIs, browsers: https://github.com/modelcontextprotocol/servers",
            message_ua="\U0001f517 MCP Сервери \u2014 підключи Claude до БД, API, браузерів: https://github.com/modelcontextprotocol/servers",
        ))

        tips.sort(key=lambda t: t.relevance, reverse=True)
        return tips
