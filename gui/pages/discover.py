from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PyQt5.QtCore import Qt
from i18n import get_language

DISCOVER_RESOURCES = [
    # === Skills & Plugins ===
    {
        "title": "Awesome Claude Skills (53K+ stars)",
        "desc_en": "30+ curated productivity skills: TDD, debugging, code review, PR management, brainstorming",
        "desc_ua": "30+ скілів: TDD, дебаг, код рев'ю, PR менеджмент, брейнштормінг",
        "url": "https://github.com/ComposioHQ/awesome-claude-skills",
        "icon": "\U0001f9e9",
        "section_en": "Skills & Plugins",
        "section_ua": "Скіли та плагіни",
    },
    {
        "title": "Official Anthropic Skills",
        "desc_en": "PDF, DOCX, XLSX, PPTX processing, commit, code review by Anthropic",
        "desc_ua": "PDF, DOCX, XLSX, PPTX обробка, коміт, код рев'ю від Anthropic",
        "url": "https://github.com/anthropics/skills",
        "icon": "\U0001f9e9",
    },
    {
        "title": "Superpowers Plugin",
        "desc_en": "TDD, brainstorming, plan execution, git worktrees, code review workflows",
        "desc_ua": "TDD, брейнштормінг, виконання планів, git worktrees, код рев'ю",
        "url": "https://github.com/anthropics/claude-code/tree/main/plugins",
        "icon": "\U0001f9e9",
    },
    {
        "title": "Firecrawl Plugin",
        "desc_en": "Web scraping, search, crawling directly from Claude Code. Replace WebFetch/WebSearch",
        "desc_ua": "Веб-скрепінг, пошук, кролінг прямо з Claude Code. Заміна WebFetch/WebSearch",
        "url": "https://github.com/anthropics/claude-code/tree/main/plugins",
        "icon": "\U0001f9e9",
    },
    # === MCP Servers ===
    {
        "title": "MCP Servers Directory",
        "desc_en": "Connect Claude to databases, APIs, Slack, GitHub, browsers, filesystems and 100+ tools",
        "desc_ua": "Підключи Claude до баз даних, API, Slack, GitHub, браузерів та 100+ інструментів",
        "url": "https://github.com/modelcontextprotocol/servers",
        "icon": "\U0001f527",
        "section_en": "MCP Servers",
        "section_ua": "MCP Сервери",
    },
    {
        "title": "Playwright MCP",
        "desc_en": "Browser automation: navigate, click, fill forms, scrape, screenshot from Claude",
        "desc_ua": "Автоматизація браузера: навігація, кліки, форми, скріншоти з Claude",
        "url": "https://github.com/anthropics/claude-code/tree/main/plugins",
        "icon": "\U0001f527",
    },
    {
        "title": "Sequential Thinking MCP",
        "desc_en": "Structured reasoning server for complex multi-step problem solving",
        "desc_ua": "Структуроване мислення для складних багатокрокових задач",
        "url": "https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking",
        "icon": "\U0001f527",
    },
    # === Token Optimization ===
    {
        "title": "18 Token Management Hacks",
        "desc_en": "Practical tips: /compact, context management, prompt engineering for efficiency",
        "desc_ua": "Практичні хаки: /compact, менеджмент контексту, промпт інженерінг",
        "url": "https://www.mindstudio.ai/blog/claude-code-token-management-hacks-3/",
        "icon": "\U0001f4b0",
        "section_en": "Token Optimization",
        "section_ua": "Оптимізація токенів",
    },
    {
        "title": "6 Ways to Cut Token Usage in Half",
        "desc_en": "Tested: CLAUDE.md, /compact, model switching, specific prompts, batch tasks",
        "desc_ua": "Перевірено: CLAUDE.md, /compact, переключення моделей, конкретні промпти",
        "url": "https://www.sabrina.dev/p/6-ways-i-cut-my-claude-token-usage",
        "icon": "\U0001f4b0",
    },
    {
        "title": "Prompt Caching Deep Dive",
        "desc_en": "Save 90% on repeated tokens. Cache structure: system -> tools -> messages",
        "desc_ua": "Економ 90% на повторних токенах. Структура кешу: system -> tools -> messages",
        "url": "https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching",
        "icon": "\U0001f4b0",
    },
    # === Documentation ===
    {
        "title": "Claude Code Memory (CLAUDE.md)",
        "desc_en": "Project memory: conventions, commands, architecture. Persists across sessions",
        "desc_ua": "Пам'ять проєкту: конвенції, команди, архітектура. Зберігається між сесіями",
        "url": "https://docs.anthropic.com/en/docs/claude-code/memory",
        "icon": "\U0001f4d6",
        "section_en": "Documentation",
        "section_ua": "Документація",
    },
    {
        "title": "Claude Code Hooks",
        "desc_en": "Pre/post tool hooks: auto-lint, auto-test, custom notifications on every action",
        "desc_ua": "Pre/post хуки: авто-лінт, авто-тест, кастомні нотифікації на кожну дію",
        "url": "https://docs.anthropic.com/en/docs/claude-code/hooks",
        "icon": "\U0001f4d6",
    },
    {
        "title": "Slash Commands Reference",
        "desc_en": "/compact /model /review /pr /init /cost /usage /clear /config /doctor",
        "desc_ua": "/compact /model /review /pr /init /cost /usage /clear /config /doctor",
        "url": "https://docs.anthropic.com/en/docs/claude-code/cli-usage",
        "icon": "\U0001f4d6",
    },
    {
        "title": "Claude Agent SDK",
        "desc_en": "Build custom multi-step AI agents: tool use, orchestration, delegation",
        "desc_ua": "Створюй кастомних AI агентів: tool use, оркестрація, делегування",
        "url": "https://docs.anthropic.com/en/docs/agents-and-tools/claude-agent-sdk",
        "icon": "\U0001f4d6",
    },
    {
        "title": "IDE Extensions (VS Code, JetBrains)",
        "desc_en": "Use Claude Code inside your IDE: inline edits, terminal, sidebar chat",
        "desc_ua": "Claude Code в IDE: інлайн правки, термінал, чат в сайдбарі",
        "url": "https://docs.anthropic.com/en/docs/claude-code/ide-integrations",
        "icon": "\U0001f4d6",
    },
    # === Community ===
    {
        "title": "Reddit Tips & Tricks Megathread",
        "desc_en": "Community-collected tips, gotchas, workflows, productivity hacks",
        "desc_ua": "Зібрані спільнотою поради, трюки, робочі процеси",
        "url": "https://www.reddit.com/r/ClaudeCode/comments/1q193fr/",
        "icon": "\U0001f465",
        "section_en": "Community",
        "section_ua": "Спільнота",
    },
    {
        "title": "r/ClaudeCode Subreddit",
        "desc_en": "Active community: tips, showcases, bug reports, feature requests",
        "desc_ua": "Активна спільнота: поради, демо, баг-репорти, запити фіч",
        "url": "https://www.reddit.com/r/ClaudeCode/",
        "icon": "\U0001f465",
    },
    {
        "title": "10 Must-Have Skills for Claude Code",
        "desc_en": "Curated list: debugging, TDD, architecture, code review, deployment workflows",
        "desc_ua": "Кращі скіли: дебаг, TDD, архітектура, код рев'ю, деплоймент",
        "url": "https://medium.com/@unicodeveloper/10-must-have-skills-for-claude-and-any-coding-agent-in-2026-b5451b013051",
        "icon": "\U0001f465",
    },
    {
        "title": "Claude Code GitHub Issues",
        "desc_en": "Report bugs, request features, see what's coming next",
        "desc_ua": "Баг-репорти, запити фіч, що буде далі",
        "url": "https://github.com/anthropics/claude-code/issues",
        "icon": "\U0001f465",
    },
]


