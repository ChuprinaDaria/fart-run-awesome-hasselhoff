# SPEC: Haiku UX Overhaul — Everything Explained in Human Language

> "AI зробив щось з твоїм проектом. Тепер ти нарешті зрозумієш що саме."
> Для вайбкодерів які кажуть "а шо це таке" і "чому тут червоне"

## Проблема

Бекенд написаний на ~80%, але UI показує технічний текст який вайбкодер не розуміє.
Ніде не підключений Haiku як пояснювач. Немає API ключа в Settings. Сторінки
вимагають ручного вибору директорії. Немає контексту "де ти зупинився".
Текст не можна скопіювати з більшості сторінок.

## Принципи

- **Все працює без API ключа** — fallback на статичні пояснення з `file_explainer.py`
- **Smart batch** — один виклик Haiku на секцію, не на кожен finding
- **Мова = мова UI** — якщо юзер вибрав UA, Haiku відповідає українською
- **Не переписуємо** — розширюємо існуючий код, використовуємо все що вже є
- **Копіювання всюди** — будь-який текст/warnings можна скопіювати з GUI
- **Промпт-стиль** — "поясни як для людини яка не знає програмування, без жаргону"
- **Rate limit** — 1 виклик на 30 секунд замість 5 хвилин (batch mode не потребує жорсткого ліміту)

## 1. Settings: HaikuHoff

### Що є зараз
`gui/pages/settings.py` — мова, звуки, алерти. Без API ключа.
`core/haiku_client.py` — бере ключ з `ANTHROPIC_API_KEY` env var.
`config.toml` — без секції `[haiku]`.

### Що додаємо

**UI (`settings.py`):**
- Нова група "HaikuHoff" перед групою звуків
- Поле "HaikuHoff Key" — `QLineEdit` з `setEchoMode(Password)`
- Підпис: "Ключ від Claude API — Haiku буде пояснювати все людською мовою" (UA) / "Claude API key — Haiku will explain everything in human language" (EN)
- Кнопка "Test" — викликає `haiku_client.ask("Say OK", max_tokens=5)`, показує результат
- Статус-лейбл: "Connected" / "No key — static mode"

**Config (`config.toml`):**
```toml
[haiku]
api_key = ""
```

**Backend (`haiku_client.py`):**
- Конструктор: `api_key` параметр → env var → config.toml fallback chain
- Змінити `_MIN_INTERVAL` з 300 на 30 секунд
- Новий метод `batch_explain(items: list[str], context: str, language: str) -> dict[str, str]` — один виклик, повертає маппінг item→explanation

## 2. Auto-Project Detection

### Що є зараз
Activity, Health, Snapshots — кожна має свій directory picker.
`~/.claude/projects/` містить сесії по проектах.

### Що додаємо

**Новий модуль `core/project_detector.py`:**
- `detect_projects() -> list[ProjectInfo]` — сканує `~/.claude/projects/`, витягує шляхи, сортує по mtime
- `get_last_project(db: HistoryDB) -> str | None` — останній використаний з SQLite
- `save_last_project(db: HistoryDB, path: str)` — зберігає

**SQLite:**
- Нова таблиця `app_state` (key TEXT PRIMARY KEY, value TEXT) — для `last_project_dir` та інших налаштувань

**UI — синхронізований дропдаун:**
- `gui/widgets/project_selector.py` — `QComboBox` + кнопка "Browse"
- Один інстанс в `app.py`, передається в Activity, Health, Snapshots
- При зміні проекту — `project_changed` сигнал оновлює всі три вкладки
- При старті — автоматично вибирає останній проект, сторінки одразу показують дані

## 3. Activity Log — Таймлайн для людей

### Що є зараз
- `gui/pages/activity.py` — показує одноразовий зріз поточного стану
- `core/activity_tracker.py` — збирає git/docker/port зміни
- `core/file_explainer.py` — маппінг файлів до пояснень (34 патерни + 70 розширень)
- Немає історії, немає контексту, немає часових міток

