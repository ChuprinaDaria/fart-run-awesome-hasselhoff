# Dev Health Checks — Phase 1: Project Map

> "Дати людині карту її власного проєкту."

## Goal

Одна кнопка "Scan Project" — сканує директорію проєкту, показує 5 checks людською мовою з severity badges. Вайбкодер бачить що в нього є, де entry points, які файли-монстри, і чому `utils.py` — найважливіший файл.

## Architecture

### Rust crate: `health`

Новий crate, окремий від sentinel. PyO3 + maturin build.

```
crates/health/
  Cargo.toml                # pyo3, tree-sitter, tree-sitter-python, tree-sitter-javascript, tree-sitter-typescript, rayon, ignore
  pyproject.toml             # maturin build config
  src/
    lib.rs                   # PyO3 module: 4 scan functions + result structs
    file_tree.rs             # Check 1.1 — File Tree Summary
    entry_points.rs          # Check 1.2 — Entry Points Detection
    module_map.rs            # Check 1.3 — Module/Component Map (tree-sitter AST)
    monsters.rs              # Check 1.4 — Monster File Detection
```

**Dependencies:**
- `pyo3 = "0.25"` (extension-module)
- `tree-sitter = "0.24"` — AST парсинг
- `tree-sitter-python = "0.23"` — Python граматика
- `tree-sitter-javascript = "0.23"` — JS граматика
- `tree-sitter-typescript = "0.23"` — TS граматика
- `rayon = "1.10"` — parallel file scanning
- `ignore = "0.4"` — gitignore-aware directory walking (замість ручного skip list)

**Skip list (через `ignore` crate — читає .gitignore автоматично):**
Додатково ігноруємо навіть якщо не в .gitignore: `node_modules`, `.git`, `__pycache__`, `.venv`, `venv`, `.tox`, `dist`, `build`, `.next`, `.nuxt`, `target`.

### Python: `core/health/`

```
core/health/
  __init__.py
  project_map.py             # Check 1.5 (Python) + orchestrator
  models.py                  # Dataclasses для результатів всіх checks
```

### GUI

```
gui/pages/
  health_page.py             # Нова сторінка "Dev Health"
```

### Data

```
data/
  tips_health.md             # Підказки (вшиті, не AI-generated)
```

---

## Checks Detail

### Check 1.1 — File Tree Summary (`health::scan_file_tree`)

**Rust.** Сканує директорію, рахує:
- Кількість файлів по розширенню (top 10)
- Загальний розмір проєкту (без ignored)
- Максимальна глибина вкладеності каталогів
- Кількість директорій

**Returns:**
```python
@dataclass
class FileTreeResult:
    total_files: int
    total_dirs: int
    total_size_bytes: int
    max_depth: int
    files_by_ext: dict[str, int]      # {".py": 42, ".js": 18, ...}
    largest_dirs: list[tuple[str, int]]  # [(path, file_count), ...] top 5
```

**Severity:** info (завжди). Це контекст, не проблема.

**Tip:** "В тебе {total_files} файлів. З них {top_ext_count} — {top_ext}. Це нормально, але знай що вони є."

### Check 1.2 — Entry Points Detection (`health::scan_entry_points`)

**Rust.** Шукає файли за патернами:

Python entry points:
- `main.py`, `app.py`, `manage.py`, `wsgi.py`, `asgi.py`
- `__main__.py`
- Файли з `if __name__ == "__main__"` (tree-sitter parse)

JS/TS entry points:
- `index.js`, `index.ts`, `app.js`, `app.ts`, `server.js`, `server.ts`
- `package.json` → `"main"`, `"scripts.start"`, `"scripts.dev"` fields
- Файли з top-level `createServer`, `listen(`, `createApp` (tree-sitter parse)

**Returns:**
```python
@dataclass
class EntryPoint:
    path: str
    kind: str          # "main", "package_json_script", "server", "django_manage", etc.
    description: str   # "Python main module", "Express server", "Django management"

@dataclass
class EntryPointsResult:
    entry_points: list[EntryPoint]
```

**Severity:** info якщо є entry points; medium якщо жодного не знайдено.

**Tip:** "Точка входу — це файл з якого все починається. Як двері в будинок. В тебе їх {count}."

### Check 1.3 — Module/Component Map (`health::scan_module_map`)

**Rust + tree-sitter.** Парсить import/require у всіх .py/.js/.ts/.jsx/.tsx файлах:

Python imports (tree-sitter-python AST nodes):
- `import_statement` → `import foo`
- `import_from_statement` → `from foo import bar`
- Відрізняє local imports (`.foo`, `from . import`) від third-party

JS/TS imports (tree-sitter-javascript/typescript):
- `import_statement` → `import X from 'Y'`
- `call_expression` де callee = `require` → `require('Y')`
- Відрізняє local (`./`, `../`) від npm packages

Будує directed graph: file → [imported files]. Рахує in-degree кожного файлу.

**Returns:**
```python
@dataclass
class ModuleInfo:
    path: str
    imports: list[str]           # що цей файл імпортує (resolved paths)
    imported_by_count: int       # скільки файлів імпортує цей файл

@dataclass
class ModuleMapResult:
    modules: list[ModuleInfo]
    hub_modules: list[tuple[str, int]]   # top 5 most-imported: [(path, imported_by_count)]
    circular_deps: list[tuple[str, str]] # pairs з circular imports (якщо є)
    orphan_candidates: list[str]          # файли які ніхто не імпортує і не entry points
```

**Severity:** info для графу; medium якщо є circular deps; low для orphan candidates.

**Tip для хабів:** "{path} імпортується з {count} файлів. Це твій найважливіший модуль. Зламаєш — зламається все."

**Tip для circular:** "{a} імпортує {b}, а {b} імпортує {a}. Це замкнене коло — може зламатися при рефакторингу."

### Check 1.4 — Monster File Detection (`health::scan_monsters`)

**Rust.** Рахує рядки + функції/класи через tree-sitter:

Для кожного .py/.js/.ts/.jsx/.tsx:
- Рядки коду (без пустих)
- Кількість function/class definitions (tree-sitter nodes)

Thresholds:
- `> 500` рядків → severity medium ("warning")
- `> 1000` рядків → severity high
- `> 3000` рядків → severity critical

**Returns:**
```python
@dataclass
class MonsterFile:
    path: str
    lines: int
    functions: int
    classes: int
    severity: str          # "medium", "high", "critical"

@dataclass
class MonstersResult:
    monsters: list[MonsterFile]    # sorted by lines desc
```

**Tip:** "{path} — {lines} рядків і {functions} функцій. Це не файл, це роман. Один файл = одна відповідальність."

### Check 1.5 — Config & Env Inventory (`core/health/project_map.py`)

**Python.** Шукає конфіг-файли glob-ом:

Patterns:
- `.env`, `.env.*` (severity warning для кожного знайденого)
- `docker-compose*.yml`, `Dockerfile*`
- `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, `Pipfile`
- `package.json`, `tsconfig*.json`
- `Makefile`, `Procfile`
- `.github/workflows/*.yml`, `.gitlab-ci.yml`

Для .env файлів: рахує кількість змінних (рядки без коментарів), НЕ читає значення.

**Returns:**
```python
@dataclass
class ConfigFile:
    path: str
    kind: str          # "env", "docker", "python_deps", "js_config", "ci", "build"
    description: str   # "Environment variables (12 vars)", "Docker Compose config"
    severity: str      # "warning" для .env, "info" для решти

@dataclass
class ConfigInventoryResult:
    configs: list[ConfigFile]
    env_file_count: int
    has_docker: bool
    has_ci: bool
```

**Severity:** warning якщо >1 файл .env; info для решти.

**Tip:** "В тебе {count} файлів .env в різних папках. Це хаос. Зазвичай потрібен один .env в корені."

---

## GUI Design

Одна сторінка "Dev Health" в sidebar (між Activity Log і Security).

```
┌─────────────────────────────────────────────────────┐
│ 🏥 Dev Health                                        │
├─────────────────────────────────────────────────────┤
│ Project: /home/user/myapp          [Select Dir...]  │
│                                                      │
│ [🔍 Scan Project]                                    │
│                                                      │
│ ── Results ──────────────────────────────────────── │
│                                                      │
│ ℹ️ Project Map                                       │
│ ┌──────────────────────────────────────────────────┐│
│ │ 234 files | 18 dirs | 2.3 MB | depth 6          ││
│ │ .py: 89  .js: 42  .html: 18  .css: 12  ...      ││
│ └──────────────────────────────────────────────────┘│
│                                                      │
│ ℹ️ Entry Points (3)                                  │
│ ┌──────────────────────────────────────────────────┐│
│ │ ● manage.py — Django management                  ││
│ │ ● src/app.py — Python main module                ││
│ │ ● frontend/src/index.tsx — React entry           ││
│ └──────────────────────────────────────────────────┘│
│                                                      │
│ 🟡 Module Hubs                                       │
│ ┌──────────────────────────────────────────────────┐│
│ │ utils.py — imported by 14 files (hub!)           ││
│ │ models.py — imported by 9 files                  ││
│ │ config.py — imported by 7 files                  ││
│ │                                                  ││
│ │ ⚠️ 2 orphan files: old_api.py, temp_script.py    ││
│ └──────────────────────────────────────────────────┘│
│                                                      │
│ 🔴 Monster Files                                     │
│ ┌──────────────────────────────────────────────────┐│
│ │ 💀 app.py — 3241 lines, 47 functions             ││
│ │   "Це не файл, це роман."                        ││
│ │ 🔴 views.py — 1820 lines, 32 functions           ││
│ │ 🟡 utils.py — 612 lines, 28 functions            ││
│ └──────────────────────────────────────────────────┘│
│                                                      │
│ ⚠️ Configs (8 files)                                 │
│ ┌──────────────────────────────────────────────────┐│
│ │ ⚠️ .env (12 vars) — root                         ││
│ │ ⚠️ .env.local (8 vars) — root                    ││
│ │ ℹ️ docker-compose.yml — Docker config             ││
│ │ ℹ️ requirements.txt — Python dependencies         ││
│ └──────────────────────────────────────────────────┘│
│                                                      │
│ ── Summary ─────────────────────────────────────── │
│ 💀 1 critical | 🔴 1 high | 🟡 3 medium | ℹ️ 12 info │
└─────────────────────────────────────────────────────┘
```

- Одна кнопка "Scan Project"
- Результати grouped by check
- Severity badges кольорами
- Tips під кожним finding
- Summary bar внизу

---

## Data Flow

```
1. User clicks "Scan Project"
2. Python orchestrator (project_map.py):
   a. Calls health.scan_file_tree(path) → FileTreeResult
   b. Calls health.scan_entry_points(path) → EntryPointsResult
   c. Calls health.scan_module_map(path) → ModuleMapResult
   d. Calls health.scan_monsters(path) → MonstersResult
   e. Runs config_inventory(path) → ConfigInventoryResult  (Python)
   f. Combines into HealthReport
   g. Generates tips from data/tips_health.md templates
3. GUI renders HealthReport
```

Rust checks run sequentially (кожен <1 sec на типовому проєкті). Якщо треба — можна parallelise через rayon, але поки не потрібно.

---

## Error Handling

- `health` crate not installed → показуємо warning "Build health crate: cd crates/health && maturin develop"
- Директорія не існує → placeholder message
- Не git repo → все працює, просто orphan detection менш точний
- tree-sitter parse error на файлі → skip файл, log warning, продовжити
- Порожній проєкт (0 файлів) → "Empty project. Nothing to scan."

---

## Testing

**Rust tests (cargo test):**
- file_tree: scan tmp dir with known structure
- entry_points: detect main.py, index.js, package.json scripts
- module_map: parse known imports, build graph, detect hubs + circular deps
- monsters: count lines/functions in test fixtures

**Python tests (pytest):**
- project_map: config inventory on tmp dir with known files
- models: dataclass creation
- orchestrator: mock Rust calls, verify report assembly
- tips generation

**Test fixtures:** small .py/.js files with known imports in tests/fixtures/health/

---

## i18n

~20 нових рядків EN + UA:
- Sidebar label, page header, scan button
- Section headers (Project Map, Entry Points, Module Hubs, Monster Files, Configs)
- Severity labels, summary format
- Error messages (no crate, empty project)
- Hasselhoff mode variants

---

## Scope Exclusions

- Не робимо real-time watching (тільки manual scan)
- Не робимо auto-fix (тільки показуємо + tip)
- Не зберігаємо результати в SQLite (це Phase 2+ якщо потрібна історія)
- Не робимо CI інтеграцію
- tree-sitter тільки для Python + JS/TS (інші мови — Phase 2+)

---

## Cross-Platform

- Rust: `ignore` crate handles gitignore кросплатформенно
- tree-sitter: pure Rust, компілюється скрізь
- Python: pathlib, glob — кросплатформенні
- GUI: Qt native dialogs
- maturin: builds wheels для Linux/Mac/Windows
