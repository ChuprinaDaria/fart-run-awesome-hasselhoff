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

### 🐍 Python Scanners

- **Docker security** — privileged containers, docker.sock mounts, host network, root user, :latest tags
- **Git config** — .env files committed to git
- **Dependencies** — pip-audit, npm-audit integration
- **Typosquatting** — Levenshtein distance detection against popular packages + known malicious package database
- **System** — firewall status, SSH config weaknesses, available security updates, sudoers audit, world-writable PATH dirs

### 💰 Token Usage Monitor (for the budget-conscious vibe coder)

Because vibe coding isn't free. Someone pays. Usually you.

- **Real-time token tracking** — parses Claude Code JSONL sessions from `~/.claude/projects/`
- **Cost calculator** — per-model pricing (Opus $5/$25, Sonnet $3/$15, Haiku $1/$5 per M tokens), cache read/write costs
- **Cache efficiency analysis** — shows how much you're saving (or wasting) with prompt caching
- **Model comparison** — "100% Opus today = $X. With Sonnet: $Y. Save $Z. Think about it."
- **Session analytics** — which project is eating your tokens, output/input ratio (is Claude too chatty?), session batching
- **Budget forecasting** — daily average, weekly trends, "you're 50% above average today" warnings
- **What-if analysis** — "what if you used Sonnet for everything?" with actual dollar amounts

### 🧠 AI-Powered Tips (optional, Claude Haiku)

Set `ANTHROPIC_API_KEY` and get personalized advice for ~$0.001 per tip:

- **Smart tips** — Haiku analyzes your actual usage patterns and gives ONE specific, actionable recommendation
- **Model advisor** — "For this task, Sonnet is enough. Save ~$0.15."
- **Security explanations** — plain-language explanations of findings in YOUR project's context

No API key? No problem. Falls back to a rules-based engine with 15+ dynamic tips based on cache efficiency, model selection, session patterns, output verbosity, and project switching.

### 😤 Nag Messages (the passive-aggressive part)

Four escalation levels based on token consumption. Bilingual (EN/UA). Examples from Level 4:

> *"You're like while(true) without break. That's not a feature, it's a bug."*
>
> *"Ти як cron job без sleep interval. Зупинись."*
>
> *"GG. 1.2M tokens. Stand up. Go out. Touch grass. Find a girlfriend. In that order."*

The messages get more aggressive as your token count rises. This is a feature, not a bug.

### 🔍 Scan Engine

- **MCP Server** — use from Claude, Cursor, or any MCP-compatible assistant: `npx fartrun`
- **Security Score** — 0-100 rating on the Overview page with severity breakdown (critical=-20, high=-10, medium=-3, low=-1)
- **Quick Fix suggestions** — "Fix" buttons for common findings (.env in git, firewall inactive, Docker root)
- **SQLite History** — persistent daily stats with weekly trend tracking and text-based bar charts
- **GitHub/Local MD Fetcher** — pulls and caches security advisories, curated tool lists, education resources

### 🖥️ GUI (the unserious part)

A PyQt5 desktop app styled as Windows 95. Because nothing says "your code is insecure" like a dialog box from 1995.

**Pages:**

| Page | What it does |
|------|-------------|
| **Overview** | Token budget bar, cost display, session stats, compact Docker/Ports status, Security Score, nag messages |
| **Security** | Findings table with severity, type, source. Detail panel with explanations and fix instructions |
| **Usage** | Per-session breakdown, daily/weekly stats, model distribution |
| **Analytics** | Cache efficiency bar, model comparison table, project breakdown, weekly trend chart |
| **Tips** | Dynamic recommendations sorted by relevance. AI-powered tip at the top if API key is set |
| **Discover** | Resources and education links from `data/*.md` — no hardcoded content |
| **Settings** | Language (EN/UA), sound mode (Classic/Fart), alert filters, cooldown, notification toggles |
| **Hoff Wizard** | Hasselhoff-themed tool installer. The only page where Hasselhoff appears uninvited |

