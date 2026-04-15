# Dev Health Checks Phase 1: Project Map — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rust crate `health` with tree-sitter AST parsing + Python orchestrator + GUI page that scans a project directory and shows 5 health checks with human-language tips.

**Architecture:** New Rust crate (`crates/health/`) with PyO3 bindings exposes 4 scan functions. Python orchestrator (`core/health/`) calls Rust + runs Check 1.5 natively, assembles `HealthReport`. GUI page (`gui/pages/health_page.py`) renders results with severity badges.

**Tech Stack:** Rust (PyO3 0.25, tree-sitter 0.26, rayon 1.10, ignore 0.4), Python (pathlib, glob), PyQt5, maturin

---

## File Structure

### New files — Rust crate

```
crates/health/
  Cargo.toml
  pyproject.toml
  src/
    lib.rs                  # PyO3 module registration
    common.rs               # Shared types: skip dirs, severity constants
    file_tree.rs            # Check 1.1 — File Tree Summary
    entry_points.rs         # Check 1.2 — Entry Points Detection
    module_map.rs           # Check 1.3 — Module/Component Map
    monsters.rs             # Check 1.4 — Monster File Detection
```

### New files — Python

```
core/health/
  __init__.py
  models.py                 # Dataclasses for all check results
  project_map.py            # Check 1.5 + orchestrator
  tips.py                   # Tip generation from check results

gui/pages/
  health_page.py            # GUI page

tests/
  test_health_models.py     # Python model tests
  test_health_project_map.py # Check 1.5 + orchestrator tests
```

### Modified files

```
gui/app.py                  # Add health page to sidebar + stack
i18n/en.py                  # ~25 new strings
i18n/ua.py                  # ~25 new strings
```

### Test fixtures

```
tests/fixtures/health/
  sample_project/
    main.py
    utils.py
    api/
      views.py
      models.py
    .env
    requirements.txt
    package.json
```

---

### Task 1: Rust crate scaffold + file_tree module

**Files:**
- Create: `crates/health/Cargo.toml`
- Create: `crates/health/pyproject.toml`
- Create: `crates/health/src/lib.rs`
- Create: `crates/health/src/common.rs`
- Create: `crates/health/src/file_tree.rs`

- [ ] **Step 1: Create Cargo.toml**

```toml
[package]
name = "health"
version = "0.1.0"
edition = "2021"
description = "fart.run health — project health scanner for vibe coders"

[lib]
name = "health"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.25", features = ["extension-module"] }
tree-sitter = "0.26"
tree-sitter-python = "0.25"
tree-sitter-javascript = "0.25"
tree-sitter-typescript = "0.23"
rayon = "1.10"
ignore = "0.4"
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["maturin>=1.0,<2.0"]
build-backend = "maturin"

[project]
name = "health"
version = "0.1.0"
description = "fart.run health — project health scanner"
requires-python = ">=3.10"

[tool.maturin]
features = ["pyo3/extension-module"]
```

- [ ] **Step 3: Create common.rs**

```rust
//! Shared constants and types for health checks.

/// Directories to always skip, even if not in .gitignore.
pub const ALWAYS_SKIP: &[&str] = &[
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "env",
    ".egg-info",
];

/// Source file extensions we care about for analysis.
pub const SOURCE_EXTENSIONS: &[&str] = &[
    "py", "js", "ts", "jsx", "tsx",
    "mjs", "mts", "cjs", "cts",
];

/// Check if a path component should be skipped.
pub fn should_skip(name: &str) -> bool {
    ALWAYS_SKIP.iter().any(|s| *s == name)
}
```

- [ ] **Step 4: Create file_tree.rs**

```rust
//! Check 1.1 — File Tree Summary.
//!
//! Scans project directory, counts files by extension, measures depth.

use std::collections::HashMap;
use std::path::Path;

use ignore::WalkBuilder;
use pyo3::prelude::*;

use crate::common::should_skip;

#[pyclass]
#[derive(Clone)]
pub struct FileTreeResult {
    #[pyo3(get)]
    pub total_files: u64,
    #[pyo3(get)]
    pub total_dirs: u64,
    #[pyo3(get)]
    pub total_size_bytes: u64,
    #[pyo3(get)]
    pub max_depth: u32,
    #[pyo3(get)]
    pub files_by_ext: HashMap<String, u64>,
    #[pyo3(get)]
    pub largest_dirs: Vec<(String, u64)>,
}

#[pyfunction]
pub fn scan_file_tree(path: &str) -> PyResult<FileTreeResult> {
    let root = Path::new(path);
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Not a directory: {}", path),
        ));
    }

    let mut total_files: u64 = 0;
    let mut total_dirs: u64 = 0;
    let mut total_size: u64 = 0;
    let mut max_depth: u32 = 0;
    let mut ext_counts: HashMap<String, u64> = HashMap::new();
    let mut dir_counts: HashMap<String, u64> = HashMap::new();

    let walker = WalkBuilder::new(root)
        .hidden(false)
        .git_ignore(true)
        .git_global(false)
        .git_exclude(true)
        .filter_entry(|entry| {
            if let Some(name) = entry.file_name().to_str() {
                !should_skip(name)
            } else {
                true
            }
        })
        .build();

    for entry in walker.flatten() {
        let entry_path = entry.path();

        // Calculate depth relative to root
        if let Ok(rel) = entry_path.strip_prefix(root) {
            let depth = rel.components().count() as u32;
            if depth > max_depth {
                max_depth = depth;
            }
        }

        if entry_path.is_dir() {
            total_dirs += 1;
            continue;
        }

        // File
        total_files += 1;

        if let Ok(meta) = entry_path.metadata() {
            total_size += meta.len();
        }

        // Extension count
        if let Some(ext) = entry_path.extension().and_then(|e| e.to_str()) {
            let ext_lower = ext.to_lowercase();
            *ext_counts.entry(ext_lower).or_insert(0) += 1;
        } else {
            *ext_counts.entry(String::new()).or_insert(0) += 1;
        }

        // Parent directory file count
        if let Some(parent) = entry_path.parent() {
            if let Ok(rel) = parent.strip_prefix(root) {
                let dir_key = rel.to_string_lossy().to_string();
                *dir_counts.entry(dir_key).or_insert(0) += 1;
            }
        }
    }

    // Top 10 extensions by count
    let mut ext_vec: Vec<(String, u64)> = ext_counts.into_iter().collect();
    ext_vec.sort_by(|a, b| b.1.cmp(&a.1));
    let files_by_ext: HashMap<String, u64> = ext_vec.into_iter().take(10).collect();

    // Top 5 largest directories
    let mut dir_vec: Vec<(String, u64)> = dir_counts.into_iter().collect();
    dir_vec.sort_by(|a, b| b.1.cmp(&a.1));
    let largest_dirs: Vec<(String, u64)> = dir_vec.into_iter().take(5).collect();

    Ok(FileTreeResult {
        total_files,
        total_dirs,
        total_size_bytes: total_size,
        max_depth,
        files_by_ext,
        largest_dirs,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_scan_empty_dir() {
        let tmp = tempfile::tempdir().unwrap();
        let result = scan_file_tree(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.total_files, 0);
    }

    #[test]
    fn test_scan_with_files() {
        let tmp = tempfile::tempdir().unwrap();
        fs::write(tmp.path().join("main.py"), "print('hi')").unwrap();
        fs::write(tmp.path().join("app.js"), "console.log('hi')").unwrap();
        fs::create_dir(tmp.path().join("src")).unwrap();
        fs::write(tmp.path().join("src/utils.py"), "x = 1").unwrap();

        let result = scan_file_tree(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.total_files, 3);
        assert!(result.max_depth >= 1);
        assert!(result.files_by_ext.contains_key("py"));
        assert_eq!(*result.files_by_ext.get("py").unwrap(), 2);
    }

    #[test]
    fn test_skips_node_modules() {
        let tmp = tempfile::tempdir().unwrap();
        fs::create_dir(tmp.path().join("node_modules")).unwrap();
        fs::write(tmp.path().join("node_modules/junk.js"), "x").unwrap();
        fs::write(tmp.path().join("app.js"), "y").unwrap();

        let result = scan_file_tree(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.total_files, 1);
    }
}
```

- [ ] **Step 5: Create lib.rs (minimal, just file_tree)**

```rust
//! health — project health scanner for vibe coders.

mod common;
mod file_tree;

use pyo3::prelude::*;

#[pymodule]
fn health(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<file_tree::FileTreeResult>()?;
    m.add_function(wrap_pyfunction!(file_tree::scan_file_tree, m)?)?;
    Ok(())
}
```

- [ ] **Step 6: Add tempfile dev-dependency to Cargo.toml**

Append to Cargo.toml:
```toml

[dev-dependencies]
tempfile = "3"
```

- [ ] **Step 7: Build and test**

Run:
```bash
cd crates/health && ~/.cargo/bin/cargo test 2>&1
```
Expected: 3 tests pass

- [ ] **Step 8: Build Python wheel**

Run:
```bash
cd crates/health && maturin develop 2>&1
```
Expected: builds and installs `health` module

- [ ] **Step 9: Verify from Python**

Run:
```bash
python -c "import health; r = health.scan_file_tree('.'); print(f'Files: {r.total_files}')"
```
Expected: prints file count

- [ ] **Step 10: Commit**

