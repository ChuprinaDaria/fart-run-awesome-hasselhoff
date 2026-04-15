# SPEC: Activity Log + Environment Snapshots

> "Your AI has amnesia. You don't."
> Фіча для вайбкодерів які кажуть "а шо він зробив?" і "воно було, а тепер нема"

## Проблема

Вайбкодер працює з Claude Code. Після сесії:
- Не знає які файли створені/змінені/видалені і **навіщо вони**
- Не знає які Docker контейнери з'явились/зникли
- Не знає які порти відкрились
- Завтра відкриває проект — а AI "забув" все що було налаштовано
- Колеги питають "як ти це зробив?" — відповідь: "хз, Claude зробив"

## Рішення

Два компоненти:

### 1. Activity Log ("What Did AI Do While You Weren't Looking")

Нова сторінка в sidebar — показує що змінилось в середовищі **людською мовою**.

#### Джерела даних:

**Git changes (основне):**
- `git diff --stat` — які файли змінились, скільки рядків +/-
- `git diff --name-status` — створені (A), змінені (M), видалені (D), перейменовані (R)
- `git log --oneline` — останні коміти
- **Для кожного файлу** — короткий опис людською мовою що це за файл і навіщо він (по розширенню, шляху, контенту):
  - `docker-compose.yml` → "Docker конфігурація — які сервіси запускаються"
  - `requirements.txt` → "Python залежності — що встановлюється"
  - `.env` → "Змінні середовища — паролі, ключі, налаштування"
  - `Dockerfile` → "Docker образ — як збирається контейнер"
  - `*.py` в `migrations/` → "Міграція БД — зміни в структурі бази даних"
  - і т.д. — маппінг патернів до пояснень

**Docker changes:**
- Нові контейнери які з'явились
- Контейнери що зникли/впали
- Нові volumes
- Зміни в мережах

**Port changes:**
- Нові відкриті порти (і хто їх слухає)
- Порти що закрились

**Process changes:**
- Нові процеси (сервери, воркери)
- Процеси що зникли

#### UI:

```
┌─────────────────────────────────────────────────┐
│ 📋 Activity Log                    [Refresh] 🔄 │
├─────────────────────────────────────────────────┤
│ 🕐 Today, 14:35                                 │
│                                                  │
│ 📁 Files Changed (5 files)                       │
│ ┌──────────────────────────────────────────────┐ │
│ │ + docker-compose.yml                         │ │
│ │   Docker config — added Redis service        │ │
│ │                                              │ │
│ │ + src/worker.py (NEW)                        │ │
│ │   Celery worker — processes background tasks │ │
│ │                                              │ │
│ │ ~ requirements.txt (+3 lines)                │ │
│ │   Python deps — added celery, redis, flower  │ │
│ │                                              │ │
│ │ - old_script.py (DELETED)                    │ │
│ │   Was: utility script for data migration     │ │
│ └──────────────────────────────────────────────┘ │
│                                                  │
│ 🐳 Docker Changes                                │
│ ┌──────────────────────────────────────────────┐ │
│ │ + redis:7-alpine (NEW container)             │ │
│ │   Port 6379 — in-memory cache/queue          │ │
│ │                                              │ │
│ │ ● web (restarted 2x)                         │ │
│ │   Might mean: config changed, crashed, OOM   │ │
│ └──────────────────────────────────────────────┘ │
│                                                  │
│ 🔌 Ports                                         │
│ ┌──────────────────────────────────────────────┐ │
│ │ + :6379 (redis) — NEW                        │ │
│ │ + :5555 (flower) — NEW                       │ │
│ │   Flower = Celery monitoring dashboard       │ │
│ └──────────────────────────────────────────────┘ │
│                                                  │
│ 🕐 Today, 11:20                                  │
│ (earlier activity...)                            │
└─────────────────────────────────────────────────┘
```

#### Тон тексту:

- Людська мова, не технічний жаргон
- "Docker config — added Redis service", НЕ "modified docker-compose.yml +15 -2"
- Коротко але інформативно
- Якщо щось потенційно небезпечне — жовтий/червоний колір
  - `.env` змінився → "⚠️ Environment variables changed — check if secrets are OK"
  - Контейнер крашнувся → "🔴 Container died — check logs"

#### Мультиплатформенність:

- Git — працює однаково на Linux/Mac/Windows
- Docker — вже є кросплатформений Docker моніторинг через `docker` Python SDK
- Ports — вже є через `psutil`
- Processes — вже є через `psutil`

---

### 2. Environment Snapshots ("Amnesia Insurance")

Кнопка "📸 Snapshot" — зберігає поточний стан середовища в SQLite.

#### Що зберігається:

```python
@dataclass
class EnvironmentSnapshot:
    id: str                    # UUID
    timestamp: datetime
    label: str                 # user label або auto "Before AI session"

    # Git state
    git_branch: str
    git_last_commit: str       # hash + message
    git_tracked_files: list[str]  # список файлів під git
    git_dirty_files: list[str]    # незакомічені зміни

    # Docker state
    containers: list[dict]     # name, image, status, ports
    volumes: list[str]
    networks: list[str]

    # Ports
    listening_ports: list[dict]  # port, pid, process name

    # Config files checksums
    config_checksums: dict[str, str]  # path → sha256
    # Які конфіги трекати: docker-compose*.yml, .env, Dockerfile,
    # requirements.txt, package.json, pyproject.toml, Makefile
```