**Sound modes:**
  - 🎵 **Classic** — severity-based alert sounds (critical = sirens, warning = chime, info = gentle ping)
  - 💨 **Fart** — severity-based flatulence (critical = earth-shattering, warning = thunderclap, info = silent but deadly)

**Win95 Popup Notifications** — critical and warning findings get a proper Win95-style dialog with severity icon (✖ / ⚠ / ℹ), auto-close timer, and an OK button your grandfather would recognize.

**Hasselhoff** — appears in the Setup Wizard and via manual trigger. We reduced his appearances after beta testers reported "Hasselhoff fatigue syndrome." He's still there. Watching. Like your vulnerabilities.

### 📚 Resources & Education

Dynamic content loaded from `data/*.md` files — update the repo, update the resources. No code changes needed.

**Security courses:**

| Language | Platforms |
|----------|-----------|
| 🇺🇦 Ukrainian | Prometheus, Projector, Mate Academy, DOU |
| 🇬🇧 English | Coursera, HackTheBox, TryHackMe, Snyk Learn, OWASP |

**Topics covered:** Docker security, Network security, System hardening, Supply chain attacks, Secrets management

**Also in Discover:**
- Token optimization guides (18 hacks, prompt caching deep dive)
- Claude Code documentation (CLAUDE.md, hooks, slash commands, Agent SDK)
- API & pricing reference (models, batch pricing, fast mode)
- Community links (r/ClaudeCode, Awesome Claude Skills, MCP Servers Directory)

### 🛠️ MCP/Skills Installer

Drop a GitHub URL. Get a security scan. Install with one click.

- **Drop-link install** — paste a GitHub URL for any MCP server or Skill
- **Pre-install security scan** — checks for malicious postinstall scripts, suspicious binaries, obfuscated JS, typosquatting deps
- **API key detection** — auto-detects required env vars from README, shows input fields
- **Curated catalog** — `data/curated.md` with recommended MCP servers and Skills, "Install" button next to each
- **Settings.json integration** — writes directly to `~/.claude/settings.json` with atomic writes (no corruption on crash)

### 🖥️ Cross-Platform

Native support for Linux, macOS, and Windows:

| Feature | Linux | macOS | Windows |
|---------|-------|-------|---------|
| Notifications | notify-send | osascript | PowerShell toast |
| Sound playback | pw-play / paplay / ffplay / aplay | afplay | PowerShell SoundPlayer |
| Firewall check | ufw / nftables / iptables | socketfilterfw / pf | netsh advfirewall |
| System updates | apt / dnf / pacman | softwareupdate | winget |
| SSH audit | /etc/ssh/sshd_config | /etc/ssh/sshd_config | %ProgramData%\ssh\sshd_config |
| Admin elevation | pkexec / sudo | osascript with privileges | PowerShell RunAs |
| Config dir | ~/.config/claude-monitor/ | ~/Library/Application Support/ | %APPDATA%\claude-monitor\ |
| Docker | unix socket | unix socket | npipe |

All strings sanitized against command injection. Because a security scanner with command injection would be... ironic.

-----

## Quick Start

### MCP (for the lazy — i.e. the target audience)

```bash
npx fartrun scan .
```

Or add to your Claude Desktop / Cursor config:

```json
{
  "mcpServers": {
    "fartrun": {
      "command": "npx",
      "args": ["fartrun"]
    }
  }
}
```

Then just ask your AI: *"scan this project for security issues"*

### Desktop GUI (for the aesthetes)

```bash
git clone https://github.com/ChuprinaDaria/fart-run-awesome-hasselhoff.git
cd fart-run-awesome-hasselhoff
pip install -e .
python -m gui.app
```

A Win95 window will appear. Hasselhoff may or may not greet you. Click "Scan". Listen.

### Rust Sentinel (for the fast)

```bash
cd crates/sentinel
maturin build --release
pip install target/wheels/sentinel-*.whl
```

Now your Python scanners use compiled Rust modules. 10x faster than regex in Python. Because your time is valuable. (Your code might not be. Run the scan.)

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

## Architecture