class DiscoverTab(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        container = QWidget()
        self.items_layout = QVBoxLayout(container)
        self.items_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        layout.addWidget(scroll)
        self._populate()

    def _populate(self):
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        lang = get_language()
        current_section = None

        for res in DISCOVER_RESOURCES:
            # Section header
            section = res.get(f"section_{lang}") or res.get("section_en")
            if section and section != current_section:
                current_section = section
                header = QLabel(f"<b>\u2501\u2501 {section} \u2501\u2501</b>")
                header.setStyleSheet("font-size: 14px; padding: 8px 4px 2px 4px; color: #000080;")
                self.items_layout.addWidget(header)

            icon = res.get("icon", "\U0001f517")
            desc = res.get(f"desc_{lang}", res["desc_en"])
            text = (f'{icon}  <b>{res["title"]}</b><br/>'
                    f'{desc}<br/>'
                    f'<a href="{res["url"]}" style="color: #000080;">{res["url"]}</a>')
            lbl = QLabel(text)
            lbl.setWordWrap(True)
            lbl.setOpenExternalLinks(True)
            lbl.setTextFormat(Qt.RichText)
            lbl.setStyleSheet(
                "padding: 6px 8px; margin: 1px 4px; background: white; color: #000; "
                "border: 2px groove #808080;"
            )
            self.items_layout.addWidget(lbl)

    def retranslate(self):
        self._populate()