```bash
git add crates/health/
git commit -m "feat: scaffold health crate + Check 1.1 file_tree scanner"
```

---

### Task 2: entry_points module (Rust)

**Files:**
- Create: `crates/health/src/entry_points.rs`
- Modify: `crates/health/src/lib.rs`

- [ ] **Step 1: Create entry_points.rs**

```rust
//! Check 1.2 — Entry Points Detection.
//!
//! Finds main.py, index.js, package.json scripts, __main__.py,
//! and files with `if __name__ == "__main__"` or server creation patterns.

use std::collections::HashSet;
use std::fs;
use std::path::Path;

use ignore::WalkBuilder;
use pyo3::prelude::*;

use crate::common::{should_skip, SOURCE_EXTENSIONS};

/// Known entry point file names (case-insensitive stem matching).
const PYTHON_ENTRY_NAMES: &[&str] = &[
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
    "__main__.py", "run.py", "server.py", "cli.py",
];

const JS_ENTRY_NAMES: &[&str] = &[
    "index.js", "index.ts", "index.jsx", "index.tsx",
    "index.mjs", "index.mts",
    "app.js", "app.ts", "app.jsx", "app.tsx",
    "server.js", "server.ts",
    "main.js", "main.ts",
];

#[pyclass]
#[derive(Clone)]
pub struct EntryPoint {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub kind: String,
    #[pyo3(get)]
    pub description: String,
}

#[pyclass]
#[derive(Clone)]
pub struct EntryPointsResult {
    #[pyo3(get)]
    pub entry_points: Vec<EntryPoint>,
}

#[pyfunction]
pub fn scan_entry_points(path: &str) -> PyResult<EntryPointsResult> {
    let root = Path::new(path);
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Not a directory: {}", path),
        ));
    }

    let mut entries: Vec<EntryPoint> = Vec::new();
    let mut seen: HashSet<String> = HashSet::new();

    // Check package.json scripts
    let pkg_json = root.join("package.json");
    if pkg_json.is_file() {
        if let Ok(content) = fs::read_to_string(&pkg_json) {
            let mut scripts_found = Vec::new();
            // Simple JSON parsing — look for "main", "scripts" fields
            if let Some(main_field) = extract_json_string(&content, "main") {
                scripts_found.push(("package_json_main", main_field));
            }
            // Check for start/dev scripts
            for script_name in &["start", "dev", "serve"] {
                if content.contains(&format!("\"{}\"", script_name)) {
                    scripts_found.push(("package_json_script", script_name.to_string()));
                }
            }
            if !scripts_found.is_empty() {
                let rel = "package.json".to_string();
                if seen.insert(rel.clone()) {
                    let desc = scripts_found
                        .iter()
                        .map(|(_, v)| v.as_str())
                        .collect::<Vec<_>>()
                        .join(", ");
                    entries.push(EntryPoint {
                        path: rel,
                        kind: "package_json".to_string(),
                        description: format!("Node.js project config (scripts: {})", desc),
                    });
                }
            }
        }
    }

    // Walk source files
    let walker = WalkBuilder::new(root)
        .hidden(false)
        .git_ignore(true)
        .git_global(false)
        .git_exclude(true)
        .max_depth(Some(6))
        .filter_entry(|entry| {
            if let Some(name) = entry.file_name().to_str() {
                !should_skip(name)
            } else {
                true
            }
        })
        .build();

    for entry in walker.flatten() {
        let entry_path = entry.path();
        if !entry_path.is_file() {
            continue;
        }

        let file_name = match entry_path.file_name().and_then(|n| n.to_str()) {
            Some(n) => n.to_lowercase(),
            None => continue,
        };

        let rel_path = match entry_path.strip_prefix(root) {
            Ok(r) => r.to_string_lossy().to_string(),
            Err(_) => continue,
        };

        if seen.contains(&rel_path) {
            continue;
        }

        // Check Python entry points by name
        if PYTHON_ENTRY_NAMES.iter().any(|n| *n == file_name) {
            let kind = if file_name == "manage.py" {
                "django_manage"
            } else if file_name == "__main__.py" {
                "python_package_main"
            } else if file_name == "wsgi.py" || file_name == "asgi.py" {
                "python_wsgi"
            } else {
                "python_main"
            };
            let desc = match kind {
                "django_manage" => "Django management script",
                "python_package_main" => "Python package entry point",
                "python_wsgi" => "WSGI/ASGI server entry",
                _ => "Python main module",
            };
            seen.insert(rel_path.clone());
            entries.push(EntryPoint {
                path: rel_path,
                kind: kind.to_string(),
                description: desc.to_string(),
            });
            continue;
        }

        // Check JS/TS entry points by name
        if JS_ENTRY_NAMES.iter().any(|n| *n == file_name) {
            seen.insert(rel_path.clone());
            entries.push(EntryPoint {
                path: rel_path,
                kind: "js_entry".to_string(),
                description: "JavaScript/TypeScript entry point".to_string(),
            });
            continue;
        }

        // Check file content for patterns (only source files, max 50KB)
        let ext = entry_path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("");
        if !SOURCE_EXTENSIONS.contains(&ext) {
            continue;
        }
        if let Ok(meta) = entry_path.metadata() {
            if meta.len() > 50_000 {
                continue;
            }
        }
        if let Ok(content) = fs::read_to_string(entry_path) {
            if ext == "py" && content.contains("if __name__") && content.contains("__main__") {
                seen.insert(rel_path.clone());
                entries.push(EntryPoint {
                    path: rel_path,
                    kind: "python_main_guard".to_string(),
                    description: "Python script with __main__ guard".to_string(),
                });
            } else if ["js", "ts", "mjs", "mts"].contains(&ext) {
                if content.contains("createServer")
                    || content.contains(".listen(")
                    || content.contains("createApp")
                    || content.contains("express()")
                {
                    seen.insert(rel_path.clone());
                    entries.push(EntryPoint {
                        path: rel_path,
                        kind: "js_server".to_string(),
                        description: "Server/app creation detected".to_string(),
                    });
                }
            }
        }
    }

    Ok(EntryPointsResult { entry_points: entries })
}

/// Extract a string value for a top-level key from JSON (simple, no serde needed).
fn extract_json_string(json: &str, key: &str) -> Option<String> {
    let pattern = format!("\"{}\"", key);
    let pos = json.find(&pattern)?;
    let after = &json[pos + pattern.len()..];
    // Skip whitespace and colon
    let after = after.trim_start();
    let after = after.strip_prefix(':')?;
    let after = after.trim_start();
    // Extract quoted value
    let after = after.strip_prefix('"')?;
    let end = after.find('"')?;
    Some(after[..end].to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_detect_main_py() {
        let tmp = tempfile::tempdir().unwrap();
        fs::write(tmp.path().join("main.py"), "print('hello')").unwrap();

        let result = scan_entry_points(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.entry_points.len(), 1);
        assert_eq!(result.entry_points[0].kind, "python_main");
    }

    #[test]
    fn test_detect_manage_py() {
        let tmp = tempfile::tempdir().unwrap();
        fs::write(tmp.path().join("manage.py"), "#!/usr/bin/env python").unwrap();

        let result = scan_entry_points(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.entry_points[0].kind, "django_manage");
    }

    #[test]
    fn test_detect_index_js() {
        let tmp = tempfile::tempdir().unwrap();
        fs::write(tmp.path().join("index.js"), "module.exports = {}").unwrap();

        let result = scan_entry_points(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.entry_points[0].kind, "js_entry");
    }

    #[test]
    fn test_detect_main_guard() {
        let tmp = tempfile::tempdir().unwrap();
        fs::write(
            tmp.path().join("worker.py"),
            "def run():\n    pass\n\nif __name__ == \"__main__\":\n    run()\n",
        )
        .unwrap();

        let result = scan_entry_points(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.entry_points.len(), 1);
        assert_eq!(result.entry_points[0].kind, "python_main_guard");
    }

    #[test]
    fn test_detect_package_json() {
        let tmp = tempfile::tempdir().unwrap();
        fs::write(
            tmp.path().join("package.json"),
            r#"{"name": "app", "main": "index.js", "scripts": {"start": "node index.js", "dev": "nodemon"}}"#,
        )
        .unwrap();

        let result = scan_entry_points(tmp.path().to_str().unwrap()).unwrap();
        assert!(result.entry_points.iter().any(|e| e.kind == "package_json"));
    }

    #[test]
    fn test_empty_project() {
        let tmp = tempfile::tempdir().unwrap();
        let result = scan_entry_points(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.entry_points.len(), 0);
    }
}
```

- [ ] **Step 2: Update lib.rs**

```rust
//! health — project health scanner for vibe coders.

mod common;
mod file_tree;
mod entry_points;

use pyo3::prelude::*;

#[pymodule]
fn health(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<file_tree::FileTreeResult>()?;
    m.add_function(wrap_pyfunction!(file_tree::scan_file_tree, m)?)?;

    m.add_class::<entry_points::EntryPoint>()?;
    m.add_class::<entry_points::EntryPointsResult>()?;
    m.add_function(wrap_pyfunction!(entry_points::scan_entry_points, m)?)?;

    Ok(())
}
```

- [ ] **Step 3: Build and test**

Run:
```bash
cd crates/health && ~/.cargo/bin/cargo test 2>&1
```
Expected: 9 tests pass (3 file_tree + 6 entry_points)

- [ ] **Step 4: Commit**

