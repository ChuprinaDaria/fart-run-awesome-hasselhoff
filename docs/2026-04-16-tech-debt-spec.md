# SPEC: Tech Debt Cleanup + Context7 Usage

> Що лишилось після crash-safety фіксу, і як правильно використати context7
> MCP на наступних ітераціях.

## Контекст

**Зроблено 2026-04-16** (commit `13a8e03`, `fix: crash-safety`):

- `core/safety_net.py` — `timeout=30` + graceful fallback у `_git()`
- `core/safety_net.py` — `open()` з `encoding="utf-8"` + `with`
- `core/token_parser.py` (x2), `core/parser.py` — `encoding="utf-8"`
- `gui/app.py` — `finished.connect(deleteLater)` + `isRunning()` guard
  для `_collector_thread` і `_scan_thread`

Не зачепили: монстри, DB singleton, swallowed exceptions, `._conn.execute`
leaks, config race у threads. Все нижче.

## Non-goals

- **Переписування в іншу мову.** Нема CPU-bound hot loops — все I/O
  (git, HTTP, SQLite, Qt). Rust/Go нічого не прискорить.
- **Розбивка monster files >500 LOC.** Не критично, робимо тільки коли
  файл реально заважає змінам.

## Tech Debt Items

### T1 — MCP server: DB singleton / context manager

**Проблема.** `core/mcp_server.py` — кожен tool-call робить `_db()` який
створює новий `HistoryDB()`. SQLite у WAL mode толерує, але якщо агент
шле 2 tool calls швидко — може бути readonly error або lock contention.

**Де болить.** `core/mcp_server.py` — всі 14 tools, функція `_db()`.

**Що робити.** Вибрати один з двох:

1. **Module-level singleton** — створити `_DB_INSTANCE` на старті, усі
   tools беруть його. Плюс: просто. Мінус: не звільняється при shutdown.
2. **Lifespan-managed resource** — MCP `Server` має lifespan hook, DB
   відкривається при старті, закривається при stop. Плюс: чисто.
   Мінус: більше коду.

**Context7 запит.** Перед початком дернути:
```
/mcp context7 get-library-docs /modelcontextprotocol/python-sdk
Topic: lifespan, server resources, singleton patterns
Tokens: ~5000
```

Шукати в доках: `Server.lifespan`, `AsyncExitStack`, приклади з БД.

### T2 — MCP server: startup validation + visible errors

**Проблема.** Якщо юзер додасть наш MCP в `.claude/mcp.json`, а Python
env у нього побитий / модуль `mcp` не встановлений — Claude Code
мовчки скіпне сервер. Юзер не зрозуміє чому "воно не працює".

**Повторюваність.** Саме це сталось з `@upstash/context7-mcp` у моїй
сесії — прописаний, але не завантажився.

**Де болить.** `core/mcp_server.py:408` — `except Exception: pass`.

**Що робити.**

1. На старті MCP сервера логувати версію, шлях, доступні tools в
   stderr (MCP stdio — stderr йде в логи CC).
2. Замінити blanket `except Exception: pass` на
   `except Exception as e: log.exception("tool failed: %s", e)`.
3. Якщо critical dep (SQLite, config) недоступна — fail-fast з
   читабельним повідомленням замість тихого скіпу.

**Context7 запит.**
```
/mcp context7 get-library-docs /modelcontextprotocol/python-sdk
Topic: error handling, logging, startup diagnostics
Tokens: 3000
```

### T3 — Swallowed exceptions без логу (20+ місць)

**Проблема.** Патерн `except Exception: pass` маскує проблеми. Коли
юзер каже "не працює" — в логах порожньо.

**Де болить (за пріоритетом):**

| Файл:рядок | Що ковтається | Критичність |
|------------|---------------|-------------|
| `core/mcp_server.py:408` | Haiku client init | High (див. T2) |
| `core/config.py:85` | Config load | High — юзер не зна чому налашт не працюють |
| `plugins/security_scan/plugin.py:82,91` | Scan errors | Medium |
| `gui/app.py:519,538` | Docker/ports scan | Medium |
| `plugins/docker_monitor/collector.py:74` | Container info | Low |
| `gui/pages/health_page.py:68` | Health render | Low |
| `gui/pages/safety_net_page.py:217,668` | SN dialogs | Low |

**Що робити.** Заміна шаблону:
```python
except Exception:
    pass
# →
except Exception as e:
    log.warning("Context: %s", e)
```

**Context7 запит не потрібен.** Це базовий Python best practice.

### T4 — Leaky `_db._conn.execute(...)` — приватна API у 5 місцях

**Проблема.** `core/status_checker.py:111,122,134,153` і
`gui/app.py:652` лізуть у приватний `_conn` `HistoryDB`. Коли
HistoryDB отримає `close()`, async, або пул — мовчки зламається.

**Що робити.** Додати в `HistoryDB` проксі-методи:

```python
class HistoryDB:
    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def execute_many(self, sql: str, seq: list) -> None:
        self._conn.executemany(sql, seq)
        self._conn.commit()
```

Далі — grep `._conn.execute` і заміна на `.execute`.

