# Security Guardian for Vibe Coders — Design Spec

**Date:** 2026-04-14
**Status:** Approved
**Target:** Новачки-вайбкодери, які юзають AI-агенти (Cursor, Copilot, Claude Code) і сліпо приймають згенерований код.

## Problem

AI-агенти можуть генерувати код, який:
- Хардкодить API ключі в `.py`, `.js`, `.txt`, `.yaml`
- Додає шкідливі або typosquat пакети в залежності
- Модифікує autostart файли (`.bashrc`, systemd services)
- Запускає процеси що дзвонять на зовнішні сервери
- Створює persistence через cron jobs або postinstall scripts

Новачки не мають досвіду щоб це помітити. Апка має бути їх security-ментором.

## UX Philosophy

- **Хассельхоф** — секʼюріті-ментор, який пердить від незадоволення
- **Блокуючий діалог** для CRITICAL — юзер НЕ МОЖЕ ігнорувати
- **Людські пояснення** — без жаргону, з контекстом "чому це погано"
- **Освітні посилання** — безкоштовні Coursera курси per category
- **Без автофіксу** — вказуємо де проблема + як фіксити + лінк на курс
- Звуки: fart sounds для алертів (вже є в `sounds/`)

---

## New Scanners

### 1. Secret Scanner (`crates/sentinel/src/secrets.rs`)

**Rust module** — сканує ВСІ папки на компі.

**Що шукає:**
- AWS Access Keys: `AKIA[0-9A-Z]{16}`
- AWS Secret Keys: рядки після `aws_secret_access_key`
- GitHub tokens: `ghp_[A-Za-z0-9]{36}`, `gho_`, `ghs_`, `ghu_`, `github_pat_`
- OpenAI API keys: `sk-[A-Za-z0-9]{20,}`
- Anthropic API keys: `sk-ant-[A-Za-z0-9-]{20,}`
- Stripe keys: `sk_live_`, `sk_test_`, `pk_live_`, `pk_test_`
- Generic secrets: `password\s*=\s*["'][^"']+["']`, `secret\s*=`, `token\s*=`, `api_key\s*=`
- Bearer tokens: `Bearer [A-Za-z0-9-._~+/]+=*`
- Private keys: `-----BEGIN (RSA |EC |DSA )?PRIVATE KEY-----`
- Database URLs: `postgres://`, `mysql://`, `mongodb://` з credentials

**Які файли:**
- `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.rb`, `.go`, `.java`, `.rs`
- `.env`, `.env.local`, `.env.production`
- `.txt`, `.md`, `.yaml`, `.yml`, `.json`, `.toml`, `.cfg`, `.ini`, `.conf`
- `.sh`, `.bash`, `.zsh`

**Skip directories:**
- `/proc`, `/sys`, `/dev`, `/run`, `/snap`
- `node_modules`, `.git/objects`, `__pycache__`, `.venv`, `venv`
- `/usr/lib`, `/usr/share`, `/lib`
- Бінарні файли (перевірка magic bytes)

**Severity:** CRITICAL для всіх знахідок

**Performance:**
- Паралельний walk через rayon
- Ліміт файлу: пропускати файли > 1MB
- Depth limit: 10 рівнів
- Regex compiled один раз, reused

---

### 2. Autostart Persistence Scanner (`crates/sentinel/src/autostart.rs`)

**Rust module** — сканує autostart точки.

**Shell RC файли:**
- `~/.bashrc`, `~/.bash_profile`, `~/.profile`, `~/.zshrc`, `~/.zprofile`
- Шукає: `curl|bash`, `wget|sh`, `eval $(`, `base64 -d`, `/dev/tcp/`, `nc -e`
- Також: нові `export PATH=` що додають підозрілі директорії (`/tmp`, `/dev/shm`)

**Systemd user services:**
- `~/.config/systemd/user/*.service`
- Перевірка ExecStart на підозрілі бінарники (з `/tmp`, unknown)
- Нещодавно створені сервіси (< 24h)

**XDG Autostart:**
- `~/.config/autostart/*.desktop`
- `~/.local/share/applications/*.desktop`
- Перевірка Exec= на підозрілі шляхи та команди
- Hidden=true + NoDisplay=true = підозріло

**Cron (розширення існуючого `crontab.rs`):**
- `@reboot` записи
- Записи що запускають файли з `/tmp`, `/dev/shm`

**Severity:** CRITICAL для curl|bash, reverse shells. HIGH для решти.

---

### 3. Suspicious Package Scanner (розширення `plugins/security_scan/scanners.py`)

**Python** — новий scanner `scan_suspicious_packages()`.

**Що перевіряє:**

*Python packages (requirements.txt, Pipfile, pyproject.toml):*
- Typosquat detection: відстань Левенштейна ≤ 2 від популярних пакетів
- Популярні пакети list: `requests`, `django`, `flask`, `numpy`, `pandas`, `tensorflow`, `pytorch`, `boto3`, `pillow`, `cryptography` тощо (50+)
- Відомі малварні пакети (hardcoded list, оновлюваний)

*NPM packages (package.json):*
- Typosquat від: `react`, `express`, `lodash`, `axios`, `webpack`, `next`, `vue` тощо
- `scripts.postinstall` / `scripts.preinstall` що містять: `curl`, `wget`, `eval`, `exec`, `child_process`, `http.get`, `net.connect`
- Підозрілі залежності з кастомних registry

**Severity:** CRITICAL для відомих малварних пакетів, HIGH для typosquat.

---

### 4. CPU Anomaly Detector (розширення `crates/sentinel/src/processes.rs`)