```bash
git add crates/health/src/entry_points.rs crates/health/src/lib.rs
git commit -m "feat: add Check 1.2 entry_points detection (Rust)"
```

---

### Task 3: monsters module (Rust)

**Files:**
- Create: `crates/health/src/monsters.rs`
- Modify: `crates/health/src/lib.rs`

- [ ] **Step 1: Create monsters.rs**

```rust
//! Check 1.4 — Monster File Detection.
//!
//! Finds files > 500 lines with function/class counts via tree-sitter.

use std::fs;
use std::path::Path;

use ignore::WalkBuilder;
use pyo3::prelude::*;

use crate::common::{should_skip, SOURCE_EXTENSIONS};

#[pyclass]
#[derive(Clone)]
pub struct MonsterFile {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub lines: u32,
    #[pyo3(get)]
    pub functions: u32,
    #[pyo3(get)]
    pub classes: u32,
    #[pyo3(get)]
    pub severity: String,
}

#[pyclass]
#[derive(Clone)]
pub struct MonstersResult {
    #[pyo3(get)]
    pub monsters: Vec<MonsterFile>,
}

fn severity_for_lines(lines: u32) -> Option<&'static str> {
    if lines > 3000 {
        Some("critical")
    } else if lines > 1000 {
        Some("high")
    } else if lines > 500 {
        Some("medium")
    } else {
        None
    }
}

fn count_definitions_python(content: &str) -> (u32, u32) {
    let mut parser = tree_sitter::Parser::new();
    parser
        .set_language(&tree_sitter_python::LANGUAGE.into())
        .ok();

    let tree = match parser.parse(content, None) {
        Some(t) => t,
        None => return (0, 0),
    };

    let mut functions: u32 = 0;
    let mut classes: u32 = 0;

    let mut cursor = tree.walk();
    walk_nodes(&mut cursor, &mut |node| {
        match node.kind() {
            "function_definition" => functions += 1,
            "class_definition" => classes += 1,
            _ => {}
        }
    });

    (functions, classes)
}

fn count_definitions_js(content: &str, is_ts: bool) -> (u32, u32) {
    let mut parser = tree_sitter::Parser::new();
    if is_ts {
        parser
            .set_language(&tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into())
            .ok();
    } else {
        parser
            .set_language(&tree_sitter_javascript::LANGUAGE.into())
            .ok();
    }

    let tree = match parser.parse(content, None) {
        Some(t) => t,
        None => return (0, 0),
    };

    let mut functions: u32 = 0;
    let mut classes: u32 = 0;

    let mut cursor = tree.walk();
    walk_nodes(&mut cursor, &mut |node| {
        match node.kind() {
            "function_declaration" | "arrow_function" | "method_definition"
            | "function_expression" | "generator_function_declaration" => functions += 1,
            "class_declaration" => classes += 1,
            _ => {}
        }
    });

    (functions, classes)
}

/// Recursively walk all nodes in the tree, calling f on each.
fn walk_nodes<F>(cursor: &mut tree_sitter::TreeCursor, f: &mut F)
where
    F: FnMut(tree_sitter::Node),
{
    f(cursor.node());
    if cursor.goto_first_child() {
        loop {
            walk_nodes(cursor, f);
            if !cursor.goto_next_sibling() {
                break;
            }
        }
        cursor.goto_parent();
    }
}

#[pyfunction]
pub fn scan_monsters(path: &str) -> PyResult<MonstersResult> {
    let root = Path::new(path);
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Not a directory: {}", path),
        ));
    }

    let mut monsters: Vec<MonsterFile> = Vec::new();

    let walker = WalkBuilder::new(root)
        .hidden(false)
        .git_ignore(true)
        .git_global(false)
        .git_exclude(true)
        .filter_entry(|entry| {
            if let Some(name) = entry.file_name().to_str() {
                !should_skip(name)
            } else {
                true
            }
        })
        .build();

    for entry in walker.flatten() {
        let entry_path = entry.path();
        if !entry_path.is_file() {
            continue;
        }

        let ext = match entry_path.extension().and_then(|e| e.to_str()) {
            Some(e) => e,
            None => continue,
        };

        if !SOURCE_EXTENSIONS.contains(&ext) {
            continue;
        }

        // Count non-empty lines
        let content = match fs::read_to_string(entry_path) {
            Ok(c) => c,
            Err(_) => continue,
        };

        let line_count = content.lines().filter(|l| !l.trim().is_empty()).count() as u32;

        let severity = match severity_for_lines(line_count) {
            Some(s) => s,
            None => continue,
        };

        let (functions, classes) = if ext == "py" {
            count_definitions_python(&content)
        } else if ext == "ts" || ext == "tsx" || ext == "mts" || ext == "cts" {
            count_definitions_js(&content, true)
        } else {
            count_definitions_js(&content, false)
        };

        let rel_path = entry_path
            .strip_prefix(root)
            .unwrap_or(entry_path)
            .to_string_lossy()
            .to_string();

        monsters.push(MonsterFile {
            path: rel_path,
            lines: line_count,
            functions,
            classes,
            severity: severity.to_string(),
        });
    }

    // Sort by lines descending
    monsters.sort_by(|a, b| b.lines.cmp(&a.lines));

    Ok(MonstersResult { monsters })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_no_monsters_in_small_files() {
        let tmp = tempfile::tempdir().unwrap();
        fs::write(tmp.path().join("small.py"), "x = 1\ny = 2\n").unwrap();

        let result = scan_monsters(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.monsters.len(), 0);
    }

    #[test]
    fn test_detect_monster_python() {
        let tmp = tempfile::tempdir().unwrap();
        // 600 non-empty lines + 5 functions
        let mut content = String::new();
        for i in 0..5 {
            content.push_str(&format!("def func_{}():\n", i));
            for j in 0..119 {
                content.push_str(&format!("    x_{} = {}\n", j, j));
            }
        }
        fs::write(tmp.path().join("big.py"), &content).unwrap();

        let result = scan_monsters(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.monsters.len(), 1);
        assert_eq!(result.monsters[0].severity, "medium");
        assert_eq!(result.monsters[0].functions, 5);
    }

    #[test]
    fn test_detect_monster_js() {
        let tmp = tempfile::tempdir().unwrap();
        let mut content = String::new();
        for i in 0..3 {
            content.push_str(&format!("function handler_{}() {{\n", i));
            for j in 0..400 {
                content.push_str(&format!("  const x_{} = {};\n", j, j));
            }
            content.push_str("}\n");
        }
        fs::write(tmp.path().join("big.js"), &content).unwrap();

        let result = scan_monsters(tmp.path().to_str().unwrap()).unwrap();
        assert!(result.monsters.len() >= 1);
        assert_eq!(result.monsters[0].severity, "high"); // >1000 lines
    }

    #[test]
    fn test_sorted_by_lines_desc() {
        let tmp = tempfile::tempdir().unwrap();

        // 600-line file
        let mut small_monster = String::new();
        for i in 0..600 {
            small_monster.push_str(&format!("x_{} = {}\n", i, i));
        }
        fs::write(tmp.path().join("medium.py"), &small_monster).unwrap();

        // 1500-line file
        let mut big_monster = String::new();
        for i in 0..1500 {
            big_monster.push_str(&format!("y_{} = {}\n", i, i));
        }
        fs::write(tmp.path().join("big.py"), &big_monster).unwrap();

        let result = scan_monsters(tmp.path().to_str().unwrap()).unwrap();
        assert_eq!(result.monsters.len(), 2);
        assert!(result.monsters[0].lines > result.monsters[1].lines);
    }
}
```

- [ ] **Step 2: Update lib.rs — add monsters**

```rust
//! health — project health scanner for vibe coders.

mod common;
mod file_tree;
mod entry_points;
mod monsters;

use pyo3::prelude::*;

#[pymodule]
fn health(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<file_tree::FileTreeResult>()?;
    m.add_function(wrap_pyfunction!(file_tree::scan_file_tree, m)?)?;

    m.add_class::<entry_points::EntryPoint>()?;
    m.add_class::<entry_points::EntryPointsResult>()?;
    m.add_function(wrap_pyfunction!(entry_points::scan_entry_points, m)?)?;

    m.add_class::<monsters::MonsterFile>()?;
    m.add_class::<monsters::MonstersResult>()?;
    m.add_function(wrap_pyfunction!(monsters::scan_monsters, m)?)?;

    Ok(())
}
```

- [ ] **Step 3: Build and test**

Run:
```bash
cd crates/health && ~/.cargo/bin/cargo test 2>&1
```
Expected: 13 tests pass (3 + 6 + 4)

- [ ] **Step 4: Commit**

```bash
git add crates/health/src/monsters.rs crates/health/src/lib.rs
git commit -m "feat: add Check 1.4 monster file detection with tree-sitter (Rust)"
```

---

### Task 4: module_map module (Rust + tree-sitter)

**Files:**
- Create: `crates/health/src/module_map.rs`
- Modify: `crates/health/src/lib.rs`

- [ ] **Step 1: Create module_map.rs**