**Context7 запит.**
```
/mcp context7 get-library-docs /python/sqlite3
Topic: connection lifecycle, WAL mode, thread safety
Tokens: 2000
```
(SQLite в stdlib — може не бути в Context7, тоді офіційна CPython doc.)

### T5 — Config reference leak у QThreads

**Проблема.** Кожен `QThread` робить `self._config = config`. Якщо
Settings змінить config in-place під час роботи треда — race.

**Де болить.** `gui/app.py` — `DataCollectorThread`, `SecurityScanThread`.
Також пошукати по `gui/pages/*.py` — там є свої `_BuilderThread`.

**Що робити.** `self._config = dict(config)` (shallow copy) у
`__init__` кожного треда. Shallow вистачає — ми не мутуємо nested.

**Context7 запит.**
```
/mcp context7 get-library-docs /pyqt/pyqt5
Topic: QThread lifecycle, thread-safe data passing, moveToThread
Tokens: 3000
```

### T6 — Button double-click replaces live QThread

**Проблема.** У `gui/pages/prompt_helper.py`, `activity.py`,
`snapshots.py`, `smart_rollback.py`:

```python
self._thread = _BuilderThread(...)
self._thread.start()
```

Юзер швидко клікає двічі → старий ref пропадає → GC збирає живий
QThread → segfault або silent memory corruption.

**Що робити (два варіанти):**

1. `button.setEnabled(False)` на старті, `True` в слоті completion.
2. Guard `if self._thread and self._thread.isRunning(): return`.

Обидва треба, вибираємо за UX: disable кнопку — видно юзеру, guard —
на випадок програмного тригера.

**Context7 запит.** Той самий `/pyqt/pyqt5`, тема `QThread`.

## Пріоритет виконання

```
T1 (DB singleton) ────┐
                      ├──> фіксить стабільність MCP
T2 (startup validate) ┘

T3 (swallowed exc) ───────> одразу покращує debuggability

T4 (_conn proxy) ─────────> розблоковує future HistoryDB refactor

T5, T6 (Qt threads) ──────> робити разом, те саме знання
```

**Рекомендоване групування в commits:**

1. `fix: MCP server — singleton DB + startup validation` (T1+T2)
2. `fix: log swallowed exceptions in critical paths` (T3)
3. `refactor: proxy methods in HistoryDB, remove ._conn leaks` (T4)
4. `fix: Qt thread lifecycle — config copy, button guards` (T5+T6)

## Використання Context7 у цьому workflow

### Що таке Context7 у нашому контексті

Два різних речі називаються "Context7":

1. **`@upstash/context7-mcp`** — MCP сервер який дає агенту доки
   сторонніх бібліотек on-demand. Встановлено в
   `~/.claude/mcp.json`, але на момент цієї сесії tools не
   з'явились (fail-silent MCP transport).
2. **`core/context_fetcher.py` (наш код)** — HTTP fetcher URL-ів у
   `docs/context/`. Це наша окрема фіча, **не залежить від Context7
   MCP**, не падає коли MCP не завантажився.

### Чому MCP не завантажився і як перевірити перед наступною сесією

Перевірити перед тим як відкривати Claude Code:

```bash
# 1. npx відпрацьовує?
npx -y @upstash/context7-mcp@latest --help

# 2. Node доступний?
node --version

# 3. Кеш npm не битий?
ls ~/.npm/_npx/ 2>/dev/null | head
```

Якщо npx тягне пакет довше ніж Claude Code чекає — MCP не стартує.
Воркераунд: попередньо встановити глобально:

```bash
npm i -g @upstash/context7-mcp
```

Тоді в `mcp.json`:
```json
"context7": {"command": "context7-mcp", "args": []}
```

### Як правильно звертатись до Context7

Скоротити цикл "питання → код":

```
1. resolve-library-id  "pyqt5"      →  /pyqt/pyqt5
2. get-library-docs    /pyqt/pyqt5  +  topic="QThread lifecycle"
3. читаєш → фіксиш → тести
```

**Не робити:** не слати pure "give me docs for pyqt" — contextless
дамп з'їсть контекст вікно. Завжди з `topic=`.

**Коли Context7 не допомагає:**
- stdlib (sqlite3, subprocess) — йди в офіційну Python docs
- твій власний код — читай репо, не MCP
- GUI/UX рішення — не техніка, а продукт

### Перевіряти наявність перед використанням

У майбутніх сесіях, перед тим як покладатись на Context7:

```
ToolSearch "context7" → якщо порожньо, MCP не живий, використовуй
fallback (офіційні доки через WebFetch або `core/context_fetcher.py`).
```

## Acceptance

Цей spec вважається виконаним коли:

- [ ] T1+T2 commit запушений, MCP сервер логує старт + не ковтає
      помилки tools
- [ ] T3 commit — grep `except Exception:\s*\n\s*pass` повертає
      тільки місця де навмисно (з коментарем чому)
- [ ] T4 commit — grep `\._conn\.execute` повертає 0 рядків поза
      `core/history.py`
- [ ] T5+T6 commit — всі QThread-creating місця мають або
      `setEnabled(False)` або `isRunning()` guard
- [ ] Всі 410+ тестів проходять
- [ ] Ручний smoke test на Linux/macOS (Windows — не критично якщо
      немає тестера)
