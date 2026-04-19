# 💨 Fartrun & Awesome Hasselhoff

**A security scanner for vibe-coded projects. Finds vulnerabilities. Farts at you. Hasselhoff appears.**

> *"Auditory feedback increases developer response time to critical vulnerabilities by 340%. We chose the most primal auditory signal known to humanity."*
> — Fartrun Institute of Applied Flatulence, 2026 (peer-reviewed by nobody)

![Python](https://img.shields.io/badge/python-3.10+-blue)
![Rust](https://img.shields.io/badge/rust-sentinel_modules-orange)
![Platform](https://img.shields.io/badge/platform-Linux%20|%20macOS%20|%20Windows-lightgrey)
![Hasselhoff](https://img.shields.io/badge/hasselhoff-awesome-ff69b4)
![License](https://img.shields.io/badge/license-Fart%20%26%20Run-brown)

-----

## What is this?

Your AI assistant just wrote 2,000 lines of code. It works. Tests pass. You deploy.

Three days later your API keys are on GitHub trending, your `.env` is public, and someone in a Discord server is showing your database schema to 400 people.

**Fartrun** scans your vibe-coded project and tells you what's wrong. Loudly.

-----

## What it actually does

### 🦀 Rust Sentinel Modules (the serious part)

Ten compiled Rust modules that scan fast and scan deep:

- **processes** — detects cryptominers, reverse shells, suspicious commands, CPU anomalies, process masquerading
- **network** — finds suspicious ESTABLISHED connections (C2, Tor, IRC, mining pools), risky services on 0.0.0.0
- **filesystem** — sensitive file detection (.env, credentials, .key), SUID binaries, malware persistence paths, /tmp executables
- **crontab** — audits cron, systemd timers, launchd plists, Windows Task Scheduler for suspicious commands
- **secrets** — regex-based detection of AWS, GitHub, OpenAI, Anthropic, Stripe, Slack tokens, private keys, DB URLs
- **autostart** — checks shell RC files, systemd services, XDG autostart, LaunchAgents for persistence
- **container_escape** — detects CAP_SYS_ADMIN in container processes, docker.sock exposure, sysrq-trigger access
- **supply_chain** — analyzes lock files for suspicious URLs, HTTP deps, malicious install scripts, MITM vectors
- **git_hooks** — finds pre-commit/post-commit hooks with curl|sh, wget, base64, download-and-execute patterns
- **env_leak** — hunts for API keys and tokens leaked into process environment variables across all running processes

### 🐍 Python Scanners (the sidekick)

Because not everything needs to be compiled at the speed of sound:

- **Docker security** — privileged containers, docker.sock mounts, host network, root user, `:latest` tags (the "I'll pin the version later" crowd, we see you)
- **Git config** — `.env` files committed to git. Yes, people still do this. In 2026.
- **Dependencies** — pip-audit, npm-audit. Because `npm install left-pad` was a warning, not an instruction.
- **Typosquatting** — Levenshtein distance against popular packages + known malicious DB. `requsets` is not `requests`. One will steal your cookies. The other makes HTTP calls.
- **System** — firewall status, SSH config, security updates, sudoers, world-writable PATH dirs. The stuff you configured once in 2019 and never touched again.

### 💰 Token Usage Monitor (the accountant nobody asked for)

Vibe coding isn't free. Someone pays. Usually you. Usually more than you think.

- **Real-time token tracking** — parses Claude Code JSONL sessions from `~/.claude/projects/`. Yes, we read your diaries. Locally.
- **Cost calculator** — Opus $5/$25, Sonnet $3/$15, Haiku $1/$5 per M tokens. Cache read/write costs included because Anthropic isn't running a charity.
- **Cache efficiency** — "Your cache hit rate is 47%. That's like buying a gym membership and going once." Tells you exactly how many dollars you're flushing.
- **Model comparison** — "100% Opus today = $4.20. With Sonnet: $1.80. You could've bought a coffee with the difference. Two coffees if you used Haiku."
- **Session analytics** — which project is eating your tokens, is Claude writing novels instead of code (output/input ratio), are you starting 15 sessions instead of using /continue
- **Budget forecasting** — weekly trends with text-based bar charts that look like they were rendered on a Commodore 64. "You're 50% above your average. Maybe take a walk."
- **What-if analysis** — "What if you used Sonnet for everything?" Spoiler: you'd save enough for a nice dinner. Monthly.

### 🧠 AI-Powered Tips (the expensive fortune cookie)

Set `ANTHROPIC_API_KEY` and get personalized advice for ~$0.001 per tip. That's cheaper than any advice you've ever received from a human, and probably more useful:

- **Smart tips** — Haiku analyzes your actual patterns. Not generic "use caching" — actual "your project X is eating 60% of tokens, use /compact in that session"
- **Model advisor** — "This looks like a refactoring task. Sonnet handles those fine. Save $0.15 and your dignity."
- **Security explanations** — "You have a Django project with SECRET_KEY in .env that's in git. This means anyone with repo access can forge sessions. Fix: `git rm --cached .env`"

No API key? The rules-based engine has 15+ dynamic tips. It's like having a backseat driver for your token spending. Free. Annoying. Correct.

### 😤 Nag Messages (the emotional support you didn't want)

Four escalation levels. Because gentle reminders don't work on developers.

**Level 1** (< 50K tokens) — mild concern:
> *"Tokens spent: 45K. Calories burned: 0. Priorities?"*

**Level 2** (< 150K tokens) — growing worry:
> *"Even vim users exit sometimes. At least accidentally."*

**Level 3** (< 500K tokens) — disappointment:
> *"For these tokens you could've hired a junior. A living one. With legs."*

**Level 4** (> 500K tokens) — intervention:
> *"SYSTEM ALERT: Carbon-based prompt wrapper detected. Needs reboot (sleep)."*
>
> *"Ти як while(true) без break. Це не фіча, це баг."*
>
> *"GG. 1.2M tokens. Stand up. Go out. Touch grass. Find a girlfriend. In that order."*

All messages available in English and Ukrainian. Because passive-aggression transcends language barriers.

### 🏥 Health Scanner (the doctor you can't ignore)

9 phases of automated project analysis. Rust-powered for speed. Tested on 7 real projects with ~80% accuracy (and climbing):

- **Phase 1: Project Map** — file tree, entry points, module graph (hubs, circular deps, orphans), monster files (>500 lines)
- **Phase 2: Dead Code** — unused imports, unused functions/methods, commented-out code, duplicate code blocks
- **Phase 3: Tech Debt** — missing type hints, hardcoded URLs/secrets, TODO archaeology ("from 104 days ago"), error handling smells (bare `except:`, empty `catch`)
- **Phase 4: Brake System** — uncommitted work, test coverage (zero tests = high severity), scope creep detection
- **Phase 5: Git Survival** — commit hygiene (3940-line commits get flagged), branch awareness, gitignore gaps
- **Phase 6: Docs & Context** — README quality, dependency documentation, LLM context summary
- **Phase 7: UI/UX Design** — JSX/TSX lint (buttons without handlers, setState in render)
- **Phase 8: Framework Checks** — Django SECRET_KEY, DEBUG=True, DRF throttling, Docker best practices, npm lockfile
- **Phase 9: Context7 Recommendations** — enriches critical/high findings with real library documentation via Context7 MCP. "No tests found" → actual pytest Getting Started example from official docs.

**Smart false positive prevention:**
- TypeScript `type_identifier` tracking (no more flagging `FormEvent` as unused)
- File-based routing awareness (Expo Router, Next.js, Nuxt — `app/` and `pages/` conventions)
- React Native / HTML primitives excluded from reusable pattern detection
- Non-standard Python venv detection (`pyvenv.cfg`)
- Framework method whitelist (Django, FastAPI, Textual TUI, Qt, pytest)
- SQLAlchemy side-effect imports, alembic migrations, `import pytest`

**Output: HEALTH-REPORT.md** — checklist with severity levels, file:line references, Context7 fix snippets, and "Possible false positives" section. Copy to Claude: *"Fix the issues in HEALTH-REPORT.md"*

### 🔌 MCP Server (19 tools, two transports)

Use from Claude Code, Cursor, Windsurf, or any MCP client:

**stdio** (default — for Claude Code / settings.json):
```bash
fartrun mcp
```

**HTTP+SSE** (for Cursor, web integrations, any HTTP client):
```bash
fartrun mcp --http --port 3001
```

| Tool | Type | What it does |
|------|------|-------------|
| `run_health_scan` | READ | Full 9-phase project audit with Context7 recommendations |
| `get_health_summary` | READ | Critical + high only — quick "what's broken" |
| `get_unused_code` | READ | Dead imports, functions, orphans, duplicates |
| `get_tech_debt` | READ | Missing types, hardcoded values, TODOs, error handling |
| `get_security_issues` | READ | Secrets, misconfigs, gitignore gaps |
| `generate_health_report` | WRITE | Save HEALTH-REPORT.md with checklist |
| `get_status` | READ | Project overview (save points, frozen, stack) |
| `get_activity` | READ | Uncommitted changes, recent commits |
| `detect_project_stack` | READ | Parse manifests, detect libraries |
| `search_code` | READ | Grep-style keyword search |
| `build_prompt` | READ | Vibe one-liner → structured prompt |
| `create_save_point` | WRITE | Git-based save point (commit+tag) |
| `rollback_save_point` | WRITE | Hard-reset to save point (with backup) |
| `freeze_file` / `unfreeze_file` | WRITE | Lock/unlock files in CLAUDE.md |
| `list_save_points` / `list_frozen` / `list_prompts` | READ | History queries |
| `install_context7` / `uninstall_context7` | WRITE | Manage Context7 MCP |

**HTTP endpoints:**
- `GET /health` — server status, version, tool count
- `GET /sse` — Server-Sent Events stream for MCP clients
- `POST /mcp` — JSON-RPC tool calls

### 🔍 Security Scan Engine

- **Security Score** — 0-100 on the Overview page. Critical finding? That's -20 points. You start at 100. Most vibe-coded projects end up somewhere around... let's not talk about it.
- **Quick Fix buttons** — ".env in git? Click Fix. Firewall off? Click Fix. Docker running as root? Click Fix. Existential dread about your code quality? We're working on that one."
- **SQLite History** — tracks your security score over time. The graph usually goes up. If it goes down, that means you installed something. Check what.
- **MD Fetcher** — pulls curated resources from GitHub. Updates itself. Unlike your dependencies.

### 🖥️ GUI (Windows 95 called. It wants its UI back.)

A PyQt5 desktop app that looks like it escaped from 1995. This is intentional. We studied UX extensively and concluded that the most effective way to communicate "your code has problems" is through the aesthetic of an era when code always had problems.

**Pages:**

| Page | What it does | Secret purpose |
|------|-------------|----------------|
| **Overview** | Token budget, costs, Docker/Ports compact, Security Score | Making you feel things about your spending habits |
| **Security** | Findings table, detail panel, fix instructions | The page you should look at but won't |
| **Usage** | Session breakdown, model distribution | Evidence for your therapist |
| **Analytics** | Cache efficiency, trends, weekly bar chart | Proof that Monday you is different from Friday you |
| **Tips** | AI + rules-based recommendations | Unsolicited advice, ranked by how much you need it |
| **Discover** | Resources, courses, community links | All the things you'll bookmark and never read |
| **Settings** | Language, sound mode, alert filters | The Classic/Fart toggle. You know which one you'll pick. |
| **Hoff Wizard** | MCP/Skills installer with Hasselhoff theme | The only page where Hasselhoff appears uninvited |

**Sound modes:**
- 🎵 **Classic** — sirens, chimes, pings. Professional. Boring. Your manager would approve.
- 💨 **Fart** — The Devastator (critical), The Thunderclap (high), The Squeaker (medium), The Whisper (low), The Silent But Deadly (info). Your manager would not approve. Choose this one.

**Win95 Popup Notifications** — critical findings get a proper dialog with ✖ icon. Warning gets ⚠. Info gets ℹ. There's an OK button. It auto-closes in 8 seconds. Just like your attention span for security warnings.

**Hasselhoff** — used to appear for everything. Container started? Hasselhoff. Cache hit rate good? Hasselhoff. You blinked? Hasselhoff. Beta testers staged an intervention. Now he only shows up in the Wizard and when you explicitly summon him. He's still watching though. Always watching.

### 📚 Learn Security (or at least bookmark the links)

Everything loaded from `data/*.md` — update the file, update the app. No releases needed. No PRs for "fixed typo in education link" touching 400 lines of Python.

**For Ukrainian developers** (because cybersecurity education shouldn't require English):

| Platform | What you'll learn | What you'll actually do |
|----------|------------------|------------------------|
| Prometheus | Cybersecurity fundamentals, Linux, networking | Start the course, finish 30%, feel good about yourself |
| Projector | DevOps, DevSecOps, infrastructure | Add to bookmarks. Forever. |
| Mate Academy | Security basics | Tell yourself "next month" |
| DOU | Practical articles | Read during standup |

**For English speakers:**

| Platform | Style | Pain level |
|----------|-------|-----------|
| Coursera | Academic, certificates | Low (video lectures, pajamas) |
| HackTheBox | Hands-on, CTF-style | Medium (you will feel stupid, this is normal) |
| TryHackMe | Guided labs | Medium-low (hand-holding with purpose) |
| Snyk Learn | Interactive, short | Low (bite-sized guilt trips) |
| OWASP | Reference docs | High (reading OWASP Top 10 is a rite of passage) |

**Topics:** Docker security, Network security, System hardening, Supply chain attacks, Secrets management. Everything you need to know to feel slightly less anxious about your `docker run --privileged` habits.

### 🛠️ MCP/Skills Installer (drop link, pray, install)

The Hasselhoff Wizard, but useful:

1. **Paste a GitHub URL** — any MCP server or Claude Code skill
2. **Fartrun scans it first** — because installing unscanned code from the internet is how we got here in the first place. Checks for malicious postinstall scripts, suspicious binaries, obfuscated JS (if your dependency is one long line, we have questions), typosquatting
3. **API key detection** — reads the README, finds `OPENAI_API_KEY` or whatever, shows you input fields. Like a concierge, but for environment variables
4. **One-click install** — writes to `~/.claude/settings.json`. Atomically. Because the last thing you need is a corrupted settings file after a crash during install of a tool called "fartrun"
5. **Curated catalog** — `data/curated.md` has recommended MCP servers and Skills with "Install" buttons. We vetted these. We scanned these. We still don't fully trust these. Neither should you.

### 🖥️ Cross-Platform (yes, even Windows)

Because bad code doesn't discriminate by operating system:

| What we check | Linux | macOS | Windows |
|--------------|-------|-------|---------|
| Notifications | notify-send | osascript | PowerShell toast |
| Fart delivery | pw-play / paplay / aplay | afplay | PowerShell SoundPlayer |
| Firewall | ufw / nftables / iptables | socketfilterfw / pf | netsh advfirewall |
| "You have updates" | apt / dnf / pacman | softwareupdate | winget |
| SSH audit | /etc/ssh/sshd_config | /etc/ssh/sshd_config | %ProgramData%\ssh\sshd_config |
| Sudo/admin | pkexec / sudo | osascript privileges | PowerShell RunAs |
| Config lives in | ~/.config/claude-monitor/ | ~/Library/Application Support/ | %APPDATA%\claude-monitor\ |
| Docker talks via | unix socket | unix socket | named pipe (npipe) |

All user-facing strings are sanitized against command injection. We tested this. A security scanner with command injection would be the kind of irony that ends careers.

-----

## Quick Start

### MCP — stdio (Claude Code / settings.json)

```json
{
  "mcpServers": {
    "fartrun": {
      "command": "fartrun-mcp"
    }
  }
}
```

Then ask your AI: *"run a health scan on this project"* or *"generate a health report"*

### MCP — HTTP (Cursor / Windsurf / web)

```bash
fartrun mcp --http --port 3001
```

```json
{
  "mcpServers": {
    "fartrun": {
      "url": "http://localhost:3001/sse"
    }
  }
}
```

Check it's alive: `curl http://localhost:3001/health`

### CLI (for humans)

```bash
git clone https://github.com/ChuprinaDaria/fart-run-awesome-hasselhoff.git
cd fart-run-awesome-hasselhoff
pip install -e ".[http]"
```

```bash
# Health scan → MD report
fartrun scan /path/to/project

# Save point before risky changes
fartrun save "before refactoring auth"

# Rollback if everything breaks
fartrun rollback 1
```

### Desktop GUI (for the aesthetes)

```bash
python -m gui.app
```

A Win95 window will appear. Hasselhoff may or may not greet you. Click "Scan". Listen.

### Rust Health Modules (for the fast)

```bash
cd crates/health
pip install maturin
maturin develop --release
```

Now your health scanner uses compiled Rust modules for file tree, dead code, module map, duplicates, and more. 10-50x faster than pure Python AST parsing.

-----

## Severity Levels

|Level   |Icon|Classic Sound |Fart Sound           |Meaning                             |
|--------|----|--------------|---------------------|------------------------------------|
|Critical|💀   |Air raid siren|The Devastator       |Your secrets are already on Pastebin|
|High    |🔴   |Alarm bell    |The Thunderclap      |Someone will find this. Soon.       |
|Medium  |🟡   |Warning beep  |The Squeaker         |Not great, not terrible             |
|Low     |🔵   |Gentle ping   |The Whisper          |Technically a finding. Relax.       |
|Info    |ℹ️   |Soft chime    |The Silent But Deadly|Good to know. Carry on.             |

-----

## Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Health scanner (AST) | **Rust** + tree-sitter + oxc | Fast parsing of Python/JS/TS/TSX across thousands of files |
| Health scanner (logic) | **Python 3.11+** | Framework checks, Context7 integration, report generation |
| MCP server | **Python** + mcp SDK | stdio + HTTP/SSE transports, 19 tools |
| HTTP transport | **Starlette** + **Uvicorn** | ASGI server for Cursor/web MCP clients |
| Documentation enrichment | **Context7 MCP** | Real-time library docs for fix recommendations |
| GUI | **PyQt5** | Win95 aesthetic. Peak design. |
| Security scanner | **Rust** (sentinel modules) | Process/network/filesystem/secrets scanning |
| Database | **SQLite** | Save points, history, frozen files |
| Build | **maturin** | Rust → Python wheel via PyO3 |

## Architecture (for people who actually read this section)

```
fartrun/
├── core/                          # The brain. Doesn't fart. Just thinks.
│   ├── health/                    # 🏥 Health scanner — 9 phases of project analysis
│   │   ├── project_map.py         # Orchestrator. Runs all phases. Returns HealthReport.
│   │   ├── dead_code.py           # Phase 2: unused imports/functions (wraps Rust)
│   │   ├── tech_debt.py           # Phase 3: missing types, error handling (wraps Rust)
│   │   ├── brake_system.py        # Phase 4: uncommitted work, test health, scope creep
│   │   ├── git_survival.py        # Phase 5: commit hygiene, branches, gitignore
│   │   ├── docs_context.py        # Phase 6: README quality, dependency docs
│   │   ├── ui_ux_design.py        # Phase 7: JSX/TSX lint
│   │   ├── framework_checks.py    # Phase 8: Django, Docker, frontend best practices
│   │   ├── context7_recommendations.py  # Phase 9: Context7 docs for fix suggestions
│   │   ├── report_md.py           # Markdown report generator (checklist + FP warnings)
│   │   ├── models.py              # HealthReport, HealthFinding dataclasses
│   │   └── tips.py                # Human-friendly messages. "This isn't a file, it's a novel."
│   ├── mcp/                       # 🔌 MCP server — 19 tools, stdio + HTTP
│   │   ├── server.py              # Server instance, stdio_server + HTTP/SSE transport
│   │   ├── tools/                 # Tool modules (self-registering via @register)
│   │   │   ├── health.py          # run_health_scan, get_health_summary, generate_health_report
│   │   │   ├── status.py          # get_status, get_activity, search_code, detect_stack
│   │   │   ├── save_points.py     # create_save_point, rollback_save_point
│   │   │   ├── frozen.py          # freeze_file, unfreeze_file
│   │   │   ├── prompt.py          # build_prompt (vibe text → structured prompt)
│   │   │   └── context7_install.py # install/uninstall Context7 MCP
│   │   ├── helpers.py             # ok(), err(), json_block(), resolve_project_dir()
│   │   └── state.py               # SQLite singleton shared across tool calls
│   ├── platform.py                # "What OS am I on?" → dispatch
│   ├── platform_backends/         # Linux, macOS, Windows. All equally vulnerable.
│   ├── stack_detector.py          # Parse package.json/pyproject.toml → detected libraries
│   ├── context7_mcp.py            # Context7 registration + directive generation
│   ├── prompt_builder.py          # Vibe text → structured prompt with Context7 directives
│   ├── safety_net/                # Save points: git commit+tag, rollback with backup
│   ├── frozen_manager.py          # Don't Touch list → CLAUDE.md sync
│   ├── calculator.py              # Token cost math. The bad news machine.
│   ├── usage_analyzer.py          # Cache efficiency. The "I told you so" module.
│   ├── haiku_client.py            # Claude Haiku API. ~$0.001/call. Cheapest therapist.
│   ├── history.py                 # SQLite. Remembers everything. Forgives nothing.
│   ├── token_parser.py            # Reads your Claude JSONL diaries. Judges silently.
│   └── nagger/                    # Nag messages + Hasselhoff. The emotional core.
├── crates/health/                 # 🦀 Rust health modules (PyO3 → Python)
│   └── src/
│       ├── dead_code.rs           # Unused imports/definitions via tree-sitter AST
│       ├── file_tree.rs           # File count, extensions, directory sizes
│       ├── module_map.rs          # Import graph, hub modules, circular deps, orphans
│       ├── monsters.rs            # Large files (>500 lines)
│       ├── duplicates.rs          # Code duplication detection
│       ├── reusable.rs            # Repeated JSX patterns (extract into components)
│       ├── tech_debt.rs           # Missing types, error handling, hardcoded values
│       ├── overengineering.rs     # Single-method classes, deep nesting
│       ├── common.rs              # Shared: skip dirs, venv detection, source extensions
│       └── lib.rs                 # PyO3 module exports
├── crates/sentinel/               # 🦀 Rust security scanner
│   └── src/                       # 10 modules: processes, network, secrets, supply_chain...
├── gui/                           # Win95 PyQt5. Peak aesthetic.
│   ├── app.py                     # Main window + sidebar
│   ├── pages/                     # 8 pages + health scan page
│   └── win95_popup.py             # ✖ ⚠ ℹ — the holy trinity of 1995
├── plugins/                       # Docker monitor, port map, security scan
├── data/                          # MD files for education/resources/curated MCP
├── sounds/                        # classic/ + fart/ — your manager's opinion varies
├── i18n/                          # EN + UA. Passive-aggression is multilingual.
└── tests/                         # Tests. More tests than some projects have lines of code.
```

-----

## Configuration

`config.toml` lives in your platform config dir. On Linux that's `~/.config/claude-monitor/`. On macOS it's somewhere in `~/Library/` because Apple likes hiding things. On Windows it's `%APPDATA%` because Microsoft likes hiding things differently.

```toml
[general]
refresh_interval = 5       # seconds. Your anxiety refreshes faster.
language = "ua"            # "en" or "ua". Nag messages hit different in Ukrainian.

[sounds]
enabled = true             # set to false if you value your marriage
mode = "fart"              # "classic" or "fart". We know which one you picked.
quiet_hours_start = "23:00"
quiet_hours_end = "07:00"  # because a critical-severity fart at 2 AM wakes up
                           # more than just the developer. We learned this.

[alerts]
cooldown_seconds = 300     # minimum time between farts for the same finding
desktop_notifications = true

[plugins.docker_monitor]
enabled = true
cpu_threshold = 80         # percent. Your container is sweating.
ram_threshold = 85         # percent. Your container is drowning.

[plugins.security_scan]
enabled = true
scan_interval = 3600       # seconds between full scans. Paranoia is configurable.
scan_paths = ["~"]         # where to look. "~" means everywhere. Brave.
```

-----

## Philosophy

Vibe coding is the programming equivalent of a fart in an elevator. It's fast, it's effortless, everyone pretends it didn't happen, and someone else deals with the consequences.

Fartrun is the person who says "dude, that was you."

Most security tools assume you understand CVE scores, OWASP categories, and CVSS vectors. Fartrun assumes you copy-pasted code from Claude and want to know if you're about to get hacked. That's it.

The Hasselhoff is there because every project needs a spiritual guardian. David Hasselhoff has survived Baywatch, a talking car, eating a cheeseburger on the floor drunk, and performing on the Berlin Wall in a light-up jacket. If he can survive all that, your codebase might survive too. Maybe. Run the scan first.

-----

## Why Fartrun and not [other scanner]?

|Feature                                    |ScanVibe|Vibeship|Aikido |**Fartrun**|
|-------------------------------------------|--------|--------|-------|-----------|
|Scans locally (no code leaves your machine)|❌       |❌       |❌      |✅          |
|Full project health scan (9 phases)        |❌       |❌       |partial|✅          |
|Dead code detection (AST-based)            |❌       |❌       |❌      |✅          |
|Fix recommendations from real docs (Context7)|❌    |❌       |❌      |✅          |
|MD report with checklist for AI            |❌       |❌       |❌      |✅          |
|MCP server (19 tools, stdio + HTTP)        |❌       |✅       |❌      |✅          |
|Custom Rust security modules               |❌       |❌       |❌      |✅          |
|Framework-aware (Django, Next.js, Expo, FastAPI)|❌  |❌       |partial|✅          |
|Tells you how much money you're burning    |❌       |❌       |❌      |✅          |
|AI tips that cost less than a gumball      |❌       |❌       |❌      |✅          |
|Insults you in Ukrainian                   |❌       |❌       |❌      |✅          |
|Fart sounds                                |❌       |❌       |❌      |✅          |
|Hasselhoff                                 |❌       |❌       |❌      |✅          |
|Win95 GUI                                  |❌       |❌       |❌      |✅          |
|Teaches you security (UA + EN)             |❌       |❌       |❌      |✅          |
|Free                                       |partial |partial |partial|**forever**|
|Sends your code to someone's server        |✅       |✅       |✅      |**never**  |

Your code stays on your machine. Always. No cloud. No telemetry. No "we only use it to improve our service." Just a local scan and a fart.

-----

## The Name

Five layers deep. Because we're nerds.

1. **fart + run** = "dealt it and bolted" 💨🏃
1. **fart + run** = a perfectly normal CLI command. `fartrun scan .` Type it with a straight face in a meeting. We dare you.
1. **Fart & Run License** = the only honest software license
1. **fast + run** = one typo away from a legitimate tool name
1. **FORTRAN** = anagram of one of the oldest programming languages (1957). Because security vulnerabilities are also timeless.

-----

## Buy Me a Toilet Paper 🧻

This project is free. Forever. No premium tier. No "enterprise edition." No "contact sales."

If Fartrun saved you from mass embarrassment, you can buy me toilet paper:

[![Buy Me a Toilet Paper](https://img.shields.io/badge/donate-🧻%20toilet%20paper-yellow)](YOUR_DONATE_LINK)

All donations go toward toilet paper, coffee, and finding the perfect fart sound for the next severity level.

-----

## Contributing

PRs welcome. Especially if you:

- Found a better fart sound (WAV/OGG, must be royalty-free, must be funny)
- Want to add a new sentinel module in Rust
- Have a Hasselhoff fact that needs to be in the codebase
- Spotted a bug (ironic, for a security scanner)
- Can translate nag messages to a new language (bonus points for maximum passive-aggression)
- Want to add security courses for your country to `data/education.md`
- Think the nag messages aren't aggressive enough (we have a Level 5 branch. It's... a lot.)

-----

## Fart & Run License

```
FART & RUN LICENSE v1.0

Copyright (c) 2026 Lazysoft

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software, to use, copy, modify, merge, publish, distribute, and/or
sublicense it, subject to the following conditions:

1. You may fart and run, but you must attribute the original farter.
2. You may not use this software to mass-fart on production servers you
   don't own. That's not a vulnerability scan, that's just rude.
3. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
   If it fails to detect a vulnerability, that's on you for trusting
   a scanner named after flatulence.
4. Hasselhoff appearances are provided on an AS-AVAILABLE basis and
   are not guaranteed in all runtime environments.
5. Nag messages are a feature. Disabling them voids your warranty
   (you never had one).
6. The "Silent But Deadly" sound mode is exactly what it sounds like.
   And doesn't sound like.

THE AUTHORS SHALL NOT BE LIABLE FOR ANY EMBARRASSMENT, TERMINATED
EMPLOYMENT, OR SOCIAL CONSEQUENCES ARISING FROM FART SOUNDS PLAYING
DURING VIDEO CALLS, OPEN OFFICES, OR CLIENT DEMONSTRATIONS.
```

-----

## Star This Repo ⭐

You've read this far. You know you want to. Hit the star. Tell your friends. Spread the flatulence.

-----

<p align="center">
  <i>Made with 💨 in Wrocław, Poland</i><br>
  <i>Lazysoft — "it works, we checked (with farts)"</i>
</p>