### Що додаємо

**SQLite — таблиця `activity_log`:**
```sql
CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY,
    project_dir TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    entry_json TEXT NOT NULL,         -- серіалізована ActivityEntry
    haiku_summary TEXT,               -- Haiku пояснення (nullable)
    haiku_context TEXT                 -- "де ти зупинився" (nullable)
);
```

**UI — три блоки зверху вниз:**

1. **"Де ти зупинився"** (виділений блок, жовтий бордер):
   - Витягуємо останні коміти + змінені файли з останньої сесії
   - Haiku промпт: "Ось останні коміти і змінені файли проекту. Поясни в 2-3 реченнях що юзер робив і на чому зупинився. Простими словами, без жаргону. Мовою: {lang}"
   - Fallback: останній коміт + 3 файли з поясненнями з `file_explainer.py`

2. **"Незакінчене"** (червоний бордер, якщо є):
   - Джерело: Health scan findings з `check_id` в `["brake.unfinished", "debt.todos"]`
   - Показуємо перші 3-5 по severity
   - Потребує щоб Health scan хоча б раз пройшов — якщо ні, показуємо "Запусти Health scan щоб побачити незакінчене"

3. **"Таймлайн змін"** (хронологічний список):
   - Часові мітки: "Сьогодні, 14:35", "Вчора, 11:20"
   - При рефреші: зберігаємо `ActivityEntry` в SQLite, порівнюємо з попередньою
   - Smart batch Haiku: "Ось список змін у проекті. Поясни коротко що відбулось, для кожної групи змін — 1-2 речення. Простими словами. Мовою: {lang}"
   - Fallback: `file_explainer.py` пояснення (як зараз, вже працює)
   - Показуємо останні N записів (default 20), скрол для більше

**Копіювання:**
- Кнопка "Copy all" зверху — копіює весь видимий текст у буфер обміну
- Правий клік на будь-якому блоці → "Copy"

## 4. Health — Haiku пояснює код "для дебілів"

### Що є зараз
- `gui/pages/health_page.py` — рендерить findings з Rust крейтів
- `core/health/project_map.py` — `run_all_checks()` повертає `HealthReport`
- `core/haiku_client.py` — є метод `explain_finding()`, ніде не викликається

### Що додаємо

**Smart batch після сканування:**
- Збираємо топ-10 findings по severity (critical → high → medium → low)
- Один промпт Haiku: "Ось проблеми в коді проекту. Для кожної поясни: що це, чому це погано, що робити. Поясни як для людини яка вперше бачить код. Без технічного жаргону. Мовою: {lang}. Формат: номер проблеми — пояснення."
- Парсимо відповідь, вставляємо як додатковий рядок під кожним finding (інший колір, курсив)
- Findings поза топ-10 — показуємо зі статичним `finding.message`
- Fallback: все працює як зараз

**Summary блок зверху результатів:**
- Один Haiku-коментар по всьому скану
- Промпт: "Ось загальна статистика проекту: {summary}. Дай загальну оцінку стану проекту в 2-3 реченнях. Простими словами. Мовою: {lang}"
- Fallback: summary bar з іконками як зараз (залишається в обох випадках)

**Копіювання:**
- Кнопка "Copy all findings" — копіює всі findings з поясненнями як текст
- Кожен finding — правий клік → "Copy"

## 5. Snapshots — "Збереження гри"

### Що є зараз
- `gui/pages/snapshots.py` — список знімків, порівняння з технічними деталями
- `core/snapshot_manager.py` — create/compare/delete працюють
- Незрозуміло для вайбкодера навіщо це і що з цим робити

### Що додаємо

**Підказка зверху сторінки (статичний текст):**
- UA: "Знімки = збереження в грі. Зроби знімок перед тим як AI почне щось міняти. Потім порівняй що було і що стало."
- EN: "Snapshots = game saves. Take one before AI starts changing things. Then compare what was and what became."