```rust
//! Check 1.3 — Module/Component Map.
//!
//! Parses imports via tree-sitter, builds dependency graph,
//! finds hub modules and circular dependencies.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

use ignore::WalkBuilder;
use pyo3::prelude::*;

use crate::common::{should_skip, SOURCE_EXTENSIONS};

#[pyclass]
#[derive(Clone)]
pub struct ModuleInfo {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub imports: Vec<String>,
    #[pyo3(get)]
    pub imported_by_count: u32,
}

#[pyclass]
#[derive(Clone)]
pub struct ModuleMapResult {
    #[pyo3(get)]
    pub modules: Vec<ModuleInfo>,
    #[pyo3(get)]
    pub hub_modules: Vec<(String, u32)>,
    #[pyo3(get)]
    pub circular_deps: Vec<(String, String)>,
    #[pyo3(get)]
    pub orphan_candidates: Vec<String>,
}

/// Extract import sources from Python file using tree-sitter.
fn extract_python_imports(content: &str) -> Vec<String> {
    let mut parser = tree_sitter::Parser::new();
    if parser
        .set_language(&tree_sitter_python::LANGUAGE.into())
        .is_err()
    {
        return vec![];
    }

    let tree = match parser.parse(content, None) {
        Some(t) => t,
        None => return vec![],
    };

    let mut imports = Vec::new();
    let mut cursor = tree.walk();

    collect_imports_recursive(&mut cursor, content, &mut imports, "python");

    imports
}

/// Extract import sources from JS/TS file using tree-sitter.
fn extract_js_imports(content: &str, is_ts: bool) -> Vec<String> {
    let mut parser = tree_sitter::Parser::new();
    let lang = if is_ts {
        tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into()
    } else {
        tree_sitter_javascript::LANGUAGE.into()
    };
    if parser.set_language(&lang).is_err() {
        return vec![];
    }

    let tree = match parser.parse(content, None) {
        Some(t) => t,
        None => return vec![],
    };

    let mut imports = Vec::new();
    let mut cursor = tree.walk();

    collect_imports_recursive(&mut cursor, content, &mut imports, "js");

    imports
}

fn collect_imports_recursive(
    cursor: &mut tree_sitter::TreeCursor,
    source: &str,
    imports: &mut Vec<String>,
    lang: &str,
) {
    let node = cursor.node();

    match lang {
        "python" => {
            // import foo → "foo"
            // from foo import bar → "foo"
            // from .foo import bar → ".foo" (relative)
            if node.kind() == "import_statement" || node.kind() == "import_from_statement" {
                if let Some(module_node) = node.child_by_field_name("module_name")
                    .or_else(|| {
                        // For "from X import Y", module name is in "module_name" field
                        // For "import X", it's in "name" field
                        node.child_by_field_name("name")
                    })
                {
                    if let Ok(text) = module_node.utf8_text(source.as_bytes()) {
                        imports.push(text.to_string());
                    }
                } else {
                    // Try to get the dotted_name child directly
                    for i in 0..node.child_count() {
                        if let Some(child) = node.child(i) {
                            if child.kind() == "dotted_name" || child.kind() == "relative_import" {
                                if let Ok(text) = child.utf8_text(source.as_bytes()) {
                                    imports.push(text.to_string());
                                }
                                break;
                            }
                        }
                    }
                }
            }
        }
        "js" => {
            // import X from 'Y' → source is string node
            // require('Y') → source is string argument
            if node.kind() == "import_statement" {
                if let Some(source_node) = node.child_by_field_name("source") {
                    if let Ok(text) = source_node.utf8_text(source.as_bytes()) {
                        let cleaned = text.trim_matches(|c| c == '\'' || c == '"');
                        imports.push(cleaned.to_string());
                    }
                }
            } else if node.kind() == "call_expression" {
                if let Some(func) = node.child_by_field_name("function") {
                    if let Ok(fname) = func.utf8_text(source.as_bytes()) {
                        if fname == "require" {
                            if let Some(args) = node.child_by_field_name("arguments") {
                                if args.child_count() >= 2 {
                                    // (  "string"  )
                                    if let Some(arg) = args.child(1) {
                                        if arg.kind() == "string" {
                                            if let Ok(text) =
                                                arg.utf8_text(source.as_bytes())
                                            {
                                                let cleaned = text
                                                    .trim_matches(|c| c == '\'' || c == '"');
                                                imports.push(cleaned.to_string());
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        _ => {}
    }

    if cursor.goto_first_child() {
        loop {
            collect_imports_recursive(cursor, source, imports, lang);
            if !cursor.goto_next_sibling() {
                break;
            }
        }
        cursor.goto_parent();
    }
}

/// Check if an import string looks like a local/relative import.
fn is_local_import(imp: &str, lang: &str) -> bool {
    match lang {
        "python" => imp.starts_with('.'),
        "js" => imp.starts_with("./") || imp.starts_with("../"),
        _ => false,
    }
}

/// Try to resolve a local import to a project file path.
fn resolve_local_import(
    imp: &str,
    source_file: &Path,
    root: &Path,
    all_files: &HashSet<String>,
    lang: &str,
) -> Option<String> {
    let source_dir = source_file.parent()?;

    let relative_path = match lang {
        "python" => {
            // .foo → foo.py or foo/__init__.py in same dir
            // ..foo → parent dir
            let dots = imp.chars().take_while(|c| *c == '.').count();
            let module = &imp[dots..];
            let mut base = source_dir.to_path_buf();
            for _ in 1..dots {
                base = base.parent()?.to_path_buf();
            }
            if module.is_empty() {
                return None;
            }
            let module_path = module.replace('.', "/");
            base.join(module_path)
        }
        "js" => {
            let resolved = source_dir.join(imp);
            resolved
        }
        _ => return None,
    };

    // Try exact match, then with extensions
    let rel = relative_path.strip_prefix(root).ok()?;
    let rel_str = rel.to_string_lossy().to_string();

    // Direct match
    if all_files.contains(&rel_str) {
        return Some(rel_str);
    }

    // Try with extensions
    let extensions: &[&str] = match lang {
        "python" => &["py"],
        "js" => &["js", "ts", "jsx", "tsx", "mjs", "mts"],
        _ => &[],
    };

    for ext in extensions {
        let with_ext = format!("{}.{}", rel_str, ext);
        if all_files.contains(&with_ext) {
            return Some(with_ext);
        }
        // Try index file in directory
        let index = format!("{}/index.{}", rel_str, ext);
        if all_files.contains(&index) {
            return Some(index);
        }
    }

    // Python: try __init__.py
    if lang == "python" {
        let init = format!("{}/__init__.py", rel_str);
        if all_files.contains(&init) {
            return Some(init);
        }
    }

    None
}

#[pyfunction]
pub fn scan_module_map(path: &str, entry_point_paths: Vec<String>) -> PyResult<ModuleMapResult> {
    let root = Path::new(path);
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Not a directory: {}", path),
        ));
    }

    // Collect all source files
    let mut all_files: HashSet<String> = HashSet::new();
    let mut source_files: Vec<(PathBuf, String)> = Vec::new(); // (abs_path, rel_path)

    let walker = WalkBuilder::new(root)
        .hidden(false)
        .git_ignore(true)
        .git_global(false)
        .git_exclude(true)
        .filter_entry(|entry| {
            if let Some(name) = entry.file_name().to_str() {
                !should_skip(name)
            } else {
                true
            }
        })
        .build();

    for entry in walker.flatten() {
        let entry_path = entry.path();
        if !entry_path.is_file() {
            continue;
        }
        let ext = match entry_path.extension().and_then(|e| e.to_str()) {
            Some(e) => e.to_string(),
            None => continue,
        };
        if !SOURCE_EXTENSIONS.contains(&ext.as_str()) {
            continue;
        }
        if let Ok(rel) = entry_path.strip_prefix(root) {
            let rel_str = rel.to_string_lossy().to_string();
            all_files.insert(rel_str.clone());
            source_files.push((entry_path.to_path_buf(), rel_str));
        }
    }

    // Parse imports for each file
    let mut file_imports: HashMap<String, Vec<String>> = HashMap::new();
    let mut imported_by: HashMap<String, u32> = HashMap::new();

    for (abs_path, rel_path) in &source_files {
        let ext = abs_path
            .extension()
            .and_then(|e| e.to_str())
            .unwrap_or("");

        let content = match fs::read_to_string(abs_path) {
            Ok(c) => c,
            Err(_) => continue,
        };

        let lang = if ext == "py" { "python" } else { "js" };
        let is_ts = ext == "ts" || ext == "tsx" || ext == "mts" || ext == "cts";

        let raw_imports = if ext == "py" {
            extract_python_imports(&content)
        } else {
            extract_js_imports(&content, is_ts)
        };

        // Resolve local imports to file paths
        let mut resolved = Vec::new();
        for imp in &raw_imports {
            if is_local_import(imp, lang) {
                if let Some(resolved_path) =
                    resolve_local_import(imp, abs_path, root, &all_files, lang)
                {
                    resolved.push(resolved_path.clone());
                    *imported_by.entry(resolved_path).or_insert(0) += 1;
                }
            }
        }

        file_imports.insert(rel_path.clone(), resolved);
    }

    // Build modules list
    let mut modules: Vec<ModuleInfo> = Vec::new();
    for (rel_path, imports) in &file_imports {
        let count = imported_by.get(rel_path).copied().unwrap_or(0);
        modules.push(ModuleInfo {
            path: rel_path.clone(),
            imports: imports.clone(),
            imported_by_count: count,
        });
    }

    // Hub modules: top 5 most imported
    let mut hub_list: Vec<(String, u32)> = imported_by
        .iter()
        .map(|(k, v)| (k.clone(), *v))
        .collect();
    hub_list.sort_by(|a, b| b.1.cmp(&a.1));
    let hub_modules: Vec<(String, u32)> = hub_list.into_iter().take(5).collect();

    // Circular dependency detection (direct A→B and B→A)
    let mut circular: Vec<(String, String)> = Vec::new();
    let mut seen_pairs: HashSet<(String, String)> = HashSet::new();

    for (file, imports) in &file_imports {
        for imp in imports {
            if let Some(reverse_imports) = file_imports.get(imp) {
                if reverse_imports.contains(file) {
                    let pair = if file < imp {
                        (file.clone(), imp.clone())
                    } else {
                        (imp.clone(), file.clone())
                    };
                    if seen_pairs.insert(pair.clone()) {
                        circular.push(pair);
                    }
                }
            }
        }
    }

    // Orphan candidates: files not imported by anyone and not entry points
    let entry_set: HashSet<&str> = entry_point_paths.iter().map(|s| s.as_str()).collect();
    let orphan_candidates: Vec<String> = all_files
        .iter()
        .filter(|f| {
            !imported_by.contains_key(*f)
                && !entry_set.contains(f.as_str())
                && !f.ends_with("__init__.py")
                && !f.ends_with("conftest.py")
                && !f.contains("/test")
                && !f.starts_with("test")
        })
        .cloned()
        .collect();

    Ok(ModuleMapResult {
        modules,
        hub_modules,
        circular_deps: circular,
        orphan_candidates,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_python_imports() {
        let content = "import os\nfrom pathlib import Path\nfrom .utils import helper\n";
        let imports = extract_python_imports(content);
        assert!(imports.len() >= 2);
    }

    #[test]
    fn test_js_imports() {
        let content = r#"import React from 'react';
import { helper } from './utils';
const fs = require('fs');
const local = require('./local');
"#;
        let imports = extract_js_imports(content, false);
        assert!(imports.iter().any(|i| i == "react"));
        assert!(imports.iter().any(|i| i == "./utils"));
    }

    #[test]
    fn test_hub_detection() {
        let tmp = tempfile::tempdir().unwrap();

        // utils.py — will be a hub
        fs::write(tmp.path().join("utils.py"), "def helper():\n    pass\n").unwrap();

        // Three files importing utils
        for name in &["a.py", "b.py", "c.py"] {
            fs::write(
                tmp.path().join(name),
                "from .utils import helper\n",
            )
            .unwrap();
        }

        // __init__.py to make relative imports work
        fs::write(tmp.path().join("__init__.py"), "").unwrap();

        let result = scan_module_map(tmp.path().to_str().unwrap(), vec![]).unwrap();
        // utils.py should be in hub_modules
        assert!(
            result.hub_modules.iter().any(|(p, _)| p == "utils.py"),
            "utils.py should be a hub, got: {:?}",
            result.hub_modules
        );
    }

    #[test]
    fn test_circular_detection() {
        let tmp = tempfile::tempdir().unwrap();

        fs::write(tmp.path().join("a.py"), "from .b import x\n").unwrap();
        fs::write(tmp.path().join("b.py"), "from .a import y\n").unwrap();
        fs::write(tmp.path().join("__init__.py"), "").unwrap();

        let result = scan_module_map(tmp.path().to_str().unwrap(), vec![]).unwrap();
        assert!(
            !result.circular_deps.is_empty(),
            "Should detect circular dep between a.py and b.py"
        );
    }

    #[test]
    fn test_orphan_detection() {
        let tmp = tempfile::tempdir().unwrap();

        fs::write(tmp.path().join("main.py"), "print('hello')\n").unwrap();
        fs::write(tmp.path().join("orphan.py"), "x = 1\n").unwrap();

        let result = scan_module_map(
            tmp.path().to_str().unwrap(),
            vec!["main.py".to_string()],
        )
        .unwrap();
        assert!(
            result.orphan_candidates.contains(&"orphan.py".to_string()),
            "orphan.py should be detected as orphan"
        );
    }
}
```

