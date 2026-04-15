# Vibe Coder Gaps — What Safety Net Doesn't Cover

> "AI зробив рефакторинг 3000 рядків без помилки. А кнопку переставити — 7 годин."
> Три проблеми які реально болять але не входять в Safety Net.

## Source

Real feedback from a vibe coder (2026-04-15). Background: old Java/Python courses, effectively starting from zero. Uses GitHub Copilot Chat (not CLI). Builds agent orchestration systems with sub-agents.

---

## Gap 1: UI Element Dictionary — "I don't know what this thing is called"

### Problem

Vibe coder sees a thing on screen. Wants AI to move it. Doesn't know it's called "breadcrumb" or "sidebar" or "modal". Tells AI "move that menu thing" and AI breaks 7 files for 7 hours because it guessed wrong.

Backend refactoring works perfectly because the vocabulary is precise: "rename this function", "move this class", "change this import". Frontend vocabulary is visual and non-obvious.

### Solution

New section in Health page (Phase 6 Docs area) or standalone reference page. A visual cheat sheet of common UI elements with:
- Name (English term that AI understands)
- ASCII wireframe showing where it lives
- One-line description
- Example prompt: "how to tell AI to change this"

### Content

```
+- UI Element Dictionary ------------------------------+
|                                                       |
|  NAVBAR / NAVIGATION BAR                              |
|  +--------------------------------------------------+|
|  | Logo   Home  About  Contact         [Login]      ||
|  +--------------------------------------------------+|
|  The bar at the very top. Usually has links + logo.   |
|  Tell AI: "change the navbar links" or "add a button |
|  to the navigation bar on the right side"             |
|                                                       |
|  --------------------------------------------------- |
|                                                       |
|  SIDEBAR                                              |
|  +------+-------------------------------------------+|
|  | Home |                                            ||
|  | Dash |  (main content here)                       ||
|  | Users|                                            ||
|  | Logs |                                            ||
|  +------+-------------------------------------------+|
|  Vertical menu on the left (sometimes right).         |
|  Tell AI: "add a new item to the sidebar" or          |
|  "move Settings to the bottom of the sidebar"         |
|                                                       |
|  --------------------------------------------------- |
|                                                       |
|  MODAL / DIALOG / POPUP                               |
|  +--------------------------------------------------+|
|  |          +- Delete Item? ------+                  ||
|  |          | Are you sure?       |                  ||
|  |          |   [Yes]   [No]      |                  ||
|  |          +---------------------+                  ||
|  +--------------------------------------------------+|
|  A box that appears on top of everything.             |
|  Tell AI: "show a confirmation modal before delete"   |
|  or "add a popup that asks for user input"            |
|                                                       |
+-------------------------------------------------------+
```

### Full element list (v1, ~20 elements):

**Layout:**
- Navbar / Navigation Bar
- Sidebar
- Footer
- Header / Hero
- Breadcrumb (Home > Products > Shoes)
- Tab / Tab Bar

**Interactive:**
- Modal / Dialog / Popup
- Dropdown / Select
- Toast / Notification (small message that disappears)
- Tooltip (hover text)
- Accordion / Collapsible
- Toggle / Switch

**Content:**
- Card (box with image + text + button)
- Table
- List / List Item
- Badge / Tag / Chip (small colored label)
- Avatar (user photo circle)
- Pagination (< 1 2 3 4 ... 10 >)

**Form:**
- Input / Text Field
- Textarea
- Checkbox / Radio
- Button (primary, secondary, danger, ghost)

### How it's accessed:

- New check in `docs_context.py`: `check_ui_vocabulary(report, project_dir)`
- Triggers only if project has .jsx/.tsx/.vue/.svelte/.html files
- Severity: info
- Finding links to the dictionary (rendered in health_page or as a separate popup)
- Also accessible from Tips page as a reference

### Implementation:

- Pure Python, no Rust, no API calls
- Content hardcoded in `data/ui_dictionary.md` or `data/ui_elements.py`
- Rendered as scrollable widget with ASCII wireframes
- i18n: EN + UA (element names stay English because AI needs English terms, but descriptions translated)

### Haiku enrichment:

If API key set — Haiku scans the project's frontend files and tells which elements ARE in the project:
"Your project has: navbar (in Header.tsx), sidebar (in Layout.tsx), modal (in DeleteConfirm.tsx). You don't have: breadcrumb, pagination, toast."

One batch_explain call. Cached per project scan.

---

## Gap 2: SDK Context Prep — "AI doesn't know this framework"

### Problem

Vibe coder uses a new SDK that has no stable release yet. AI (any model — Sonnet to Opus to GPT) doesn't know the patterns, decorators, or conventions. One wrong decorator breaks the entire agent tool connection. The SDK docs exist but AI doesn't have them in context.

Real example from the vibe coder: Microsoft Copilot SDK + Microsoft Agent Framework. Both are so new that no model has training data on them. Result: model guesses patterns, gets decorators wrong, everything breaks.

The vibe coder's workaround: clone someone else's working project into an "examples" folder and tell AI "look at this, learn, write a plan from what you see."

### Solution

Enhance existing `docs_context.py` Check 6.3 with actual documentation fetching. Two modes:

**Mode A: URL fetch (manual)**
User pastes a docs URL. System fetches it, extracts text, saves to `docs/context/` folder in the project. AI can then be pointed to this folder.

**Mode B: Package detection (auto)**
System reads requirements.txt / package.json, identifies packages that are:
- Very new (published < 6 months ago, if we can check)
- Not in common "well-known" list (django, react, express, flask — skip these)
- Have low download counts (niche)

For detected packages: show a prompt "AI might not know {package}. Fetch its docs?"

### Under the hood:

```python
class ContextFetcher:
    def __init__(self, project_dir: str)

    def fetch_url(self, url: str) -> ContextDoc
        # 1. HTTP GET with requests
        # 2. Extract text (html2text or BeautifulSoup)
        # 3. Truncate to ~50KB (enough for context, not too much)
        # 4. Save to {project_dir}/docs/context/{domain}-{slug}.md
        # Returns: ContextDoc(path, title, size, url)

    def detect_unknown_packages(self) -> list[UnknownPackage]
        # 1. Parse requirements.txt / package.json
        # 2. Filter out well-known packages (hardcoded list of ~200)
        # 3. For remaining: check PyPI/npm metadata (creation date, downloads)
        # 4. Flag packages that are new or niche
        # Returns: [{name, version, registry, reason}]

    def generate_context_file(self) -> str
        # Generates a single PROJECT_CONTEXT.md for pasting into AI chat:
        # - Project structure summary (from existing health file_tree)
        # - Entry points (from existing health entry_points)
        # - Key modules (from existing health module_map hubs)
        # - Fetched docs summary
        # Returns: path to generated file
```

### UI:

New section in Health page under Docs & Context:

```
+- SDK Context ----------------------------------------+
|                                                       |
|  Unknown packages detected:                           |
|                                                       |
|  ! copilot-sdk 0.3.1 — no stable release yet         |
|    AI probably doesn't know this. [Fetch Docs]        |
|                                                       |
|  ! agent-framework 0.1.0 — published 2 weeks ago     |
|    Very new package. [Fetch Docs]                     |
|                                                       |
|  ---                                                  |
|                                                       |
|  Fetch docs manually: [URL: ____________] [Fetch]     |
|                                                       |
|  ---                                                  |
|                                                       |
|  [Generate PROJECT_CONTEXT.md]                        |
|  Creates a file you can paste into AI chat so it      |
|  understands your project in 10 seconds.              |
|                                                       |
+-------------------------------------------------------+
```

### "Well-known" package list:

Hardcoded ~200 packages that every model knows:
- Python: django, flask, fastapi, requests, numpy, pandas, sqlalchemy, celery, pytest, pydantic...
- JS/TS: react, vue, angular, express, next, nuxt, tailwindcss, axios, lodash, prisma...
- Skip these from "unknown" detection

### Dependencies:

- `requests` (already in project deps for other features)
- `beautifulsoup4` or `html2text` — NEW dependency for HTML extraction
- Alternative: use existing `urllib` + regex stripping (no new deps, worse quality)

### Scope exclusions:

- No automatic fetching without user action (respect bandwidth + privacy)
- No caching of fetched docs in SQLite (files on disk are enough)
- No integration with context7 MCP (future — requires MCP client setup)
- No PDF parsing (text/HTML only)
- Generated context file is a snapshot, not auto-updated

---

## Gap 3: Hooks Explainer — "I don't get why I need this"

### Problem

Vibe coder understands WHAT a hook/trigger does (runs a command when X happens). But doesn't understand WHY or WHEN to use one. Has no mental model of CI/CD pipelines, automated testing, or deployment workflows.

Quote: "How the trigger works — clear enough. But a real use case for someone who has no production pipeline experience — that's hard."

### Solution

Not a feature. A curated set of 5-7 concrete scenarios with copy-paste configs, added to the Tips / Discover page. Written for someone who has ZERO devops experience.

### Content:

```markdown
# Hooks: 5 Real Scenarios (no devops required)

## 1. "Run tests before I commit broken code"

What happens: every time you (or AI) try to save code to git,
the hook runs your tests first. If tests fail — save is blocked.
You can't accidentally save broken code.

How to set up:
- File: .git/hooks/pre-commit
- Content: (copy-paste ready script)

When you need this: when AI changes 20 files and you want to
make sure nothing broke before saving.

---

## 2. "Format my code automatically on save"

What happens: every time you save code to git, the hook runs
a formatter (black for Python, prettier for JS). Code always
looks clean without you doing anything.

When you need this: when AI writes code with inconsistent
indentation and you don't want to fix it by hand.

---

## 3. "Don't let me commit passwords"

What happens: hook scans your files for things that look like
passwords, API keys, tokens. If found — blocks the save.

When you need this: always. One leaked API key = someone else's
bill on your card.

---

## 4. "Tell me in Slack/Telegram when deploy is done"

What happens: after code is pushed to the server, a hook sends
a message to your chat. You know it's live without checking.

When you need this: when you deploy and then forget to check
if it actually worked.

---

## 5. "Rebuild the project when I change config"

What happens: when docker-compose.yml or package.json changes,
hook automatically runs the rebuild command.

When you need this: when AI changes your config and you forget
to restart the server. Then spend 30 minutes debugging why
"changes don't work."
```

### Implementation:

- New file: `data/hooks_guide.md` (or `data/hooks_guide_en.md` + `data/hooks_guide_ua.md`)
- Rendered in Tips page or Discover page as a scrollable reference
- Each scenario: title, what happens, how to set up, when you need this
- Copy-paste ready configs (pre-commit hook scripts)
- No code logic — pure content

### Integration with Safety Net:

Safety Net's `pre_save_warnings` is essentially a pre-commit hook done in GUI. Teaching moment opportunity:

After user's 5th save point, hint:
"You've been saving manually 5 times. There's a way to make this automatic — it's called a git hook. Want to see how? [Show Hooks Guide]"

Link to the hooks content in Tips/Discover page.

---

## Architecture Summary

| Gap | New files | Changes to existing | Dependencies |
|---|---|---|---|
| UI Dictionary | `data/ui_elements.py` | `docs_context.py` (new check), `health_page.py` (render), i18n | None |
| SDK Context | `core/context_fetcher.py` | `docs_context.py` (enhance check 6.3), `health_page.py` (UI), i18n | `beautifulsoup4` or none (regex) |
| Hooks Guide | `data/hooks_guide_en.md`, `data/hooks_guide_ua.md` | Tips or Discover page (render), `git_educator.py` (link after 5th save) | None |

## Priority

1. **UI Dictionary** — highest impact for the "7 hours fixing a button" problem. Pure content, fast to build.
2. **Hooks Guide** — pure content, fast to build, bridges the knowledge gap.
3. **SDK Context Fetcher** — most complex, needs HTTP + HTML parsing, but solves a real pain for bleeding-edge SDK users.

## Scope Exclusions

- No browser-based visual dictionary (ASCII only in v1)
- No auto-detection of "which UI element did AI break" (would need DOM parsing)
- No MCP integration for context7 (future)
- No auto-generated hook scripts (copy-paste templates only)
- No package vulnerability scanning (that's Check 3.1 outdated_deps, already exists)