**Додаємо до існуючого Rust process scanner:**

- Процеси з CPU > 80% тривалістю > 60 секунд
- Whitelist системних процесів: `Xorg`, `gnome-shell`, `kwin`, `firefox`, `chrome`, `code`, `python3`, `node`, `cargo`, `rustc`, `gcc`
- Невідомі процеси (не в whitelist) з CPU > 50% — warning
- Процеси запущені з `/tmp`, `/dev/shm`, `/var/tmp` — незалежно від CPU

**Severity:** HIGH для CPU аномалій, CRITICAL для процесів з /tmp + high CPU.

---

### 5. Extended Process Signatures (розширення `crates/sentinel/src/processes.rs`)

**Нові сигнатури:**

*Tunneling tools (HIGH):*
- `chisel` — TCP tunnel
- `ngrok` — expose local ports
- `cloudflared` — Cloudflare tunnel
- `frpc` — fast reverse proxy
- `bore` — TCP tunnel

*Brute force tools (CRITICAL):*
- `hydra` — password brute force
- `john` — John the Ripper
- `hashcat` — hash cracking
- `medusa` — parallel brute force

*Recon/exploit (HIGH):*
- `nmap` — port scanner
- `masscan` — mass port scanner
- `sqlmap` — SQL injection
- `metasploit` / `msfconsole` — exploit framework

*Process masquerading detection:*
- Ім'я процесу ≠ binary path (наприклад, процес "sshd" але binary з /tmp)
- Процеси з квадратними дужками `[kworker]` але не від root

---

## Critical Alert Dialog

**Новий клас `CriticalAlertDialog` в `gui/pages/security.py`:**

```
╔══════════════════════════════════════════════════╗
║  🚨 ХАССЕЛЬХОФ ДУЖЕ НЕЗАДОВОЛЕНИЙ! 🚨            ║
║                                                  ║
║  {icon} {title}                                  ║
║  {detail — PID, файл, порт тощо}                 ║
║                                                  ║
║  💨 *ПРРРРТ* 💨                                  ║
║                                                  ║
║  ЩО ЦЕ:                                         ║
║  {human explanation — без жаргону}               ║
║                                                  ║
║  ЧОМУ ЦЕ ПОГАНО:                                 ║
║  {risk — attack scenario простою мовою}          ║
║                                                  ║
║  ЯК ФІКСИТИ:                                    ║
║  {fix command — копіпаст}                        ║
║                                                  ║
║  📚 ВИВЧИ ЩОБ ЗРОЗУМІТИ:                        ║
║  {coursera link — клікабельний}                  ║
║                                                  ║
║  [ Зрозумів, піду фіксити ]                      ║
╚══════════════════════════════════════════════════╝
```

- Модальний діалог (блокує GUI до закриття)
- Грає fart sound при появі
- Не зʼявляється повторно для тої ж знахідки (трекінг по finding ID)
- Quiet hours — діалог відкладається, але findings записуються

---

## Coursera Education Links

Додаються в `gui/security_explanations.py` як маппінг category → course URL:

```python
COURSERA_LINKS = {
    "secrets": "https://www.coursera.org/learn/packt-fundamentals-of-secure-software-dqsu3",
    "malware": "https://www.coursera.org/professional-certificates/google-cybersecurity",
    "cybersecurity_intro": "https://www.coursera.org/learn/cybersecurity-for-everyone",
    "python": "https://www.coursera.org/learn/python",
    "frontend": "https://www.coursera.org/learn/developing-frontend-apps-with-react",
    "ai_agents": "https://www.coursera.org/specializations/ai-agents",
    "linux_security": "https://www.coursera.org/learn/securing-linux-systems",
    "docker": "https://www.coursera.org/learn/docker-basics-for-devops",
    "network": "https://www.coursera.org/learn/crypto",
    "llm_security": "https://www.coursera.org/learn/generative-ai-llm-security",
    "supply_chain": "https://www.coursera.org/courses?query=application%20security",
}
```

Кожне пояснення в `EXPLANATIONS` dict отримує додаткове поле `course_url` та `course_title`.

---

## File Map

| Що | Файл | Дія |
|----|------|-----|
| Secret scanner | `crates/sentinel/src/secrets.rs` | NEW |
| Autostart scanner | `crates/sentinel/src/autostart.rs` | NEW |
| Sentinel lib.rs | `crates/sentinel/src/lib.rs` | MODIFY — export нові модулі |
| Sentinel Cargo.toml | `crates/sentinel/Cargo.toml` | MODIFY — додати regex crate |
| Package scanner | `plugins/security_scan/scanners.py` | MODIFY — додати scan_suspicious_packages() |
| CPU anomaly + sigs | `crates/sentinel/src/processes.rs` | MODIFY — розширити |
| Security plugin | `plugins/security_scan/plugin.py` | MODIFY — виклик нових сканерів |
| Explanations + links | `gui/security_explanations.py` | MODIFY — додати нові категорії + coursera |
| Critical dialog | `gui/pages/security.py` | MODIFY — додати CriticalAlertDialog |
| i18n EN | `claude_nagger/i18n/en.py` | MODIFY — нові повідомлення |
| i18n UA | `claude_nagger/i18n/ua.py` | MODIFY — нові повідомлення |

---

## Out of Scope

- Автофікс — тільки показуємо проблему + як фіксити
- ClamAV/YARA інтеграція — занадто heavyweight для вайбкодерів
- Real-time file watching (inotify) — поки scan-based
- Windows support для autostart (registry) — тільки Linux/macOS