- [ ] **Step 2: Update lib.rs — add module_map**

```rust
//! health — project health scanner for vibe coders.

mod common;
mod file_tree;
mod entry_points;
mod monsters;
mod module_map;

use pyo3::prelude::*;

#[pymodule]
fn health(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<file_tree::FileTreeResult>()?;
    m.add_function(wrap_pyfunction!(file_tree::scan_file_tree, m)?)?;

    m.add_class::<entry_points::EntryPoint>()?;
    m.add_class::<entry_points::EntryPointsResult>()?;
    m.add_function(wrap_pyfunction!(entry_points::scan_entry_points, m)?)?;

    m.add_class::<monsters::MonsterFile>()?;
    m.add_class::<monsters::MonstersResult>()?;
    m.add_function(wrap_pyfunction!(monsters::scan_monsters, m)?)?;

    m.add_class::<module_map::ModuleInfo>()?;
    m.add_class::<module_map::ModuleMapResult>()?;
    m.add_function(wrap_pyfunction!(module_map::scan_module_map, m)?)?;

    Ok(())
}
```

- [ ] **Step 3: Build and test**

Run:
```bash
cd crates/health && ~/.cargo/bin/cargo test 2>&1
```
Expected: 18 tests pass (3 + 6 + 4 + 5)

- [ ] **Step 4: Build Python wheel and verify**

Run:
```bash
cd crates/health && maturin develop 2>&1
python -c "import health; print(dir(health))"
```
Expected: shows all 4 scan functions + result classes

- [ ] **Step 5: Commit**

```bash
git add crates/health/src/module_map.rs crates/health/src/lib.rs
git commit -m "feat: add Check 1.3 module_map with tree-sitter import parsing (Rust)"
```

---

### Task 5: Python models + orchestrator + Check 1.5

**Files:**
- Create: `core/health/__init__.py`
- Create: `core/health/models.py`
- Create: `core/health/project_map.py`
- Create: `core/health/tips.py`
- Test: `tests/test_health_models.py`
- Test: `tests/test_health_project_map.py`

- [ ] **Step 1: Create __init__.py**

```python
# core/health/__init__.py
```

- [ ] **Step 2: Create models.py**

```python
"""Data models for health check results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConfigFile:
    path: str
    kind: str           # "env", "docker", "python_deps", "js_config", "ci", "build"
    description: str
    severity: str       # "warning", "info"


@dataclass
class ConfigInventoryResult:
    configs: list[ConfigFile] = field(default_factory=list)
    env_file_count: int = 0
    has_docker: bool = False
    has_ci: bool = False


@dataclass
class HealthFinding:
    check_id: str       # "map.file_tree", "map.entry_points", etc.
    title: str
    severity: str       # "critical", "high", "medium", "low", "info"
    message: str        # Human-readable description
    details: dict = field(default_factory=dict)


@dataclass
class HealthReport:
    project_dir: str
    findings: list[HealthFinding] = field(default_factory=list)
    file_tree: dict = field(default_factory=dict)
    entry_points: list[dict] = field(default_factory=list)
    module_map: dict = field(default_factory=dict)
    monsters: list[dict] = field(default_factory=list)
    configs: list[dict] = field(default_factory=list)
```

- [ ] **Step 3: Create tips.py**

```python
"""Tip generation for health check results."""

from __future__ import annotations


def tip_file_tree(total_files: int, top_ext: str, top_count: int) -> str:
    return (
        f"In your project: {total_files} files. "
        f"Most common: .{top_ext} ({top_count}). "
        f"This is just context — now you know what's inside."
    )


def tip_entry_points(count: int) -> str:
    if count == 0:
        return (
            "No entry points found. "
            "An entry point is where your app starts — like a front door. "
            "Usually main.py, index.js, or a package.json script."
        )
    return (
        f"Entry point = the file where everything starts. Like doors to a building. "
        f"You have {count}."
    )


def tip_hub_module(path: str, count: int) -> str:
    return (
        f"{path} is imported by {count} files. "
        f"This is your most important module. Break it — break everything."
    )


def tip_circular(a: str, b: str) -> str:
    return (
        f"{a} imports {b}, and {b} imports {a}. "
        f"A circular dependency — can break during refactoring."
    )


def tip_orphan(path: str) -> str:
    return (
        f"{path} — nobody imports it, not an entry point. "
        f"If you need it — move to archive/. If not — delete."
    )


def tip_monster(path: str, lines: int, functions: int) -> str:
    if lines > 3000:
        tone = "This isn't a file, it's a novel."
    elif lines > 1000:
        tone = "This file needs splitting."
    else:
        tone = "Getting big."
    return (
        f"{path} — {lines} lines, {functions} functions. "
        f"{tone} One file = one responsibility."
    )


def tip_env_files(count: int) -> str:
    if count > 1:
        return (
            f"You have {count} .env files in different directories. "
            f"That's chaos. Usually one .env in root is enough."
        )
    return "One .env file — that's clean."


def tip_no_configs() -> str:
    return "No config files found. This project might need a setup."
```

- [ ] **Step 4: Create project_map.py**