#### UI:

```
┌──────────────────────────────────────────────┐
│ 📸 Snapshots                                  │
├──────────────────────────────────────────────┤
│ [📸 Take Snapshot]  [🔍 Compare]              │
│                                               │
│ #3  Today 14:30  "After adding Redis"         │
│ #2  Today 11:00  "Before AI session"          │
│ #1  Yesterday     "Working baseline"          │
│                                               │
│ ─── Compare #2 → #3 ────────────────────────  │
│                                               │
│ 📁 Files: +2 new, ~1 modified, -1 deleted     │
│ 🐳 Docker: +1 container (redis)               │
│ 🔌 Ports: +2 (6379, 5555)                     │
│ ⚙️ Configs: docker-compose.yml CHANGED         │
│                                               │
│ "Looks like AI added a Redis cache and        │
│  Celery worker setup. 3 new Python deps."     │
└──────────────────────────────────────────────┘
```

#### Автоматичні снепшоти:

- При старті fart.run — автоматичний snapshot "App start"
- Опціонально: по таймеру (кожні N хвилин)
- Опціонально: при виявленні нової сесії Claude Code

#### Alerts на основі снепшотів:

- Config file змінився → notification
- Контейнер зник → notification
- Branch змінився → notification

---

### 3. Changelog Watcher (Anthropic Updates)

Окремий компонент — слідкує за оновленнями Claude Code.

#### Джерело:

- `claude --version` — поточна версія
- Парсити https://docs.anthropic.com/en/docs/changelog або RSS/Atom фід
- Або GitHub releases якщо доступно
- Кешувати останню перевірену версію в SQLite

#### UI:

- Popup при виявленні нової версії:
```
┌─────────────────────────────────────────┐
│ 🆕 Claude Code Updated!                 │
│                                          │
│ v1.0.19 → v1.0.20                        │
│                                          │
│ What's new:                              │
│ • New model: Claude Opus 4.6 with 1M ctx │
│ • Fixed: context window management       │
│ • Breaking: old .claude format changed   │
│                                          │
│ ⚠️ Heads up: your CLAUDE.md might need   │
│ re-checking if you relied on old format  │
│                                          │
│ [Got it ✓]          [Show full changelog]│
└─────────────────────────────────────────┘
```

- Індикатор в sidebar або Overview якщо є непрочитане оновлення

---

## Архітектура

### Нові файли:

```
core/
  activity_tracker.py      # збір даних: git, docker diff, ports diff
  snapshot_manager.py       # створення/порівняння снепшотів
  changelog_watcher.py      # перевірка оновлень Claude Code
  file_explainer.py         # маппінг файлів → пояснення людською мовою

gui/pages/
  activity.py               # Activity Log сторінка
  snapshots.py              # Snapshots сторінка (або секція в activity)

i18n/
  en.py  # нові рядки
  ua.py  # нові рядки
```

### Зміни в існуючих файлах:

- `gui/app.py` — додати сторінки в sidebar
- `gui/sidebar.py` — нові пункти меню
- `core/sqlite_db.py` — міграції для snapshots і activity
- `core/models.py` — нові dataclass-и

### Залежності:

- **Нові:** нічого. Все через subprocess (git) і вже наявні бібліотеки (docker SDK, psutil, aiosqlite)
- Git — очікуємо що встановлений (якщо ні — показуємо warning)

---

## Фази реалізації

### Phase 1: Activity Log (core)
- `file_explainer.py` — маппінг патернів файлів до пояснень
- `activity_tracker.py` — збір git diff, docker diff, port diff
- `gui/pages/activity.py` — UI сторінка
- Sidebar інтеграція
- i18n рядки EN/UA
- Тести

### Phase 2: Snapshots
- `snapshot_manager.py` — створення, збереження, порівняння
- SQLite міграція для таблиці snapshots
- UI для створення/перегляду/порівняння
- Auto-snapshot при старті
- Тести

### Phase 3: Changelog Watcher
- `changelog_watcher.py` — перевірка версії Claude Code
- Парсинг changelog (конкретне джерело визначимо при реалізації)
- Popup UI
- Кешування в SQLite
- Тести

---

## Що НЕ робимо

- Не робимо "real-time" відстеження кожної команди AI — це парсинг JSONL і окрема історія
- Не робимо AI-powered пояснення файлів (Haiku API call для кожного файлу) — дорого і повільно, хардкодимо маппінг
- Не робимо diff viewer як в VS Code — показуємо summary людською мовою
- Не інтегруємо ModSecurity чи інші WAF — зенітка проти голубів
- Не робимо awesome-list GUI — таких повно

## Hasselhoff Mode

Коли тема Hasselhoff увімкнена, замість стандартних заголовків:
- "Activity Log" → "The Hoff Sees All"
- "Snapshot" → "Hoff's Polaroid"
- "No changes detected" → "Even the Hoff needs a break sometimes"
- "Container crashed" → "Don't hassle the container... oh wait, it hassled itself"

## Fart Mode (sounds)

- Новий snapshot → маленький "пук"
- Changelog alert → фанфари (або пук-фанфари)
- Container crash → драматичний звук
