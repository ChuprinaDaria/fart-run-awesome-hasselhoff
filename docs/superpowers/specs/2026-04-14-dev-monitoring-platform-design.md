# Dev Monitoring Platform — Design Spec

**Дата:** 2026-04-14
**Проект:** claude-monitor (розширення)
**Автор:** Даша Чупріна / Claude

## Огляд

Розширення `claude-monitor` з plugin-системою для моніторингу локального dev-середовища: Docker контейнери, порти/сервіси, безпека, git-здоров'я, стан інструментів, прогнозування ресурсів.

## Roadmap

- **MVP (v1):** Docker Monitor + Port/Service Map + Security Scan
- **v2:** Git Health + Dev Environment Health
- **v3:** Resource Forecasting

## Архітектурні рішення

| Рішення | Вибір |
|---------|-------|
| Мова | Python 3.11+ |
| TUI | Textual |
| БД | SQLite (один файл `monitor.db`) |
| Docker API | `docker` Python SDK |
| Мережа/процеси | `psutil` |
| Security scans | `pip-audit`, `npm audit`, `psutil`, власні перевірки |
| Звук | `paplay` / `aplay` + звуки з claude-nagger |
| Notifications | `notify-send` |
| Конфіг | TOML (`config.toml`) |
| Пакетування | `pyproject.toml`, entry point `claude-monitor` |
| Архітектура | Plugin-based (ядро + модулі) |

---

## 1. Архітектура ядра

### Структура проекту

```
claude-monitor/
├── core/
│   ├── app.py              # Textual App, реєстрація плагінів
│   ├── plugin.py           # Базовий клас Plugin (ABC)
│   ├── db.py               # SQLite менеджер (міграції, спільний доступ)
│   ├── alerts.py           # Алерт-система (notify-send + звуки)
│   └── config.py           # TOML конфіг
├── plugins/
│   ├── docker_monitor/     # MVP
│   ├── port_map/           # MVP
│   ├── security_scan/      # MVP
│   ├── git_health/         # v2
│   ├── dev_env/            # v2
│   └── resource_forecast/  # v3
├── sounds/                 # Пердежі та алерт-звуки
├── monitor.db              # SQLite
└── config.toml
```

### Plugin API

Кожен плагін реалізує базовий клас:

- `name` / `icon` — ідентифікація для табу в TUI
- `collect()` — async збір метрик, викликається по інтервалу
- `render()` — Textual Widget для відображення
- `get_alerts()` — перевірка порогів, повертає список алертів
- `migrate(db)` — створення своїх таблиць в SQLite

### Конфігурація (config.toml)

```toml
[general]
refresh_interval = 5  # секунди
sound_enabled = true

[plugins.docker_monitor]
enabled = true
cpu_threshold = 80
ram_threshold = 85
alert_on_exit = true

[plugins.port_map]
enabled = true

[plugins.security_scan]
enabled = true
scan_interval = 3600  # раз на годину
```

---

## 2. Docker Monitor Plugin (MVP)

### Збір даних

Docker SDK for Python, підключення через Unix socket. Інтервал: 5 секунд.

**Метрики:**
- Список контейнерів: name, image, status, created, health check
- CPU % / RAM usage / RAM limit / Net I/O / Disk I/O (`container.stats(stream=False)`)
- Порти: host_port -> container_port mappings
- Restart count, last exit code

### SQLite таблиці

- `docker_containers` — поточний стан (upsert по container_id)
- `docker_metrics` — історія CPU/RAM за останні 24 год (для sparkline графіків)
- `docker_events` — старти, стопи, краші, рестарти (для timeline)

### TUI панель

```
┌─ Docker Containers ──────────────────────────────────────┐
│ NAME         STATUS    CPU%  RAM     PORTS     HEALTH    │
│ ● postgres   running   2.3%  256MB   5432→5432  healthy  │
│ ● redis      running   0.8%  48MB    6379→6379  —        │
│ ◉ worker     running  89.1%  1.2GB   —          —        │ ← червоний, CPU > 80%
│ ○ nginx      exited    —     —       —          —        │ ← сірий
├─ Events ─────────────────────────────────────────────────┤
│ 14:23  worker restarted (exit code 137, OOM killed)      │
│ 14:20  nginx stopped                                     │
└──────────────────────────────────────────────────────────┘
```

### Алерти

- Контейнер впав → notify-send + пердіж
- CPU > поріг → notify-send (жовтий)
- RAM > поріг → notify-send (червоний)
- Health check unhealthy → notify-send + звук
- Restart loop (3+ рестарти за 5 хв) → гучний алерт

---

## 3. Port/Service Map Plugin (MVP)

### Збір даних

`psutil` для мережевих з'єднань + Docker SDK для маппінгу порт→контейнер.

**Метрики:**
- Всі listening порти (TCP/UDP) через `psutil.net_connections()`
- PID → process name, cmdline
- Маппінг: порт належить Docker-контейнеру чи host-процесу
- Конфлікти: два процеси хочуть один порт
- Auto-discovery проектів: по `cwd` процесу визначаємо директорію = проект

### SQLite таблиці

- `port_services` — поточний стан (port, protocol, pid, process, container_name, project)
- `port_history` — коли сервіс піднявся/впав

### TUI панель