```python
"""Check 1.5 — Config & Env Inventory + orchestrator for all Phase 1 checks."""

from __future__ import annotations

import glob
import logging
from pathlib import Path

from core.health.models import (
    ConfigFile, ConfigInventoryResult, HealthFinding, HealthReport,
)
from core.health import tips

log = logging.getLogger(__name__)

# Config file patterns: (glob_pattern, kind, description_template)
_CONFIG_PATTERNS: list[tuple[str, str, str]] = [
    (".env", "env", "Environment variables"),
    (".env.*", "env", "Environment variables"),
    ("docker-compose*.yml", "docker", "Docker Compose config"),
    ("docker-compose*.yaml", "docker", "Docker Compose config"),
    ("Dockerfile*", "docker", "Docker image build"),
    ("pyproject.toml", "python_deps", "Python project config"),
    ("setup.py", "python_deps", "Python package config"),
    ("setup.cfg", "python_deps", "Python package config"),
    ("requirements*.txt", "python_deps", "Python dependencies"),
    ("Pipfile", "python_deps", "Python dependencies (Pipenv)"),
    ("package.json", "js_config", "Node.js project config"),
    ("tsconfig*.json", "js_config", "TypeScript config"),
    ("Makefile", "build", "Build/automation commands"),
    ("Procfile", "build", "Production process config"),
    (".github/workflows/*.yml", "ci", "GitHub Actions CI/CD"),
    (".github/workflows/*.yaml", "ci", "GitHub Actions CI/CD"),
    (".gitlab-ci.yml", "ci", "GitLab CI/CD"),
]


def scan_config_inventory(project_dir: str) -> ConfigInventoryResult:
    """Check 1.5 — find all config files in the project."""
    root = Path(project_dir)
    configs: list[ConfigFile] = []
    env_count = 0
    has_docker = False
    has_ci = False
    seen_paths: set[str] = set()

    for pattern, kind, desc_template in _CONFIG_PATTERNS:
        for match_path in root.glob(pattern):
            rel = str(match_path.relative_to(root))
            if rel in seen_paths:
                continue
            seen_paths.add(rel)

            description = desc_template
            severity = "info"

            if kind == "env":
                env_count += 1
                severity = "warning"
                # Count variables (lines without comments/empty)
                try:
                    lines = match_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    var_count = sum(
                        1 for l in lines
                        if l.strip() and not l.strip().startswith("#")
                    )
                    description = f"{desc_template} ({var_count} vars)"
                except OSError:
                    pass

            if kind == "docker":
                has_docker = True
            if kind == "ci":
                has_ci = True

            configs.append(ConfigFile(
                path=rel,
                kind=kind,
                description=description,
                severity=severity,
            ))

    return ConfigInventoryResult(
        configs=configs,
        env_file_count=env_count,
        has_docker=has_docker,
        has_ci=has_ci,
    )


def run_all_checks(project_dir: str) -> HealthReport:
    """Run all Phase 1 checks and assemble a HealthReport.

    Calls Rust health crate for checks 1.1-1.4, Python for 1.5.
    Gracefully handles missing Rust crate.
    """
    report = HealthReport(project_dir=project_dir)

    # Try Rust checks
    try:
        import health as health_rs
        _rust_available = True
    except ImportError:
        _rust_available = False
        log.warning("health crate not installed — Rust checks skipped")
        report.findings.append(HealthFinding(
            check_id="system",
            title="Health crate not installed",
            severity="warning",
            message="Build the health crate: cd crates/health && maturin develop",
        ))

    if _rust_available:
        # Check 1.1 — File Tree
        try:
            tree = health_rs.scan_file_tree(project_dir)
            report.file_tree = {
                "total_files": tree.total_files,
                "total_dirs": tree.total_dirs,
                "total_size_bytes": tree.total_size_bytes,
                "max_depth": tree.max_depth,
                "files_by_ext": dict(tree.files_by_ext),
                "largest_dirs": list(tree.largest_dirs),
            }
            # Generate tip
            ext_sorted = sorted(tree.files_by_ext.items(), key=lambda x: x[1], reverse=True)
            if ext_sorted:
                top_ext, top_count = ext_sorted[0]
            else:
                top_ext, top_count = "?", 0
            report.findings.append(HealthFinding(
                check_id="map.file_tree",
                title="Project Map",
                severity="info",
                message=tips.tip_file_tree(tree.total_files, top_ext, top_count),
                details=report.file_tree,
            ))
        except Exception as e:
            log.error("file_tree scan error: %s", e)

        # Check 1.2 — Entry Points
        try:
            ep_result = health_rs.scan_entry_points(project_dir)
            ep_list = [
                {"path": ep.path, "kind": ep.kind, "description": ep.description}
                for ep in ep_result.entry_points
            ]
            report.entry_points = ep_list
            severity = "info" if ep_list else "medium"
            report.findings.append(HealthFinding(
                check_id="map.entry_points",
                title="Entry Points",
                severity=severity,
                message=tips.tip_entry_points(len(ep_list)),
                details={"entry_points": ep_list},
            ))
        except Exception as e:
            log.error("entry_points scan error: %s", e)

        # Check 1.3 — Module Map
        try:
            entry_paths = [ep["path"] for ep in report.entry_points]
            mm_result = health_rs.scan_module_map(project_dir, entry_paths)
            report.module_map = {
                "hub_modules": list(mm_result.hub_modules),
                "circular_deps": list(mm_result.circular_deps),
                "orphan_candidates": list(mm_result.orphan_candidates),
                "total_modules": len(mm_result.modules),
            }
            # Hub findings
            for path, count in mm_result.hub_modules[:3]:
                report.findings.append(HealthFinding(
                    check_id="map.modules",
                    title=f"Hub: {path}",
                    severity="info",
                    message=tips.tip_hub_module(path, count),
                ))
            # Circular deps
            for a, b in mm_result.circular_deps:
                report.findings.append(HealthFinding(
                    check_id="map.modules",
                    title=f"Circular: {a} ↔ {b}",
                    severity="medium",
                    message=tips.tip_circular(a, b),
                ))
            # Orphans
            for orphan in mm_result.orphan_candidates[:5]:
                report.findings.append(HealthFinding(
                    check_id="map.modules",
                    title=f"Orphan: {orphan}",
                    severity="low",
                    message=tips.tip_orphan(orphan),
                ))
        except Exception as e:
            log.error("module_map scan error: %s", e)

        # Check 1.4 — Monsters
        try:
            monsters_result = health_rs.scan_monsters(project_dir)
            report.monsters = [
                {
                    "path": m.path,
                    "lines": m.lines,
                    "functions": m.functions,
                    "classes": m.classes,
                    "severity": m.severity,
                }
                for m in monsters_result.monsters
            ]
            for m in monsters_result.monsters:
                report.findings.append(HealthFinding(
                    check_id="map.monsters",
                    title=f"Monster: {m.path}",
                    severity=m.severity,
                    message=tips.tip_monster(m.path, m.lines, m.functions),
                ))
        except Exception as e:
            log.error("monsters scan error: %s", e)

    # Check 1.5 — Config Inventory (always Python)
    try:
        config_result = scan_config_inventory(project_dir)
        report.configs = [
            {
                "path": c.path,
                "kind": c.kind,
                "description": c.description,
                "severity": c.severity,
            }
            for c in config_result.configs
        ]
        if config_result.env_file_count > 0:
            report.findings.append(HealthFinding(
                check_id="map.configs",
                title="Config Files",
                severity="warning" if config_result.env_file_count > 1 else "info",
                message=tips.tip_env_files(config_result.env_file_count),
                details={"configs": report.configs},
            ))
        elif config_result.configs:
            report.findings.append(HealthFinding(
                check_id="map.configs",
                title="Config Files",
                severity="info",
                message=f"{len(config_result.configs)} config files found.",
                details={"configs": report.configs},
            ))
    except Exception as e:
        log.error("config inventory error: %s", e)

    return report
```

- [ ] **Step 5: Write tests**

```python
# tests/test_health_models.py
"""Tests for health check models."""

from core.health.models import (
    ConfigFile, ConfigInventoryResult,
    HealthFinding, HealthReport,
)


def test_config_file_creation():
    cf = ConfigFile(path=".env", kind="env", description="Env vars (5)", severity="warning")
    assert cf.kind == "env"
    assert cf.severity == "warning"


def test_health_finding():
    f = HealthFinding(
        check_id="map.file_tree",
        title="Project Map",
        severity="info",
        message="You have 100 files.",
    )
    assert f.check_id == "map.file_tree"
    assert f.details == {}


def test_health_report():
    r = HealthReport(project_dir="/tmp/test")
    assert r.project_dir == "/tmp/test"
    assert r.findings == []
    assert r.monsters == []
```

