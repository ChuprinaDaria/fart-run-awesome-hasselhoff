# Dev Health Phase 3a: Tech Debt — Design

> "Знайти проблеми які зараз не болять, але вибухнуть пізніше."

## Goal

4 offline checks: missing type hints, error handling gaps, hardcoded values, TODO/FIXME audit. Один Rust модуль `tech_debt.rs`, один прохід по файлах, tree-sitter + regex.

## Checks

### 3.2 Missing Type Hints

- Python: tree-sitter `function_definition` → параметри без `type` annotation, return без `->`
- JS (.js only): `function_declaration` без JSDoc `@param`/`@returns` перед ним
- Skip: `.ts`/`.tsx` (TypeScript has types), dunder methods, test functions, lambdas
- Severity: medium

### 3.3 Error Handling Gaps

- Python: `except_clause` без type (`except:` замість `except ValueError:`), `except` з тілом тільки `pass`
- JS/TS: empty `catch_clause` body, `.then()` без `.catch()`
- Severity: medium для bare except, low для missing catch

### 3.4 Hardcoded Values

Regex в string/number literals:
- Hardcoded URLs: `http://` або `https://` в string literals (not imports, not comments, not tests)
- Hardcoded ports: assignment to var with "port" in name where value is 1024-65535
- `sleep(N)` / `setTimeout(N)` де N > 10000 (ms) або N > 10 (sec) — suspicious timeout
- Skip: constants at module level (ALL_CAPS names), test files, config files
- Severity: low

### 3.5 TODO/FIXME/HACK Audit

- Regex: `TODO|FIXME|HACK|XXX|TEMP` в коментарях
- Rust знаходить рядки, Python збагачує git blame датою
- Severity: low якщо <30 днів, medium якщо >30 днів
- Output: path, line, text, kind, commit_date (optional)

## Architecture

### Rust: `crates/health/src/tech_debt.rs`

```rust
#[pyclass] struct MissingType { path, line, function_name, param_count, missing_return }
#[pyclass] struct ErrorGap { path, line, kind, description }
#[pyclass] struct HardcodedValue { path, line, value, kind }
#[pyclass] struct TodoItem { path, line, text, kind }

#[pyclass] struct TechDebtResult {
    missing_types: Vec<MissingType>,
    error_gaps: Vec<ErrorGap>,
    hardcoded: Vec<HardcodedValue>,
    todos: Vec<TodoItem>,
}

#[pyfunction] fn scan_tech_debt(path: &str) -> TechDebtResult
```

### Python: `core/health/tech_debt.py`

- Calls `health.scan_tech_debt(path)`
- Enriches TODOs with git blame dates (subprocess)
- Converts to HealthFindings with tips
- Integrates into `run_all_checks()`

### GUI

New sections in health_page: "Missing Types", "Error Handling", "Hardcoded Values", "TODOs"

### i18n

~8 new strings EN + UA

## Scope Exclusions

- No outdated dependency check (needs network — Phase 3b)
- No reusable component detection (complex JSX — Phase 3b)
- No auto-fix suggestions
- Git blame is best-effort (skipped if git unavailable)
