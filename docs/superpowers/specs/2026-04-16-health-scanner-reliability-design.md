# Health Scanner Reliability Overhaul — Design

**Date:** 2026-04-16
**Status:** Spec
**Owner:** core/health + crates/health
**Trigger:** Self-audit of the Python project. The scanner flagged
its own code and ~40% of the findings were false positives
(see "Self-audit baseline" below). User verdict: "this is the most
important part of the project — it has to work perfectly."

---

## Scope

Fix every bug found in the self-audit, and add one new feature
(background test runner). No GUI redesign, no new plugins — just
make what exists **correct**.

Everything lives in two trees:

- **`crates/health/`** — Rust, tree-sitter-based, compiled via pyo3.
  This is where the parsing/cross-file analysis lives.
- **`core/health/`** — Python, orchestrates Rust scanners, formats
  findings, handles checks that don't need a parser (git, README,
  outdated deps).

Language choice: stay in **Rust**. All the static-analysis logic is
already there (`dead_code.rs`, `module_map.rs`, `duplicates.rs`,
`tech_debt.rs`). Switching to Go/C++ buys nothing and throws away
working code. The only new runtime piece (background test runner)
goes into Python because it's I/O-bound orchestration, not parsing.

---

## Self-audit baseline (what's broken right now)

The scanner ran against itself. These are the confirmed failures
(verified manually — grep + file reads, not "trust the report"):

| # | Symptom in report | Real state | Root cause |
|---|---|---|---|
| 1 | `core/models.py` "imported by 1 files" | imported by 14 | `module_map.rs` only resolves relative imports (`.foo`), ignores absolute `from core.X import Y` |
| 2 | `core/calculator.py` "imported by 1 files" | 2–3 | same |
| 3 | `plugins/port_map/collector.py` "orphan" | imported by 4 production files | same |
| 4 | `data/hooks_guide_ua.py` "orphan" | imported by `gui/pages/discover.py:72` | same |
| 5 | `core/safety_net/_save.py` "orphan" | imported by `core/safety_net/manager.py:17` | same |
| 6 | `core/nagger/hasselhoff.py` "orphan" | imported by `gui/app/main.py:530` | same |
| 7 | `core/context7_mcp.py` "orphan" | imported by 6 files | same |
| 8 | `aiosqlite` "unused import" ×4 plugins + `core/plugin.py` | used as type hint `aiosqlite.Connection` | `dead_code.rs:305` excludes identifiers that sit on a `function_definition` line — kills all annotations in the signature |
| 9 | `mcp_types` "unused import" | used 2× as `mcp_types.Tool`, `mcp_types.TextContent` | same |
| 10 | `_sentinel` "unused import" | import line has explicit `# noqa: F401` | noqa markers are not parsed at all |
| 11 | `setup_method` "dead function" ×3 in `test_platform.py` | pytest lifecycle hook, called by pytest runner | filter only whitelists `test_*` and dunders, not pytest lifecycle names |
| 12 | `test_mcp_server.py:178` "5 lines of commented-out code" | English explanatory comment containing `confirm=True` | `find_commented_blocks` regex treats any `=`, paren, or stopword as "code"; 40% threshold too lax |
| 13 | "No README file" | `README.MD` exists in root | `core/health/docs_context.py:19` uses a hardcoded case-sensitive filename list, no `.MD` variant |
| 14 | "1 staged, 19 modified, 4 untracked" — sum = 24, but "26 uncommitted" elsewhere | actually 0 staged, 19 modified, 3 deleted-unstaged, 4 untracked | `git_survival.py:46–59` has no branch for `" D"` / `" R"` / `"??"` combinations with non-standard layouts → unstaged deletions vanish |

Two correct-but-noisy findings that aren't bugs but hurt signal:

- Pytest fixture files with `import pytest` but no `pytest.` suffix
  in the body (fixtures are often imported for `@pytest.fixture`;
  if they're not, the finding is legit). These are real positives
  in our repo.
- Platform backend duplicates (linux/macos/windows) — correct
  detection, but the *recommended fix* ("extract into a shared
  function") is wrong advice for platform-specific backends.

---

## Tasks

Ordering: **15 → 12 → 8/9 → 10 → 11 → 13 → 14 → 16 → 18 → 17**.
Each task ships independently, own commit. Task 17 is the one piece
of new scope (background test runner); Task 18 fixes a thread-safety
bug observed live (unrelated to the scanner but same owner — the
GUI). The rest are scanner bug fixes.

### Task 15 — Absolute-import resolution (kills 5 orphan false positives + all hub undercounts) ✅ DONE 2026-04-16

**File:** `crates/health/src/module_map.rs`

**Symptom:** `is_local_import()` returns `true` only for strings
starting with `.` (Python) or `./`, `../` (JS). Everything else is
treated as a third-party import and discarded. This project uses
**absolute project-rooted imports** (`from core.X import Y`,
`from plugins.X import Y`, `from gui.X import Y`) for everything.
Result: the dependency graph is almost empty → every file looks
like an orphan, every hub count is ~0–1.

**Fix strategy:**

1. Build a set of **top-level package names** from directory layout
   at scan start:

   ```rust
   let package_roots: HashSet<String> = all_files
       .iter()
       .filter_map(|f| f.split('/').next().map(|s| s.to_string()))
       .filter(|p| !p.is_empty())
       .collect();
   ```

   For this repo: `{"core", "plugins", "gui", "i18n", "data",
   "tests", "docs", ...}`.

2. Extend `is_local_import()` to also return `true` if the import
   path's first dotted segment is in `package_roots`.

3. Extend `resolve_local_import()` for the absolute case:

   - `from core.context7_mcp import X` → try `core/context7_mcp.py`,
     `core/context7_mcp/__init__.py`.
   - `from plugins.port_map.collector import X` → try
     `plugins/port_map/collector.py`,
     `plugins/port_map/collector/__init__.py`.
   - Namespace imports (`from core import context7_mcp as c7`) →
     resolve to `core/context7_mcp.py`. This requires knowing that
     `context7_mcp` is the imported *name*, not a submodule prefix.
     Tree-sitter's `import_from_statement` gives us the module
     (`core`) and the `import_list`. Each `dotted_name` in
     `import_list` is a candidate file under `core/`.

4. JS/TS: accept `@/`, `~/`, and `src/` aliased paths if a
   `tsconfig.json` / `jsconfig.json` with `paths` is present at the
   root. Out of scope for v1 — keep the `./`, `../` behavior for JS.

**Verification:**

- Add `crates/health/tests/module_map_absolute.rs` with a fixture
  repo: `core/a.py` imports `core.b`, `core/b.py` imports
  `plugins.x.y`, `plugins/x/y.py` is a leaf. Assert
  `imported_by_count` for `core/b.py` == 1 and `plugins/x/y.py`
  is not in `orphan_candidates`.
- Re-run the self-audit. Expected deltas:
  - Hub `core/models.py`: imported by ≥10 (was 1).
  - Orphan list: `collector.py`, `hooks_guide_ua.py`, `_save.py`,
    `hasselhoff.py`, `context7_mcp.py` all gone.

**Not doing:** conditional imports inside `try:/except ImportError:`
blocks get the same treatment as top-level imports (already handled
by tree-sitter walking the whole tree). Function-scope lazy imports
(`def foo(): from core.x import y`) already work because
`walk_nodes` is recursive — confirmed by grep showing
`gui/app/main.py:530` imports work end-to-end in the new logic.

**Post-implementation delta (measured on this repo):**

| file | before | after |
|---|---|---|
| `core/models.py` | imported by 1 | 28 |
| `core/calculator.py` | imported by 1 | 4 |
| `core/context7_mcp.py` | ORPHAN | imported by 7 |
| `plugins/port_map/collector.py` | ORPHAN | imported by 5 |
| `data/hooks_guide_ua.py` | ORPHAN | imported by 1 |
| `core/safety_net/_save.py` | ORPHAN | imported by 1 |
| `core/nagger/hasselhoff.py` | ORPHAN | imported by 3 |
| `i18n/en.py`, `i18n/ua.py` | ORPHAN | imported by `i18n/__init__.py` via `from . import en, ua` |

New top-5 hub modules (sanity check):
`gui/win95.py` (140), `plugins/security_scan/scanners/__init__.py`
(39), `i18n/__init__.py` (37), `core/history.py` (30),
`core/health/models.py` (29). Plausible — these are the shared
widgets, scanner registry, and models that ought to be hubs.

**Subtleties that surfaced during implementation:**

1. `child_by_field_name("module_name")` returns the `relative_import`
   node for `from . import x` — so `module_text = Some(".")`, not
   `None`. Naïve `format!("{}.{}", module, name)` produces
   `"..en"` (too many dots). Fix: use a conditional joiner — if
   `module` already ends in `.`, concat without a separator.
2. For `from .helper import util`, `module_text = Some(".helper")`,
   names = `["util"]`, emit `".helper.util"`. Resolver tries
   `i18n/helper/util.py`, `i18n/helper/util/__init__.py`,
   `i18n/helper.py`, `i18n/helper/__init__.py` — the fourth / third
   wins. Works for both "import a submodule" and "import an
   attribute" shapes.
3. A file counting itself as its own importer (`gui/app/main.py`
   imports `gui.app.main` via an odd re-export path) produced
   inflated hub counts. Added `if &resolved_path != rel_path`
   guard.

### Residual orphans after Task 15 (verified on master)

Running the fixed scanner against this repo surfaces three orphans,
all of them **real**:

| file | why | action |
|---|---|---|
| `core/parser.py` | has `if __name__ == "__main__"` guard | `scan_entry_points` **already flags it** as `python_main_guard`; `project_map.py:152` passes `entry_paths` to `scan_module_map`, which already exempts them. **No code change needed** — the orphan only appears when the scanner is called standalone with empty entry_paths. |
| `gui/app/__main__.py` | runnable as `python -m gui.app` | same — entry_points flags it as `python_package_main`, exempted via entry_paths |
| `gui/pages/docker.py` | genuinely dead (`DockerPage` class + `set_docker_client` not instantiated or called anywhere; confirmed by grep) | **Delete the file.** It's the `DockerPage` / Docker tab that was excised in an earlier refactor but whose source was left behind. |

**Conclusion:** no new scanner task needed for entry-point
handling — the existing pipeline is correct once Task 15 lands.
Just remove `gui/pages/docker.py` in a separate cleanup commit.

---

### Task 12 — Type hints are usages (kills 6 "unused import" false positives) ✅ DONE 2026-04-16

**File:** `crates/health/src/dead_code.rs:302–310`

**Symptom:**

```rust
if node.kind() == "identifier" || node.kind() == "property_identifier" {
    let node_line = node.start_position().row as u32 + 1;
    if !import_lines.contains(&node_line) && !def_lines.contains(&node_line) {
        used_identifiers.insert(text.to_string());
    }
}
```

`def_lines` collects every line that starts a `function_definition`.
But a Python function signature commonly spans a single line and
**includes parameter type annotations**:

```python
async def migrate(self, db: aiosqlite.Connection) -> None:
```

Here `aiosqlite` is an identifier on the same line as `def`. The
exclusion drops it, so the import is falsely flagged "unused".

**Fix strategy:**

Replace the line-based exclusion with a **node-kind-based** one.
Only drop identifiers that are the **direct name** of an import or
a definition — not those sitting inside annotations or default
values on that same line.

Rules (Python):
- An identifier is an "import name" iff its parent chain matches
  `import_statement | import_from_statement` AND it is a
  `dotted_name` / `aliased_import` / `import_list` child (not a
  `type` / `annotation` node).
- An identifier is a "definition name" iff it is the `name` field
  of a `function_definition` / `class_definition` (i.e. matches
  `node.parent.child_by_field_name("name") == node`).

Rules (JS/TS): mirror — only the name being imported in
`import_clause` / `named_imports` / `namespace_import`, and the
name field of `function_declaration` / `class_declaration`.

Pseudocode:

```rust
fn is_decl_or_import_name(node: Node) -> bool {
    let mut cur = node.parent();
    while let Some(p) = cur {
        match p.kind() {
            // identifier is the defined name, not a reference inside the body/signature
            "function_definition" | "class_definition"
            | "function_declaration" | "class_declaration" => {
                return p.child_by_field_name("name")
                    .map(|n| n.id() == node.id())
                    .unwrap_or(false);
            }
            // identifier is part of the imported name list
            "dotted_name" | "aliased_import" | "import_specifier"
            | "namespace_import" | "import_clause" => return true,
            // stop climbing at statement/block boundaries
            "block" | "module" | "program" => return false,
            _ => cur = p.parent(),
        }
    }
    false
}
```

Drop the `import_lines` / `def_lines` `HashSet<u32>` entirely.

**Verification:**

- Add `tests/test_health_dead_code_type_hints.py` (chose Python
  over Rust integration — the crate is `cdylib`, no native
  integration-test harness).
  Fixture: `import aiosqlite` + `def x(db: aiosqlite.Connection)` →
  `unused_imports` empty.
- Self-audit delta: `aiosqlite`, `mcp_types` no longer flagged in
  production code. `pytest` still flagged in test files where it's
  genuinely unused, `os`/`sys` in `test_cli.py` still flagged.

**Post-implementation delta (measured on this repo):**

| category | before | after |
|---|---|---|
| `aiosqlite` flagged as unused | 4 files (core/plugin, 3 plugins) | 0 |
| `mcp_types` flagged as unused | 1 file | 0 |
| `TYPE_CHECKING` + import | flagged | not flagged |
| Real unused (`pytest` in 6 tests, `os`/`sys` in test_cli) | 8 | 8 (unchanged — these are real) |
| `_sentinel` with `# noqa: F401` | flagged | still flagged (fixed by Task 10) |

**Implementation notes:**

- Dropped the line-based `import_lines` / `def_lines` exclusion
  and replaced it with `is_decl_or_import_name(node)` — walks up
  the parent chain, returns true iff the identifier is the name
  field of a declaration or sits inside an `import_statement` /
  `import_from_statement`. Stops climbing at statement/block
  boundaries to avoid wandering into unrelated scopes.
- `import_lines` / `def_lines` `HashSet<u32>` are still populated
  (every existing insert site still fires) — kept for now as
  stable-API scaffolding, not consulted for identifier-usage
  decisions. Removed "we need to exclude this line" as the
  selection mechanism; now it's purely syntactic.
- Parameter name `os` in `def f(os): ...` currently counts as a
  usage (and thus suppresses the `import os` finding). Documented
  in test `test_parameter_name_is_not_a_usage`. This is a
  conscious trade-off — preferring false negatives over false
  positives in an extremely rare shape.

---

### Tasks 8 & 9 are subsumed by Task 12 — no separate work.

### Task 10 — `# noqa` support ✅ DONE 2026-04-16

**File:** `crates/health/src/dead_code.rs` (import-collection phase)

**Symptom:** `plugins/security_scan/scanners/base.py:27` has
`import sentinel as _sentinel  # noqa: F401`. The `noqa` marker is
the universal "I know, shut up" signal (pyflakes, flake8, ruff all
honor it). We ignore it.

**Fix strategy:**

After extracting each import, read the rest of that line and check
for one of:

- `# noqa` (bare — silences all checks on that line)
- `# noqa: F401` (F401 == unused import in pyflakes taxonomy)
- `# noqa: F401, F811` (comma-separated list)

If matched, **skip adding the import to `imports`** entirely (so it
never becomes a "used/unused" question).

Apply to both `import_statement` and `import_from_statement` lines.
For multi-line imports (`from x import (\n a,\n b\n)`), the marker
can appear on any line inside the parens — honor it per-name.

JS/TS equivalent: `// eslint-disable-line no-unused-vars` or
`// eslint-disable-next-line`. Same logic, different regex.

**Verification:**

- Unit test: file with `import x  # noqa: F401` and no usage of
  `x` → `unused_imports` empty.
- Unit test: file with `import x  # noqa: F811` (wrong code for
  this check) → still flagged.
- Self-audit delta: `_sentinel` (still flagged after Task 12 —
  confirmed) no longer flagged.

**Bonus fix bundled with Task 10:** while verifying noqa behaviour
on a `from typing import Any` fixture, discovered that the existing
`import_from_statement` handler only collected names from an
`import_list` child — which tree-sitter-python *only emits when
parentheses are used*. Every non-parenthesized `from X import Y`
was therefore silently skipped, hiding dozens of real unused
imports. Fix: walk direct children for `dotted_name` /
`aliased_import` (excluding the `module_name` child), same logic
module_map.rs already uses.

Effect: the self-audit went from 10 unused_imports to 88 — the
extra 78 are real findings that the old scanner never saw.

**Post-implementation delta:**

| marker on import line | before (self-audit) | after |
|---|---|---|
| `# noqa: F401` (`_sentinel`) | flagged | not flagged |
| `# noqa` (bare) | flagged | not flagged |
| `# NOQA` (uppercase) | flagged | not flagged |
| `# noqa: E501` (wrong code) | flagged | **still flagged** (correct) |
| `from typing import Any` (never used) | **missed** | flagged (bonus) |

All three previously-known false positives (`_sentinel`,
`aiosqlite`, `mcp_types`) are no longer in the unused-imports list.

---

### Task 11 — pytest lifecycle whitelist ✅ DONE 2026-04-16

**File:** `crates/health/src/dead_code.rs:316–325`

**Symptom:** `setup_method` in `tests/test_platform.py` is flagged
as dead code. pytest calls it automatically on every test method
in a class. Same story for the full pytest class-lifecycle family.

**Fix strategy:**

Extend the existing post-parse filter for Python definitions.
Current code:

```rust
definitions.retain(|(name, _, kind)| {
    if kind == "function" {
        !name.starts_with("__") && !name.starts_with("test_")
    } else {
        !name.starts_with("Test")
    }
});
```

Add test-aware logic. This filter is per-file, so we already know
the file path — if `rel_path` starts with `tests/` OR the file name
matches `test_*.py`, apply the extended whitelist:

```rust
const PYTEST_LIFECYCLE: &[&str] = &[
    // pytest function-style
    "setup_function", "teardown_function",
    "setup_module", "teardown_module",
    // pytest class-style (xunit)
    "setup_method", "teardown_method",
    "setup_class", "teardown_class",
    // unittest-style, which pytest also runs
    "setUp", "tearDown", "setUpClass", "tearDownClass",
    "setUpModule", "tearDownModule",
];
```

Also: **detect `@pytest.fixture` decorated functions**. In the
parse phase we already collect `decorated_lines`; extend to capture
the decorator *text*, and when the decorator text contains
`pytest.fixture` (or bare `fixture` with `from pytest import
fixture`), whitelist that definition.

Conftest.py: functions in `conftest.py` are globally visible to
pytest without being imported. Already covered by
`orphan_files` exclusion for `conftest.py`, but **also** add: any
function defined in a `conftest.py` must not end up in
`unused_definitions`.

**Verification:**

- Unit test with a class containing `setup_method` and one
  `test_foo` → assert `unused_definitions` is empty.
- Unit test with `@pytest.fixture\ndef client(): ...` where `client`
  is never textually used anywhere → assert it's not flagged.
- Self-audit delta: three `setup_method` entries gone.

---

### Task 13 — Conservative commented-code detection ✅ DONE 2026-04-16

**File:** `crates/health/src/dead_code.rs:395–478`
(`find_commented_blocks`, `maybe_emit_block`)

**Symptom:** Block at `tests/test_mcp_server.py:178–182` is
English prose. Current regex
`[=\(\)\{\}]|def |class |import |return |function |const |let |var |if |for`
matches `confirm=True` and `return None` inside prose, so at 40%
threshold the block gets flagged as "commented-out code".

**Fix strategy — make this a two-stage test:**

Stage 1 — syntactic: strip the leading `#` (or `//`) and trailing
whitespace from every line, join them, feed to the tree-sitter
parser for that language. If the parser returns **zero errors**
and the tree contains at least one non-trivial statement
(`expression_statement`, `assignment`, `function_definition`,
`if_statement`, `for_statement`, `return_statement`, `import_*`,
etc.), it's real commented-out code. Otherwise, it's prose.

Stage 2 — cheap pre-filter to avoid parsing every comment block:
the block must contain **at least two of**:
- A token that is a Python/JS keyword (`def`, `class`, `import`,
  `return`, `function`, `const`, `let`, `var`, `if`, `for`, `while`)
  **at the start of a line** (after `# ` or `// `).
- A line ending with `:` (Python) or `{` / `;` (JS).
- A line containing `=` **not** inside obvious prose markers
  (no `,` before, no common English words).

This pre-filter drops the current false positive immediately —
the English block has `confirm=True` and `end-to-end` but
no keyword-at-line-start, no trailing `:` / `{` / `;`.

**Verification:**

- Test fixture with real commented code:
  ```python
  # def old_function(x):
  #     y = x + 1
  #     return y
  # print(old_function(5))
  ```
  → flagged.
- Test fixture with English prose containing `=`:
  ```python
  # This is already covered by test_x, where confirm=True
  # path is exercised. Keeping two tests would be redundant
  # and slow.
  ```
  → not flagged.
- Self-audit delta: `test_mcp_server.py:178` no longer flagged.

---

### Task 14 — Case-insensitive README detection ✅ DONE 2026-04-16

**File:** `core/health/docs_context.py:14–32`

**Symptom:** Hardcoded list
`["README.md", "README.rst", "README.txt", "README", "readme.md"]`
doesn't include `README.MD`, `Readme.md`, etc.

**Fix strategy:**

Replace the list lookup with a directory scan:

```python
from pathlib import Path

README_STEM = "readme"
README_EXTS = {"", ".md", ".mdx", ".rst", ".txt", ".adoc"}

def _find_readme(project_dir: str) -> Path | None:
    root = Path(project_dir)
    for entry in root.iterdir():
        if not entry.is_file():
            continue
        if entry.stem.lower() != README_STEM:
            continue
        if entry.suffix.lower() in README_EXTS:
            return entry
    return None
```

Keep the subsequent "quality" check (≥ N lines, contains installation
/ usage sections) as-is — it already reads the file content.

**Verification:**

- Unit test creating `README.MD` in a tmp dir → `_find_readme`
  returns it.
- Self-audit delta: "No README file" finding gone.

---

### Task 16 — Git status: handle deletions and renames correctly ✅ DONE 2026-04-16

**File:** `core/health/git_survival.py:39–59`

**Symptom:** Three unstaged deletions (`D core/tips.py`,
`D gui/pages/tips.py`, `D gui/pages/usage.py`) are invisible to the
counter. The combined `staged/modified/untracked` breakdown sums to
24 while the "uncommitted files" count elsewhere says 26. Numbers
don't reconcile.

**Root cause:** The status parser only has branches for
`index ∈ AMDRC ∧ work == ' '` (staged),
`work == 'M'` (modified),
`index == '?' ∧ work == '?'` (untracked).
It has **no branch** for `index == ' ' ∧ work == 'D'`
(unstaged deletion), `index == ' ' ∧ work == 'R'`
(unstaged rename — rare but valid), `index == ' ' ∧ work == 'T'`
(type change), or `index == 'U'` (unmerged).

**Fix strategy:**

Rewrite the parser using the official `git status --porcelain=v1`
semantics (two-character code, each column independently
classified). Use a single function that returns a structured
dict:

```python
from dataclasses import dataclass, field

@dataclass
class GitStatusCounts:
    staged: list[str]        = field(default_factory=list)
    modified: list[str]      = field(default_factory=list)
    deleted: list[str]       = field(default_factory=list)
    untracked: list[str]     = field(default_factory=list)
    renamed: list[str]       = field(default_factory=list)
    unmerged: list[str]      = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.staged) + len(self.modified) + len(self.deleted)
            + len(self.untracked) + len(self.renamed) + len(self.unmerged)
        )
```

Classification table (X = index, Y = work tree):

| X | Y | Bucket |
|---|---|---|
| `?` | `?` | untracked |
| `A`/`M`/`D`/`R`/`C`/`T` | ` ` | staged |
| any of those | `M`/`T` | staged + modified |
| ` ` | `M`/`T` | modified |
| ` ` | `D` | deleted |
| ` ` | `R` | renamed |
| `U` | any | unmerged |
| any | `U` | unmerged |

After fix, the finding surfaces all buckets and the "total"
matches the "Unfinished work" counter elsewhere. Bonus: update the
"Unfinished work" check in `tech_debt.py` to call the same parser
so the numbers can never disagree.

**Verification:**

- Unit test with crafted status output covering every row above.
- Self-audit delta: on our repo the finding reads
  "19 modified, 3 deleted, 4 untracked" — sums to 26, matches
  the total.

---

### Task 18 — Status DB thread safety ✅ DONE 2026-04-16

**Discovered:** 2026-04-16 while running the GUI during Task 15
verification. Repeating warnings in the log:

```
WARNING: Status DB write failed: SQLite objects created in a thread
can only be used in that same thread. The object was created in
thread id 140187660607616 and this is thread id 140186441737920.
```

Not a scanner bug — same owner as the rest of this spec (GUI) —
tracked here so the reliability work is one coherent effort.

**Root cause:**

A `sqlite3.Connection` (or `aiosqlite.Connection`) is opened in the
main Qt thread, then reused from `QThread` workers (Haiku client
calls, status writes). Python's stdlib `sqlite3` enforces
thread-affinity unless `check_same_thread=False` is passed — and
even then, **raw connection sharing across threads is unsafe**
without an explicit lock, because SQLite's C API serializes by
connection, not by the Python GIL.

Write failures are silently warned and dropped — which is why the
GUI keeps running but persisted status is incoherent.

**Options (pick one per storage):**

- **Per-thread connection**: open a new `sqlite3.Connection` in
  each worker thread on demand. Simplest, safest. Downside: more
  file handles, but SQLite handles this cheaply. Preferred for
  short-lived writes.
- **Connection + `threading.Lock`**: shared connection with
  `check_same_thread=False` plus a module-level `Lock` around every
  `cursor()` / `execute()` call. Preferred if the connection is
  hot and per-thread reconnection would dominate latency.
- **Write queue**: one dedicated writer thread owns the connection;
  other threads enqueue write ops through `queue.Queue`. Overkill
  for this use case — mention for completeness.

**Fix strategy:**

1. Audit every `sqlite3.connect` / `aiosqlite.connect` call site.
   Group by which thread opens it and which thread uses it. The
   prime suspect is `core/status_checker.py` (writes the status
   row on every Haiku completion) but **do the grep before
   assuming** — there may be more than one.
2. For each violating connection: convert to per-thread-on-demand.
   Pattern:
   ```python
   import threading
   _local = threading.local()

   def _conn() -> sqlite3.Connection:
       conn = getattr(_local, "conn", None)
       if conn is None:
           conn = sqlite3.connect(DB_PATH)
           _local.conn = conn
       return conn
   ```
   Every call site uses `_conn()` instead of a module-level
   global.
3. **Do not** silently swallow the warning message. If a write
   path is still hitting the threading guard, we want to crash,
   not log-and-continue — silent corruption of persisted state is
   worse than a crash.
4. Replace `try: ... except Exception as e: log.warning(...)`
   around write-paths with either a real fix or a narrow
   `except sqlite3.OperationalError` that re-raises in debug mode.

**Verification:**

- Unit test: spawn 10 threads, each writes 100 rows through the
  new `_conn()` helper. Assert 1000 rows present.
- Unit test: calling `_conn()` from two threads returns distinct
  `Connection` objects (identity check).
- Manual: run the GUI, trigger several Haiku calls in rapid
  succession, grep the log for "Status DB write failed" — must
  be zero.

**Not doing:**

- Migrating to a different database. SQLite is fine — the problem
  is our usage, not SQLite.
- Introducing an ORM. The project uses stdlib `sqlite3` and
  `aiosqlite`; a new abstraction layer buys nothing here.
- Global WAL-mode tuning. Out of scope; fix the threading bug
  first, measure, decide.

---

### Task 17 — Background test runner (new feature)

This is the one piece of new scope. Everything above is fixing
what's broken; this *adds*.

**Why:** User wants tests to be part of the health check output,
not a separate terminal command. But running pytest synchronously
blocks the GUI for minutes on a real repo. Background execution is
the only acceptable mode.

**File layout:**

- `core/health/test_runner.py` — new, pure Python, orchestrates the
  subprocess.
- `plugins/test_runner/` — new plugin (same pattern as
  `plugins/docker_monitor/`, `plugins/port_map/`). Reuses the
  existing plugin lifecycle: `migrate`, `collect`, `get_alerts`.
- `gui/pages/health/page.py` — add a "Tests" section with live
  status + last-run summary.

**Framework detection:**

Look at `pyproject.toml` / `setup.cfg` / `tox.ini` for pytest,
`package.json` scripts for `test`, `go.mod` for Go, `Cargo.toml`
for `cargo test`. Store the detected command in
`app_state.test_runner_cmd`. Respect an explicit override in
`config.toml`:

```toml
[tests]
command = "pytest -x --tb=short"
watch_paths = ["core", "plugins", "tests"]
```

**Execution model:**

One worker `QThread` owned by the plugin:

```python
# core/health/test_runner.py
import subprocess
from dataclasses import dataclass
from pathlib import Path

@dataclass
class TestRun:
    command: list[str]
    started_at: float
    finished_at: float | None
    exit_code: int | None
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_s: float
    output_tail: str  # last 200 lines of stdout/stderr, for GUI display

class TestRunner:
    def run(self, project_dir: Path, cmd: list[str]) -> TestRun:
        """Blocking — call from a worker thread."""
        ...
```

- `subprocess.Popen(cmd, cwd=project_dir, stdout=PIPE,
  stderr=STDOUT, text=True)` with streaming read loop.
- Parse pytest output line-by-line for `PASSED`/`FAILED`/`ERROR`/
  `SKIPPED` counters (or use `--json-report` if `pytest-json-report`
  is installed — detect at startup).
- Hard timeout (configurable, default 10 min). On timeout:
  `proc.kill()`, record as `timeout`.
- Persist every run to a new SQLite table `test_runs` (plugin
  `migrate()`):
  ```sql
  CREATE TABLE test_runs (
      id INTEGER PRIMARY KEY,
      project_dir TEXT NOT NULL,
      started_at REAL NOT NULL,
      finished_at REAL,
      exit_code INTEGER,
      passed INTEGER,
      failed INTEGER,
      errors INTEGER,
      skipped INTEGER,
      duration_s REAL,
      output_tail TEXT
  );
  ```

**When to run:**

Three triggers, all opt-in via settings:
1. **Manual** — "Run tests" button in the Health page. Always
   available.
2. **On save-point** — after a successful save-point, enqueue a
   run. User saw the code changed; running tests is the natural
   next step.
3. **Watch mode** — optional. Uses `watchdog` if installed.
   Debounces 2s after the last file change under `watch_paths`.
   Skipped by default (opt-in; noisy on large repos).

**Concurrency rule:** at most one run in flight per project. If a
trigger fires while a run is going, **coalesce** — remember a
single "needs-re-run" flag, fire immediately after the current
run finishes. Never queue more than one pending run.

**GUI surface:**

Health page "Tests" section shows:
- Current state: `idle` / `running (42s)` / `passed in 1m 13s` /
  `failed: 3 of 124` / `timed out after 10m`.
- Sparkline of the last 10 runs' duration, color-coded by result.
- Tail of `output_tail` in a copyable widget when failed.
- "Run tests" button (manual trigger).
- Small kebab → "Show history" → table view of `test_runs`.

**What this is NOT:**
- Not a replacement for CI.
- Not a test *runner* — it shells out to `pytest`/`cargo test`/
  `go test`/`npm test`.
- Not coverage-aware. Coverage is a separate feature nobody asked
  for.

**Verification:**

- Unit test `core/health/test_runner.py` with a tiny repo fixture
  containing one passing + one failing test. Assert counters.
- Unit test: timeout path. Process runs `sleep 60`, timeout set
  to 1s, assert `exit_code = None` and a timeout flag.
- Manual: run the GUI against this repo, hit "Run tests", watch
  the status transition idle → running → passed/failed.
- Concurrency test: fire two triggers 100ms apart, assert only
  one `TestRun` row created, with one `needs-re-run` coalesce.

---

## Non-goals

- Rewriting the scanner in a different language. Rust + tree-sitter
  is already the right call; the bugs are logic, not speed.
- Full symbolic analysis (call graphs, escape analysis, etc.).
  We want accurate *surface* facts: "X imports Y", "Z is not
  referenced". Anything deeper is out of scope.
- Windows-only edge cases for the test runner (path quoting,
  CRLF output parsing). Track as follow-up if the product goes
  beyond Linux/macOS.
- Incremental/cached runs. The scan is already fast enough
  (< 1 s on this repo); caching buys little, adds invalidation
  bugs.

---

## Test plan (end-to-end)

After all tasks land, re-run the health scan against this repo and
compare to the baseline. Acceptance:

| Finding | Baseline | After fix | Status |
|---|---|---|---|
| Orphan files | 5 (all false) + 2 entry points + `i18n/{en,ua}.py` | 1 real (`gui/pages/docker.py`) | ✅ Task 15 done |
| Hub "imported by 1" | 2 (both wrong) | real counts, 28 for `core/models.py` | ✅ Task 15 done |
| Unused imports in production code | 6 false positives | 0 | ✅ Task 12 done |
| `_sentinel` with noqa | flagged | not flagged | ✅ Task 10 done |
| `setup_method` in tests | 3 flagged | 0 flagged | ✅ Task 11 done |
| Commented code at `test_mcp_server.py:178` | flagged | not flagged | ✅ Task 13 done |
| "No README file" | flagged | not flagged | ✅ Task 14 done |
| Git status sum | 24 vs 26 mismatch | reconciles | ✅ Task 16 done |
| Status DB "created in a thread" warnings | spammed on every Haiku call | zero | ✅ Task 18 done |
| Background test runner | absent | working, one worker per project, coalesced triggers | ⏳ Task 17 |

A run is "green" only if:
- Every finding listed in `Self-audit baseline` no longer fires.
- The genuine positives (unused `pytest`/`os`/`sys` in tests,
  real `except: pass`, real hardcoded URLs, duplicate platform
  backends) **still fire** — we haven't over-corrected.
- `cargo test -p health` passes in CI.
- `pytest tests/test_health_*.py` passes.

---

## Files touched (summary)

Rust:
- `crates/health/src/dead_code.rs` — tasks 10, 11, 12, 13
- `crates/health/src/module_map.rs` — task 15
- `crates/health/tests/` — new integration tests per task

Python:
- `core/health/docs_context.py` — task 14
- `core/health/git_survival.py` — task 16
- `core/health/test_runner.py` — task 17 (new)
- `core/health/tech_debt.py` — task 16 (reconcile "uncommitted" count)
- `plugins/test_runner/` — task 17 (new package)
- `gui/pages/health/page.py` — task 17
- `core/status_checker.py` + other sqlite3 call sites — task 18
  (per-thread connections)
- `gui/pages/docker.py` — **delete** (residual-orphans cleanup,
  separate commit after Task 15)

Tests:
- Per-task unit tests added alongside each change.
- One end-to-end test that runs the full `scan_dead_code` +
  `scan_module_map` against a fixture repo mirroring the bugs
  above, asserts zero false positives.

---

## Rollout

- Each task is a separate commit on `master` (or a short-lived
  branch). No big-bang merge.
- After Task 15 lands and before the rest, run a pre/post diff of
  the full scan output on this repo — archive both as
  `docs/audit/2026-04-16-pre-fix.txt` and `-post-fix.txt` for
  regression tracking.
- Task 17 ships last. If it's unstable, it can be disabled with a
  single config flag (`[plugins] test_runner = false`) without
  touching the scanner core.