```python
# tests/test_health_project_map.py
"""Tests for config inventory and orchestrator."""

from pathlib import Path

from core.health.project_map import scan_config_inventory, run_all_checks


def test_config_inventory_finds_env(tmp_path):
    (tmp_path / ".env").write_text("DB_URL=postgres://localhost\nSECRET=abc\n")
    result = scan_config_inventory(str(tmp_path))
    assert result.env_file_count == 1
    assert any(c.kind == "env" for c in result.configs)
    env_config = next(c for c in result.configs if c.kind == "env")
    assert "2 vars" in env_config.description


def test_config_inventory_finds_docker(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
    (tmp_path / "Dockerfile").write_text("FROM python:3.11\n")
    result = scan_config_inventory(str(tmp_path))
    assert result.has_docker is True
    assert len(result.configs) == 2


def test_config_inventory_finds_ci(tmp_path):
    gh_dir = tmp_path / ".github" / "workflows"
    gh_dir.mkdir(parents=True)
    (gh_dir / "ci.yml").write_text("on: push\n")
    result = scan_config_inventory(str(tmp_path))
    assert result.has_ci is True


def test_config_inventory_empty(tmp_path):
    result = scan_config_inventory(str(tmp_path))
    assert len(result.configs) == 0
    assert result.env_file_count == 0


def test_config_inventory_multiple_env(tmp_path):
    (tmp_path / ".env").write_text("A=1\n")
    (tmp_path / ".env.local").write_text("B=2\n")
    result = scan_config_inventory(str(tmp_path))
    assert result.env_file_count == 2


def test_run_all_checks_without_rust(tmp_path):
    """Orchestrator works even without Rust crate — falls back gracefully."""
    (tmp_path / ".env").write_text("KEY=val\n")
    report = run_all_checks(str(tmp_path))
    assert report.project_dir == str(tmp_path)
    # Should have at least config findings (Python check always runs)
    config_findings = [f for f in report.findings if f.check_id == "map.configs"]
    assert len(config_findings) >= 1
```

- [ ] **Step 6: Run tests**

Run:
```bash
python -m pytest tests/test_health_models.py tests/test_health_project_map.py -v
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add core/health/ tests/test_health_models.py tests/test_health_project_map.py
git commit -m "feat: add Python health models, orchestrator, Check 1.5 config inventory"
```

---

### Task 6: i18n strings

**Files:**
- Modify: `i18n/en.py`
- Modify: `i18n/ua.py`

- [ ] **Step 1: Add English strings**

Add to `i18n/en.py` before closing `}`:

```python
    # Dev Health
    "side_health": "Dev Health",
    "health_header": "Dev Health",
    "health_no_dir": "No project directory selected",
    "health_select_dir": "Select project directory to scan",
    "health_btn_select": "Select Directory...",
    "health_btn_scan": "Scan Project",
    "health_scanning": "Scanning...",
    "health_no_results": "Click 'Scan Project' to analyze your codebase",
    "health_empty_project": "Empty project. Nothing to scan.",
    "health_no_crate": "Health crate not installed. Run: cd crates/health && maturin develop",
    "health_section_tree": "Project Map",
    "health_section_entry": "Entry Points",
    "health_section_modules": "Module Hubs",
    "health_section_monsters": "Monster Files",
    "health_section_configs": "Configs",
    "health_section_summary": "Summary",
    "health_severity_critical": "critical",
    "health_severity_high": "high",
    "health_severity_medium": "medium",
    "health_severity_low": "low",
    "health_severity_info": "info",
    "health_files_label": "files",
    "health_dirs_label": "dirs",
    "health_depth_label": "depth",
    "health_orphan_label": "orphan files",

    # Hasselhoff mode — Dev Health
    "hoff_health_header": "The Hoff's Health Check",
    "hoff_health_monster": "Even Hasselhoff can't save a 3000-line file",
    "hoff_health_clean": "Your codebase is beach-ready!",
```

- [ ] **Step 2: Add Ukrainian strings**

Add to `i18n/ua.py` before closing `}`:

```python
    # Dev Health
    "side_health": "Здоров'я коду",
    "health_header": "Здоров'я коду",
    "health_no_dir": "Директорію проєкту не обрано",
    "health_select_dir": "Оберіть директорію для сканування",
    "health_btn_select": "Обрати директорію...",
    "health_btn_scan": "Сканувати проєкт",
    "health_scanning": "Сканую...",
    "health_no_results": "Натисніть 'Сканувати проєкт' для аналізу коду",
    "health_empty_project": "Порожній проєкт. Нічого сканувати.",
    "health_no_crate": "Health модуль не встановлено. Запустіть: cd crates/health && maturin develop",
    "health_section_tree": "Карта проєкту",
    "health_section_entry": "Точки входу",
    "health_section_modules": "Модулі-хаби",
    "health_section_monsters": "Файли-монстри",
    "health_section_configs": "Конфігурація",
    "health_section_summary": "Підсумок",
    "health_severity_critical": "критичний",
    "health_severity_high": "високий",
    "health_severity_medium": "середній",
    "health_severity_low": "низький",
    "health_severity_info": "інфо",
    "health_files_label": "файлів",
    "health_dirs_label": "директорій",
    "health_depth_label": "глибина",
    "health_orphan_label": "файлів-сиріт",

    # Hasselhoff mode — Dev Health
    "hoff_health_header": "Хофф перевіряє здоров'я",
    "hoff_health_monster": "Навіть Хассельхофф не врятує файл на 3000 рядків",
    "hoff_health_clean": "Твій код готовий до пляжу!",
```

- [ ] **Step 3: Commit**

```bash
git add i18n/en.py i18n/ua.py
git commit -m "feat: add Dev Health i18n strings (EN + UA)"
```

---

### Task 7: GUI Health Page

**Files:**
- Create: `gui/pages/health_page.py`

- [ ] **Step 1: Create health_page.py**