```
fartrun/
├── core/                          # Brain
│   ├── platform.py                # OS detection + backend dispatch
│   ├── platform_backends/         # Linux, macOS, Windows implementations
│   ├── alerts.py                  # Deduplication, cooldown, severity routing
│   ├── calculator.py              # Token cost math (all Claude models)
│   ├── usage_analyzer.py          # Cache efficiency, model comparison
│   ├── tips.py                    # 15+ dynamic tips + optional Haiku AI
│   ├── haiku_client.py            # Claude Haiku API (optional, ~$0.001/call)
│   ├── history.py                 # SQLite daily stats + trends
│   ├── token_parser.py            # JSONL session log parser
│   ├── md_fetcher.py              # GitHub/local MD fetcher with cache
│   ├── mcp_installer.py           # MCP/Skill installer (atomic settings.json)
│   ├── repo_scanner.py            # Pre-install security scan
│   └── nagger/                    # Nag messages + Hasselhoff personality
├── gui/                           # Win95 PyQt5 frontend
│   ├── app.py                     # Main window, sidebar, refresh loop
│   ├── win95_popup.py             # Win95-style notification dialogs
│   ├── fmt_utils.py               # Shared formatting
│   └── pages/                     # Overview, Security, Usage, Analytics, Tips, Discover, Settings, Hoff Wizard
├── plugins/                       # Plugin system
│   ├── docker_monitor/            # Container metrics collector
│   ├── port_map/                  # Port scanner (psutil)
│   └── security_scan/             # Python scanners + Rust sentinel wrappers
├── crates/sentinel/               # Rust security modules (PyO3)
│   └── src/
│       ├── processes.rs           # Cryptominers, reverse shells
│       ├── network.rs             # C2 connections, mining pools
│       ├── filesystem.rs          # Sensitive files, SUID, malware paths
│       ├── crontab.rs             # Suspicious scheduled tasks
│       ├── secrets.rs             # Hardcoded API keys and tokens
│       ├── autostart.rs           # Persistence mechanisms
│       ├── container_escape.rs    # Docker breakout vectors
│       ├── supply_chain.rs        # Lock file integrity
│       ├── git_hooks.rs           # Malicious hook scripts
│       └── env_leak.rs            # Secrets in environment variables
├── data/                          # Dynamic content (update without code changes)
│   ├── curated.md                 # Recommended MCP servers + Skills
│   ├── resources.md               # Docs, guides, community links
│   └── education.md               # Security courses (EN + UA)
├── sounds/                        # Audio feedback
│   ├── classic/                   # Professional alert sounds
│   └── fart/                      # ...you know what these are
├── i18n/                          # Bilingual support (EN / UA)
│   ├── en.py
│   └── ua.py
└── tests/                         # 118 tests
```

-----

## Configuration

`config.toml` — lives in your platform config dir (`~/.config/claude-monitor/` on Linux):

```toml
[general]
refresh_interval = 5
language = "ua"            # "en" or "ua"

[sounds]
enabled = true
mode = "fart"              # "classic" or "fart"
quiet_hours_start = "23:00"
quiet_hours_end = "07:00"

[alerts]
cooldown_seconds = 300
desktop_notifications = true

[plugins.docker_monitor]
enabled = true
cpu_threshold = 80
ram_threshold = 85

[plugins.security_scan]
enabled = true
scan_interval = 3600
scan_paths = ["~"]
```

Quiet hours exist because we learned the hard way that a critical-severity fart at 2 AM wakes up more than just the developer.

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
|Custom Rust security modules               |❌       |❌       |❌      |✅          |
|10 compiled Rust scanners                  |❌       |❌       |❌      |✅          |
|Token usage monitoring                     |❌       |❌       |❌      |✅          |
|AI-powered tips (Haiku)                    |❌       |❌       |❌      |✅          |
|Passive-aggressive nag messages            |❌       |❌       |❌      |✅          |
|Fart sounds                                |❌       |❌       |❌      |✅          |
|Hasselhoff                                 |❌       |❌       |❌      |✅          |
|MCP integration                            |❌       |✅       |❌      |✅          |
|Win95 GUI                                  |❌       |❌       |❌      |✅          |
|Education links (UA + EN)                  |❌       |❌       |❌      |✅          |
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
