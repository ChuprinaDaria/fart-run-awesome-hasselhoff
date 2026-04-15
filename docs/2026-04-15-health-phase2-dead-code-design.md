# Dev Health Phase 2: Dead Code — Design

> "Менше коду = менше багів = менше плутанини."

## Goal

Знайти мертвий код: unused imports, unused functions/classes, orphan files, закоментований код. Один Rust scan, один прохід по файлах, tree-sitter AST.

## Checks

### Check 2.1 — Unused Imports

- tree-sitter парсить import statements
- Для кожного imported name шукає usage в решті файлу (excluding import line itself)
- Python: `import X` / `from X import Y` — шукає `X` / `Y` в коді
- JS/TS: `import { X } from 'Y'` / `const X = require('Y')` — шукає `X`
- Severity: medium

### Check 2.2 — Unused Functions/Classes

- tree-sitter знаходить `function_definition` / `class_definition` (Python), `function_declaration` / `class_declaration` (JS/TS)
- Для кожного definition шукає ім'я по ВСІХ файлах проекту (cross-file search)
- НЕ позначає як unused:
  - Entry points (main guard, server listen)
  - `__init__`, `__str__`, `__repr__` та інші dunder methods
  - Functions/classes в `__init__.py` (re-exports)
  - Test functions (`test_*`, `Test*`)
  - Decorated functions (`@app.route`, `@pytest.fixture`, etc.)
  - Names starting with `_` that are in the same file (private by convention)
- Severity: medium

### Check 2.3 — Orphan Files

- Reuse `module_map.scan_module_map()` результат — `orphan_candidates`
- Додатковий фільтр: exclude test files, config files, __init__.py, setup.py
- Severity: low

### Check 2.4 — Commented-Out Code Blocks

- Regex scan (не tree-sitter — коментарі не в AST)
- Python: >=5 consecutive lines starting with `#` що містять code patterns (`=`, `(`, `)`, `def `, `class `, `import `, `return`, `if `, `for `)
- JS/TS: >=5 consecutive lines starting with `//` з аналогічними patterns
- Block comments `/* ... */` >5 lines з code patterns
- Severity: low
- Preview: перші 3 рядки блоку

## Architecture

### Rust: `crates/health/src/dead_code.rs`

Один модуль, одна функція `scan_dead_code(path, entry_point_paths)`.

Внутрішній flow:
1. Walk all source files (reuse `ignore` + `should_skip`)
2. Per-file: tree-sitter parse → collect imports + definitions + all identifiers used
3. Cross-file: build set of all defined names, for each check if used anywhere
4. Regex pass: commented code blocks

```rust
#[pyclass]
pub struct UnusedImport {
    pub path: String,
    pub line: u32,
    pub name: String,
    pub import_statement: String,  // full line for context
}

#[pyclass]
pub struct UnusedDefinition {
    pub path: String,
    pub line: u32,
    pub name: String,
    pub kind: String,  // "function" or "class"
}

#[pyclass]
pub struct CommentedBlock {
    pub path: String,
    pub start_line: u32,
    pub end_line: u32,
    pub line_count: u32,
    pub preview: String,  // first 3 lines
}

#[pyclass]
pub struct DeadCodeResult {
    pub unused_imports: Vec<UnusedImport>,
    pub unused_definitions: Vec<UnusedDefinition>,
    pub orphan_files: Vec<String>,
    pub commented_blocks: Vec<CommentedBlock>,
}
```

### Python: `core/health/dead_code.py`

Orchestrator — calls `health.scan_dead_code()`, converts to `HealthFinding`s, generates tips.

### Integration

- `project_map.py` → `run_all_checks()` calls dead code scan after Phase 1 checks
- Orphan files: scan_dead_code gets them from module_map internally (pass entry_point_paths)
- GUI: new section "Dead Code" in health_page between Monsters and Configs
- i18n: ~10 new strings

## Tips

- Unused import: "{name} imported in {path}:{line} but never used. Remove it — nothing will break."
- Unused function: "{name}() in {path} — defined but never called anywhere. Delete or use it."
- Unused class: "class {name} in {path} — exists but nobody creates instances. Dead weight."
- Commented code: "{line_count} lines of commented code in {path}:{start_line}. That's not backup — git is. Delete."
- Orphan file: "{path} — no imports, not an entry point. Archive or delete."

## False Positive Mitigation

- Decorated functions → skip (can't know if decorator registers them)
- `__all__` exports → skip names listed in `__all__`
- Re-exports in `__init__.py` → skip
- Dynamic imports (`importlib`, `__import__`) → can't track, accept false negatives
- `*` imports → skip file entirely for unused import check (can't resolve)

## Scope Exclusions

- No duplicate code detection (Phase 3)
- No cross-language import tracking (Python importing JS or vice versa)
- No dynamic import resolution
- No auto-fix

## Cross-Platform

Same as Phase 1 — pure Rust + tree-sitter, compiles everywhere.