```python
"""Dev Health page — project health scanner with human-language results."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFileDialog, QFrame,
)
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtGui import QFont

from i18n import get_string as _t
from core.health.models import HealthReport, HealthFinding


class HealthScanThread(QThread):
    """Run health scan in background thread."""
    scan_done = pyqtSignal(object)

    def __init__(self, project_dir: str, parent=None):
        super().__init__(parent)
        self._dir = project_dir

    def run(self):
        from core.health.project_map import run_all_checks
        report = run_all_checks(self._dir)
        self.scan_done.emit(report)


class HealthPage(QWidget):
    """Dev Health — scan project and show health check results."""

    def __init__(self):
        super().__init__()
        self._project_dir: str | None = None
        self._scan_thread: HealthScanThread | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Header
        header = QHBoxLayout()
        title = QLabel(_t("health_header"))
        title.setFont(QFont("MS Sans Serif", 14, QFont.Bold))
        title.setStyleSheet("color: #000080;")
        header.addWidget(title)
        header.addStretch()

        self._dir_label = QLabel(_t("health_no_dir"))
        self._dir_label.setStyleSheet("color: #808080;")
        header.addWidget(self._dir_label)

        self._btn_select = QPushButton(_t("health_btn_select"))
        self._btn_select.clicked.connect(self._on_select_dir)
        header.addWidget(self._btn_select)

        self._btn_scan = QPushButton(_t("health_btn_scan"))
        self._btn_scan.clicked.connect(self._on_scan)
        self._btn_scan.setEnabled(False)
        self._btn_scan.setStyleSheet(
            "QPushButton { background: #000080; color: white; padding: 6px 16px; "
            "border: 2px outset #4040c0; font-weight: bold; font-size: 13px; }"
            "QPushButton:pressed { border: 2px inset #000080; }"
            "QPushButton:disabled { background: #808080; color: #c0c0c0; }"
        )
        header.addWidget(self._btn_scan)

        layout.addLayout(header)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px inset #808080; background: white; }")

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self._content_widget)

        layout.addWidget(scroll)

        self._show_placeholder(_t("health_select_dir"))

    def _show_placeholder(self, text: str) -> None:
        self._clear_content()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("color: #808080; font-size: 14px; padding: 40px;")
        self._content_layout.addWidget(lbl)

    def _clear_content(self) -> None:
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _on_select_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(
            self, _t("health_btn_select"), str(Path.home()),
        )
        if dir_path:
            self._project_dir = dir_path
            display = dir_path if len(dir_path) <= 50 else "..." + dir_path[-47:]
            self._dir_label.setText(display)
            self._dir_label.setStyleSheet("color: #000000;")
            self._btn_scan.setEnabled(True)
            self._show_placeholder(_t("health_no_results"))

    def _on_scan(self) -> None:
        if not self._project_dir:
            return
        self._btn_scan.setEnabled(False)
        self._btn_scan.setText(_t("health_scanning"))
        self._show_placeholder(_t("health_scanning"))

        self._scan_thread = HealthScanThread(self._project_dir, self)
        self._scan_thread.scan_done.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_done(self, report: HealthReport) -> None:
        self._btn_scan.setEnabled(True)
        self._btn_scan.setText(_t("health_btn_scan"))
        self._render_report(report)

    def _render_report(self, report: HealthReport) -> None:
        self._clear_content()

        if not report.findings:
            self._show_placeholder(_t("health_empty_project"))
            return

        # Group findings by check_id prefix
        sections = {
            "map.file_tree": (_t("health_section_tree"), []),
            "map.entry_points": (_t("health_section_entry"), []),
            "map.modules": (_t("health_section_modules"), []),
            "map.monsters": (_t("health_section_monsters"), []),
            "map.configs": (_t("health_section_configs"), []),
            "system": ("System", []),
        }

        for finding in report.findings:
            key = finding.check_id
            if key in sections:
                sections[key][1].append(finding)
            else:
                sections.setdefault(key, (key, []))[1].append(finding)

        # File tree summary (special rendering)
        if report.file_tree:
            tree = report.file_tree
            group = self._make_group(
                f"{_t('health_section_tree')} — "
                f"{tree['total_files']} {_t('health_files_label')} | "
                f"{tree['total_dirs']} {_t('health_dirs_label')} | "
                f"{self._format_size(tree['total_size_bytes'])} | "
                f"{_t('health_depth_label')} {tree['max_depth']}"
            )
            gl = group.layout()
            # Extension breakdown
            ext_sorted = sorted(
                tree["files_by_ext"].items(), key=lambda x: x[1], reverse=True
            )
            ext_str = "  ".join(f".{ext}: {count}" for ext, count in ext_sorted[:8])
            ext_lbl = QLabel(ext_str)
            ext_lbl.setStyleSheet("font-family: monospace; color: #333; padding: 4px;")
            gl.addWidget(ext_lbl)
            # Tip
            tree_findings = sections.get("map.file_tree", ("", []))[1]
            if tree_findings:
                tip = QLabel(f"  {tree_findings[0].message}")
                tip.setStyleSheet("color: #666; font-size: 11px;")
                tip.setWordWrap(True)
                gl.addWidget(tip)
            self._content_layout.addWidget(group)

        # Entry points
        if report.entry_points:
            ep_findings = sections.get("map.entry_points", ("", []))[1]
            group = self._make_group(
                f"{_t('health_section_entry')} ({len(report.entry_points)})"
            )
            gl = group.layout()
            for ep in report.entry_points:
                row = QLabel(f"  \u25cf {ep['path']} — {ep['description']}")
                row.setStyleSheet("color: #333; padding: 2px;")
                gl.addWidget(row)
            if ep_findings:
                tip = QLabel(f"  {ep_findings[0].message}")
                tip.setStyleSheet("color: #666; font-size: 11px;")
                tip.setWordWrap(True)
                gl.addWidget(tip)
            self._content_layout.addWidget(group)

        # Module hubs / circular / orphans
        module_findings = sections.get("map.modules", ("", []))[1]
        if module_findings:
            group = self._make_group(_t("health_section_modules"))
            gl = group.layout()
            for f in module_findings:
                row = self._make_finding_row(f)
                gl.addWidget(row)
            self._content_layout.addWidget(group)

        # Monsters
        if report.monsters:
            group = self._make_group(_t("health_section_monsters"))
            gl = group.layout()
            for m in report.monsters:
                sev_icon = self._severity_icon(m["severity"])
                row = QLabel(
                    f"  {sev_icon} {m['path']} — {m['lines']} lines, "
                    f"{m['functions']} functions, {m['classes']} classes"
                )
                color = self._severity_color(m["severity"])
                row.setStyleSheet(f"color: {color}; font-weight: bold; padding: 2px;")
                gl.addWidget(row)
            # Tips for monsters
            monster_findings = sections.get("map.monsters", ("", []))[1]
            for f in monster_findings[:3]:
                tip = QLabel(f"  {f.message}")
                tip.setStyleSheet("color: #666; font-size: 11px;")
                tip.setWordWrap(True)
                gl.addWidget(tip)
            self._content_layout.addWidget(group)

        # Configs
        if report.configs:
            group = self._make_group(
                f"{_t('health_section_configs')} ({len(report.configs)})"
            )
            gl = group.layout()
            for c in report.configs:
                icon = "\u26a0\ufe0f" if c["severity"] == "warning" else "\u2139\ufe0f"
                row = QLabel(f"  {icon} {c['path']} — {c['description']}")
                row.setStyleSheet("color: #333; padding: 2px;")
                gl.addWidget(row)
            config_findings = sections.get("map.configs", ("", []))[1]
            for f in config_findings:
                tip = QLabel(f"  {f.message}")
                tip.setStyleSheet("color: #666; font-size: 11px;")
                tip.setWordWrap(True)
                gl.addWidget(tip)
            self._content_layout.addWidget(group)

        # System warnings
        sys_findings = sections.get("system", ("", []))[1]
        for f in sys_findings:
            row = self._make_finding_row(f)
            self._content_layout.addWidget(row)

        # Summary bar
        self._add_summary_bar(report)

        self._content_layout.addStretch()

    def _add_summary_bar(self, report: HealthReport) -> None:
        """Add severity summary at the bottom."""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in report.findings:
            if f.severity in counts:
                counts[f.severity] += 1

        parts = []
        icons = {
            "critical": "\U0001f480",
            "high": "\U0001f534",
            "medium": "\U0001f7e1",
            "low": "\U0001f535",
            "info": "\u2139\ufe0f",
        }
        for sev in ["critical", "high", "medium", "low", "info"]:
            if counts[sev] > 0:
                parts.append(f"{icons[sev]} {counts[sev]} {_t(f'health_severity_{sev}')}")

        if parts:
            summary = QLabel("  " + " | ".join(parts))
            summary.setStyleSheet(
                "background: #e0e0e0; border: 2px groove #808080; "
                "padding: 6px; font-weight: bold; margin-top: 8px;"
            )
            self._content_layout.addWidget(summary)

    def _make_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        group.setStyleSheet(
            "QGroupBox { border: 2px groove #808080; margin-top: 12px; "
            "padding-top: 16px; font-weight: bold; background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; "
            "padding: 0 4px; }"
        )
        layout = QVBoxLayout(group)
        layout.setSpacing(2)
        return group

    def _make_finding_row(self, finding: HealthFinding) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { border-bottom: 1px solid #e0e0e0; padding: 4px; }")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(1)

        color = self._severity_color(finding.severity)
        icon = self._severity_icon(finding.severity)

        title_lbl = QLabel(f"{icon} {finding.title}")
        title_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(title_lbl)

        msg_lbl = QLabel(f"  {finding.message}")
        msg_lbl.setStyleSheet("color: #666; font-size: 11px;")
        msg_lbl.setWordWrap(True)
        layout.addWidget(msg_lbl)

        return frame

    @staticmethod
    def _severity_color(severity: str) -> str:
        return {
            "critical": "#8b0000",
            "high": "#cc0000",
            "medium": "#cc6600",
            "low": "#000080",
            "info": "#333333",
            "warning": "#cc6600",
        }.get(severity, "#808080")

    @staticmethod
    def _severity_icon(severity: str) -> str:
        return {
            "critical": "\U0001f480",
            "high": "\U0001f534",
            "medium": "\U0001f7e1",
            "low": "\U0001f535",
            "info": "\u2139\ufe0f",
            "warning": "\u26a0\ufe0f",
        }.get(severity, "")

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
```

- [ ] **Step 2: Commit**

```bash
git add gui/pages/health_page.py
git commit -m "feat: add Dev Health GUI page with scan results rendering"
```

---

### Task 8: Wire into app.py

**Files:**
- Modify: `gui/app.py`

- [ ] **Step 1: Add import**

After `from gui.pages.activity import ActivityPage`, add:

```python
from gui.pages.health_page import HealthPage
```

- [ ] **Step 2: Add sidebar item**

After `SidebarItem(_t("side_activity"), "activity"),`:

```python
SidebarItem(_t("side_health"), "health"),
```

- [ ] **Step 3: Create page instance**

After `self.page_activity = ActivityPage()`:

```python
self.page_health = HealthPage()
```

- [ ] **Step 4: Register in stack**

In the `for key, page in [...]` list, after `("activity", self.page_activity),`:

```python
("health", self.page_health),
```

- [ ] **Step 5: Verify import works**

Run:
```bash
python -c "from gui.app import MonitorApp; print('Import OK')"
```

- [ ] **Step 6: Commit**

```bash
git add gui/app.py
git commit -m "feat: wire Dev Health page into sidebar"
```

---

### Task 9: Build Rust crate + full integration test

- [ ] **Step 1: Build Rust crate**

Run:
```bash
cd crates/health && ~/.cargo/bin/cargo test 2>&1
```
Expected: all Rust tests pass (18 tests)

- [ ] **Step 2: Build Python wheel**

Run:
```bash
cd crates/health && maturin develop 2>&1
```
Expected: wheel builds and installs

- [ ] **Step 3: Run all Python tests**

Run:
```bash
python -m pytest tests/test_health_models.py tests/test_health_project_map.py tests/test_activity_tracker.py tests/test_file_explainer.py tests/test_activity_models.py -v
```
Expected: all pass

- [ ] **Step 4: Verify full import chain**

Run:
```bash
python -c "
import health
print('Rust crate:', dir(health))
from core.health.project_map import run_all_checks
report = run_all_checks('.')
print(f'Findings: {len(report.findings)}')
for f in report.findings[:5]:
    print(f'  [{f.severity}] {f.check_id}: {f.title}')
"
```

- [ ] **Step 5: Commit plan doc**

```bash
git add docs/2026-04-15-health-checks-phase1-plan.md
git commit -m "docs: add Dev Health Phase 1 implementation plan"
```

---

## Summary

| Task | What | Language | Files |
|------|------|---------|-------|
| 1 | Crate scaffold + file_tree | Rust | `crates/health/` scaffold + `file_tree.rs` |
| 2 | Entry points | Rust | `entry_points.rs` |
| 3 | Monster files + tree-sitter | Rust | `monsters.rs` |
| 4 | Module map + import graph | Rust | `module_map.rs` |
| 5 | Python models + orchestrator | Python | `core/health/` |
| 6 | i18n strings | Python | `i18n/en.py`, `i18n/ua.py` |
| 7 | GUI page | Python | `gui/pages/health_page.py` |
| 8 | Wire into app | Python | `gui/app.py` |
| 9 | Integration test | Both | build + test all |

**Cross-platform:**
- Rust `ignore` crate: reads .gitignore cross-platform
- tree-sitter: pure Rust, compiles everywhere
- PyO3/maturin: builds wheels for Linux/Mac/Windows
- Python: pathlib + glob
- GUI: Qt native dialogs