**Haiku summary при створенні знімка:**
- При `create_snapshot()` — відправляємо стан (branch, containers, ports, configs) в Haiku
- Промпт: "Ось поточний стан проекту. Опиши його в одному реченні, простими словами. Мовою: {lang}"
- Зберігаємо в SQLite разом зі знімком (нове поле `haiku_label TEXT`)
- В списку знімків показуємо Haiku label замість технічних деталей
- Fallback: branch + containers/ports як зараз

**Haiku пояснення при порівнянні:**
- Збираємо diff, відправляємо Haiku
- Промпт: "Ось різниця між двома станами проекту. Поясни простими словами що змінилось і що це може означати. 3-5 речень. Мовою: {lang}"
- Показуємо зверху блоку порівняння як виділений коментар
- Fallback: технічний diff як зараз

**Копіювання:**
- Кнопка "Copy diff" при порівнянні — копіює повний текст з Haiku поясненням

## 6. Changelog — Haiku пояснює оновлення

### Що є зараз
- `gui/changelog_popup.py` — попап "old → new, [Got it] [Show changelog]"
- `core/changelog_watcher.py` — перевіряє `claude --version`

### Що додаємо

**Haiku пояснення в попапі:**
- Промпт: "Claude Code оновився з версії {old} до {new}. Поясни коротко що може бути нового і чи може щось зламатись в існуючих проектах. 3-5 речень, простими словами. Мовою: {lang}"
- Показуємо в тілі попапу між версіями і кнопками
- Fallback: як зараз — тільки версії і кнопка changelog

## 7. Копіювання — наскрізна фіча

### Що є зараз
- `gui/copyable_table.py` — `CopyableTable(QTableWidget)` з Ctrl+C, використовується тільки в Security

### Що додаємо

**Розширюємо `copyable_table.py`:**
- Новий віджет `CopyableSection(QGroupBox)` — обгортка для будь-якої секції з кнопкою "Copy"
- Метод `get_copyable_text() -> str` — збирає текст з усіх дочірніх QLabel
- Ctrl+C на фокусованій секції — копіює

**Кнопка "Copy all" на кожній сторінці:**
- Activity: копіює "Де ти зупинився" + таймлайн
- Health: копіює всі findings з Haiku поясненнями
- Snapshots: копіює diff з Haiku коментарем
- Security: вже є через CopyableTable, додаємо кнопку "Copy all findings"

## Зміни в існуючих файлах

| Файл | Що змінюється |
|------|---------------|
| `core/haiku_client.py` | `batch_explain()`, rate limit 30s, config.toml fallback |
| `core/config.py` | default `[haiku]` секція |
| `config.toml` | `[haiku]` секція |
| `gui/pages/settings.py` | HaikuHoff група |
| `gui/pages/activity.py` | три блоки, таймлайн, SQLite історія |
| `gui/pages/health_page.py` | Haiku пояснення, summary, copy |
| `gui/pages/snapshots.py` | підказка, Haiku labels, copy |
| `gui/changelog_popup.py` | Haiku пояснення |
| `gui/copyable_table.py` | `CopyableSection` віджет |
| `gui/app.py` | project selector, синхронізація вкладок |
| `core/history.py` | таблиці `activity_log`, `app_state`, поле `haiku_label` в snapshots |
| `i18n/en.py`, `i18n/ua.py` | нові рядки |

## Нові файли

| Файл | Опис |
|------|------|
| `core/project_detector.py` | Сканування `~/.claude/projects/`, last project |
| `gui/widgets/project_selector.py` | Синхронізований дропдаун проектів |

## Що НЕ робимо

- Не парсимо HTML changelog Anthropic — Haiku знає про версії з навчальних даних
- Не робимо real-time стрімінг Haiku відповідей — batch і показуємо коли готово
- Не додаємо AI пояснення для кожного finding — тільки топ-10 по severity
- Не переписуємо існуючий код — тільки розширюємо і додаємо нове