```
┌─ Port Map ───────────────────────────────────────────────┐
│ PORT   PROTO  PROCESS       CONTAINER   PROJECT   STATUS │
│ 3000   TCP    node          —           кафе      ● UP   │
│ 5432   TCP    postgres      postgres    —         ● UP   │
│ 6379   TCP    redis-server  redis       —         ● UP   │
│ 8000   TCP    uvicorn       —           sloth     ● UP   │
│ 8080   TCP    nginx         nginx       skrynia   ● UP   │
│ ⚠ 3000  TCP   node          —           nexelin   CONFLICT│
├─ Summary ────────────────────────────────────────────────┤
│ 12 ports listening │ 1 conflict │ 5 Docker │ 3 host     │
└──────────────────────────────────────────────────────────┘
```

### Алерти

- Конфлікт портів → notify-send + пердіж
- Очікуваний сервіс не слухає (postgres зник з 5432) → алерт

---

## 4. Security Scan Plugin (MVP)

### Модулі сканування

Сканування за розкладом (раз на годину + on-demand).

**4.1 Docker Security:**
- Контейнери з `--privileged`
- Docker socket змонтований всередину контейнера
- Контейнери з `network_mode: host`
- Образи без тегу (`:latest`)
- Root user всередині контейнера

**4.2 Конфігурації та файли:**
- `.env` файли в git (`git ls-files` перевірка)
- Файли з широкими permissions (777, world-readable secrets)
- SSH ключі без passphrase (перевірка заголовку)
- Відкриті порти доступні ззовні (0.0.0.0 vs 127.0.0.1)

**4.3 Залежності:**
- Python: `pip-audit` для кожного venv/requirements.txt
- Node: `npm audit --json` для кожного package.json
- Парсинг CVE, severity (critical/high/medium/low)

**4.4 Мережа:**
- Established з'єднання назовні — незнайомі IP/порти
- Процеси що слухають на 0.0.0.0 замість 127.0.0.1
- DNS резолви на підозрілі домени (опціонально)

### SQLite таблиці

- `security_findings` — type, severity, description, source, first_seen, resolved_at
- `security_scans` — timestamp, duration, findings_count

### TUI панель

```
┌─ Security ──────────────────────────────────── Last: 5m ago ┐
│ 🔴 CRITICAL (2)  🟠 HIGH (3)  🟡 MEDIUM (7)  ⚪ LOW (4)     │
├──────────────────────────────────────────────────────────────┤
│ 🔴 .env committed in sloth-all (passwords.env)              │
│ 🔴 CVE-2024-1234 in requests==2.28.0 (кафе/requirements)    │
│ 🟠 postgres container runs as root                           │
│ 🟠 port 5432 exposed on 0.0.0.0 (not 127.0.0.1)            │
│ 🟠 3 npm high-severity vulns in nexelin_web                  │
│ 🟡 redis container uses :latest tag                          │
│ 🟡 SSH key ~/.ssh/id_rsa has no passphrase                   │
├─ Trend ──────────────────────────────────────────────────────┤
│ ▂▃▅▃▂▂▃ findings over 7 days (improving ↓)                  │
└──────────────────────────────────────────────────────────────┘
```

### Алерти

- Новий CRITICAL finding → notify-send + пердіж
- `.env` в git → негайний алерт
- Нова CVE (critical/high) в залежностях → алерт

---

## 5. Алерт-система

### Централізована через `core/alerts.py`

Кожен плагін повертає алерти через `get_alerts()`, ядро обробляє.

### Alert model

```python
@dataclass
class Alert:
    source: str        # "docker", "security", "ports"
    severity: str      # "critical", "warning", "info"
    title: str         # короткий заголовок
    message: str       # деталі
    sound: str | None  # назва звуку або None
```

### Канали доставки

- **TUI:** колір рядка (червоний/жовтий), badge на табі з кількістю алертів
- **Desktop:** `notify-send` з іконкою по severity
- **Звук:** `paplay` / `aplay`

### Звукова схема

| Severity | Звук |
|----------|-------|
| critical | гучний пердіж (контейнер крашнувся, CVE critical) |
| warning  | тихий пердіж (CPU > поріг, порт конфлікт) |
| info     | короткий "пук" (контейнер стартанув, скан завершився) |

### Дедуплікація та cooldown

- Один алерт не повторюється частіше ніж раз на 5 хв
- Quiet hours: вночі без звуку

```toml
[alerts]
cooldown_seconds = 300
desktop_notifications = true
sound_enabled = true
quiet_hours = ["23:00", "07:00"]
```

---

## 6. v2 — Git Health Plugin

- Сканує git-репо в налаштованих директоріях
- Незакомічені зміни, unpushed коміти, stale бранчі (>30 днів)
- Розмір `.git/`, великі файли в історії
- Таб з таблицею репо і їхнім "здоров'ям"

## 7. v2 — Dev Environment Health Plugin

- Версії: Python, Node, Docker, Docker Compose, npm, pip
- Порівняння з latest stable (чи outdated)
- Broken symlinks в `~/bin/`
- Disk usage по проектах (топ-10 найважчих)
- venv-и які давно не юзались

## 8. v3 — Resource Forecasting Plugin

- Збирає CPU/RAM/Disk метрики в SQLite з часом
- Лінійна екстраполяція: "диск закінчиться через ~12 днів"
- RAM leak detection: процес стабільно росте
- Sparkline графіки трендів за день/тиждень
- Алерт коли прогноз показує проблему в найближчі 48 год

---

## Залежності (MVP)

```
textual>=0.40
docker>=7.0
psutil>=5.9
pip-audit>=2.6
tomli>=2.0  # Python 3.11 має tomllib вбудований
aiosqlite>=0.19
```

## Міграція з поточного claude-monitor

Існуючий функціонал (парсинг сесій Claude, PostgreSQL дашборд) залишається як є. Новий plugin-based TUI — окремий entry point. Поступова міграція існуючого дашборду в плагін `claude_sessions` — опціонально, в майбутньому.
