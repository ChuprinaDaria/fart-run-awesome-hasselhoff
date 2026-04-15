# Dev Health Phase 2: Dead Code — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rust module `dead_code` that finds unused imports, unused functions/classes, orphan files, and commented-out code blocks via tree-sitter, integrated into existing health crate + GUI.

**Architecture:** Single new Rust module (`dead_code.rs`) added to `crates/health/`. Python orchestrator (`core/health/dead_code.py`) wraps Rust results into findings. GUI renders new "Dead Code" section in existing health page.

**Tech Stack:** Rust (tree-sitter, regex for commented code), Python, PyQt5

---

## File Structure

### New files

```
crates/health/src/dead_code.rs    # Rust: all 4 dead code checks in one pass
core/health/dead_code.py          # Python: orchestrator + tip generation
tests/test_health_dead_code.py    # Python integration tests
```

### Modified files

```
crates/health/src/lib.rs          # Register dead_code module
core/health/project_map.py        # Call dead code checks in run_all_checks()
core/health/tips.py               # Add dead code tips
core/health/models.py             # Add DeadCodeResult fields to HealthReport
gui/pages/health_page.py          # Render dead code section
i18n/en.py                        # ~8 new strings
i18n/ua.py                        # ~8 new strings
```

---

### Task 1: Rust dead_code module — unused imports

**Files:**
- Create: `crates/health/src/dead_code.rs`
- Modify: `crates/health/src/lib.rs`

- [ ] **Step 1: Create dead_code.rs with PyO3 structs and unused import detection**

```rust
//! Check 2.1–2.4 — Dead Code Detection.
//!
//! Single pass per file: tree-sitter parse → collect imports, definitions, identifiers.
//! Cross-file: check if definitions are used anywhere.
//! Regex: commented-out code blocks.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

use ignore::WalkBuilder;
use pyo3::prelude::*;
use regex::Regex;

use crate::common::{should_skip, SOURCE_EXTENSIONS};

#[pyclass]
#[derive(Clone)]
pub struct UnusedImport {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub line: u32,
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub import_statement: String,
}

#[pyclass]
#[derive(Clone)]
pub struct UnusedDefinition {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub line: u32,
    #[pyo3(get)]
    pub name: String,
    #[pyo3(get)]
    pub kind: String, // "function" or "class"
}

#[pyclass]
#[derive(Clone)]
pub struct CommentedBlock {
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub start_line: u32,
    #[pyo3(get)]
    pub end_line: u32,
    #[pyo3(get)]
    pub line_count: u32,
    #[pyo3(get)]
    pub preview: String,
}

#[pyclass]
#[derive(Clone)]
pub struct DeadCodeResult {
    #[pyo3(get)]
    pub unused_imports: Vec<UnusedImport>,
    #[pyo3(get)]
    pub unused_definitions: Vec<UnusedDefinition>,
    #[pyo3(get)]
    pub orphan_files: Vec<String>,
    #[pyo3(get)]
    pub commented_blocks: Vec<CommentedBlock>,
}

/// Per-file parsed data.
struct FileData {
    rel_path: String,
    lang: Lang,
    /// Imported names with their line numbers and full statement text.
    imports: Vec<(String, u32, String)>, // (name, line, statement)
    /// Defined function/class names with line numbers and kind.
    definitions: Vec<(String, u32, String)>, // (name, line, "function"/"class")
    /// All identifiers used in the file (excluding import/def lines themselves).
    used_identifiers: HashSet<String>,
    /// Whether the file has star imports (from X import *).
    has_star_import: bool,
    /// Whether this is an __init__.py file.
    is_init: bool,
}

#[derive(Clone, Copy, PartialEq)]
enum Lang {
    Python,
    JavaScript,
    TypeScript,
}

/// Walk tree-sitter nodes, calling f on each.
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

fn parse_file(content: &str, rel_path: &str, lang: Lang) -> FileData {
    let is_init = rel_path.ends_with("__init__.py");

    let mut parser = tree_sitter::Parser::new();
    let ts_lang = match lang {
        Lang::Python => tree_sitter_python::LANGUAGE.into(),
        Lang::JavaScript => tree_sitter_javascript::LANGUAGE.into(),
        Lang::TypeScript => tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
    };
    if parser.set_language(&ts_lang).is_err() {
        return FileData {
            rel_path: rel_path.to_string(),
            lang,
            imports: vec![],
            definitions: vec![],
            used_identifiers: HashSet::new(),
            has_star_import: false,
            is_init,
        };
    }

    let tree = match parser.parse(content, None) {
        Some(t) => t,
        None => {
            return FileData {
                rel_path: rel_path.to_string(),
                lang,
                imports: vec![],
                definitions: vec![],
                used_identifiers: HashSet::new(),
                has_star_import: false,
                is_init,
            };
        }
    };

    let mut imports: Vec<(String, u32, String)> = Vec::new();
    let mut definitions: Vec<(String, u32, String)> = Vec::new();
    let mut used_identifiers: HashSet<String> = HashSet::new();
    let mut import_lines: HashSet<u32> = HashSet::new();
    let mut def_lines: HashSet<u32> = HashSet::new();
    let mut has_star_import = false;
    let mut has_decorator_above: HashSet<u32> = HashSet::new(); // lines with decorators

    let mut cursor = tree.walk();

    // First pass: collect imports, definitions, decorators
    walk_nodes(&mut cursor, &mut |node| {
        let line = node.start_position().row as u32 + 1;

        match lang {
            Lang::Python => {
                if node.kind() == "import_from_statement" {
                    let stmt_text = node
                        .utf8_text(content.as_bytes())
                        .unwrap_or("")
                        .to_string();

                    if stmt_text.contains("import *") {
                        has_star_import = true;
                        return;
                    }

                    // from X import a, b, c
                    for i in 0..node.child_count() {
                        if let Some(child) = node.child(i as u32) {
                            if child.kind() == "import_list" || child.kind() == "dotted_name" {
                                // For import_list, get each name
                                if child.kind() == "import_list" {
                                    for j in 0..child.child_count() {
                                        if let Some(name_node) = child.child(j as u32) {
                                            if name_node.kind() == "dotted_name"
                                                || name_node.kind() == "aliased_import"
                                            {
                                                let name = if name_node.kind() == "aliased_import" {
                                                    // from X import Y as Z → track Z
                                                    name_node
                                                        .child_by_field_name("alias")
                                                        .and_then(|n| {
                                                            n.utf8_text(content.as_bytes()).ok()
                                                        })
                                                        .unwrap_or("")
                                                } else {
                                                    name_node
                                                        .utf8_text(content.as_bytes())
                                                        .unwrap_or("")
                                                };
                                                if !name.is_empty() {
                                                    imports.push((
                                                        name.to_string(),
                                                        line,
                                                        stmt_text.clone(),
                                                    ));
                                                    import_lines.insert(line);
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                } else if node.kind() == "import_statement" {
                    let stmt_text = node
                        .utf8_text(content.as_bytes())
                        .unwrap_or("")
                        .to_string();
                    // import X, import X as Y
                    for i in 0..node.child_count() {
                        if let Some(child) = node.child(i as u32) {
                            if child.kind() == "dotted_name" || child.kind() == "aliased_import" {
                                let name = if child.kind() == "aliased_import" {
                                    child
                                        .child_by_field_name("alias")
                                        .and_then(|n| n.utf8_text(content.as_bytes()).ok())
                                        .unwrap_or("")
                                } else {
                                    // import foo.bar → track "foo"
                                    let full = child.utf8_text(content.as_bytes()).unwrap_or("");
                                    full.split('.').next().unwrap_or("")
                                };
                                if !name.is_empty() {
                                    imports.push((name.to_string(), line, stmt_text.clone()));
                                    import_lines.insert(line);
                                }
                            }
                        }
                    }
                } else if node.kind() == "function_definition" {
                    if let Some(name_node) = node.child_by_field_name("name") {
                        let name = name_node
                            .utf8_text(content.as_bytes())
                            .unwrap_or("")
                            .to_string();
                        if !name.is_empty() {
                            definitions.push((name, line, "function".to_string()));
                            def_lines.insert(line);
                        }
                    }
                } else if node.kind() == "class_definition" {
                    if let Some(name_node) = node.child_by_field_name("name") {
                        let name = name_node
                            .utf8_text(content.as_bytes())
                            .unwrap_or("")
                            .to_string();
                        if !name.is_empty() {
                            definitions.push((name, line, "class".to_string()));
                            def_lines.insert(line);
                        }
                    }
                } else if node.kind() == "decorator" {
                    // Mark next line as decorated
                    let end_line = node.end_position().row as u32 + 2; // decorator end + 1
                    has_decorator_above.insert(end_line);
                }
            }
            Lang::JavaScript | Lang::TypeScript => {
                if node.kind() == "import_statement" {
                    let stmt_text = node
                        .utf8_text(content.as_bytes())
                        .unwrap_or("")
                        .to_string();
                    // import { X, Y } from 'Z' / import X from 'Z'
                    // Collect imported names from import_clause
                    for i in 0..node.child_count() {
                        if let Some(child) = node.child(i as u32) {
                            if child.kind() == "import_clause" {
                                collect_js_import_names(
                                    child,
                                    content,
                                    &mut imports,
                                    line,
                                    &stmt_text,
                                    &mut import_lines,
                                );
                            }
                        }
                    }
                } else if node.kind() == "function_declaration" {
                    if let Some(name_node) = node.child_by_field_name("name") {
                        let name = name_node
                            .utf8_text(content.as_bytes())
                            .unwrap_or("")
                            .to_string();
                        if !name.is_empty() {
                            definitions.push((name, line, "function".to_string()));
                            def_lines.insert(line);
                        }
                    }
                } else if node.kind() == "class_declaration" {
                    if let Some(name_node) = node.child_by_field_name("name") {
                        let name = name_node
                            .utf8_text(content.as_bytes())
                            .unwrap_or("")
                            .to_string();
                        if !name.is_empty() {
                            definitions.push((name, line, "class".to_string()));
                            def_lines.insert(line);
                        }
                    }
                }
                // JS variable declarations with require: const X = require('Y')
                if node.kind() == "variable_declarator" {
                    if let Some(init) = node.child_by_field_name("value") {
                        if init.kind() == "call_expression" {
                            let func_text = init
                                .child_by_field_name("function")
                                .and_then(|n| n.utf8_text(content.as_bytes()).ok())
                                .unwrap_or("");
                            if func_text == "require" {
                                if let Some(name_node) = node.child_by_field_name("name") {
                                    let name = name_node
                                        .utf8_text(content.as_bytes())
                                        .unwrap_or("")
                                        .to_string();
                                    let stmt_text = node
                                        .parent()
                                        .and_then(|p| p.utf8_text(content.as_bytes()).ok())
                                        .unwrap_or("")
                                        .to_string();
                                    if !name.is_empty() {
                                        imports.push((name, line, stmt_text));
                                        import_lines.insert(line);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Collect all identifiers (for usage tracking)
        if node.kind() == "identifier" || node.kind() == "property_identifier" {
            let node_line = node.start_position().row as u32 + 1;
            // Skip identifiers on import/definition lines
            if !import_lines.contains(&node_line) && !def_lines.contains(&node_line) {
                if let Ok(text) = node.utf8_text(content.as_bytes()) {
                    used_identifiers.insert(text.to_string());
                }
            }
        }
    });

    // Filter out decorated definitions (they're likely registered by framework)
    definitions.retain(|(_, line, _)| !has_decorator_above.contains(line));

    // Filter out Python dunder methods and test functions
    if lang == Lang::Python {
        definitions.retain(|(name, _, kind)| {
            if kind == "function" {
                // Keep if not dunder and not test_
                !name.starts_with("__") && !name.starts_with("test_")
            } else {
                // Keep class if not Test*
                !name.starts_with("Test")
            }
        });
    }

    FileData {
        rel_path: rel_path.to_string(),
        lang,
        imports,
        definitions,
        used_identifiers,
        has_star_import,
        is_init,
    }
}

fn collect_js_import_names(
    node: tree_sitter::Node,
    source: &str,
    imports: &mut Vec<(String, u32, String)>,
    line: u32,
    stmt: &str,
    import_lines: &mut HashSet<u32>,
) {
    // Default import: import X from 'Y'
    if node.kind() == "identifier" {
        if let Ok(text) = node.utf8_text(source.as_bytes()) {
            imports.push((text.to_string(), line, stmt.to_string()));
            import_lines.insert(line);
        }
        return;
    }

    // Named imports: import { X, Y } from 'Z'
    for i in 0..node.child_count() {
        if let Some(child) = node.child(i as u32) {
            if child.kind() == "named_imports" {
                for j in 0..child.child_count() {
                    if let Some(spec) = child.child(j as u32) {
                        if spec.kind() == "import_specifier" {
                            // Could be aliased: import { X as Y }
                            let name = spec
                                .child_by_field_name("alias")
                                .or_else(|| spec.child_by_field_name("name"))
                                .and_then(|n| n.utf8_text(source.as_bytes()).ok())
                                .unwrap_or("");
                            if !name.is_empty() {
                                imports.push((name.to_string(), line, stmt.to_string()));
                                import_lines.insert(line);
                            }
                        }
                    }
                }
            } else if child.kind() == "identifier" {
                // Default import
                if let Ok(text) = child.utf8_text(source.as_bytes()) {
                    imports.push((text.to_string(), line, stmt.to_string()));
                    import_lines.insert(line);
                }
            } else if child.kind() == "namespace_import" {
                // import * as X from 'Y'
                if let Some(name_node) = child.child(child.child_count().saturating_sub(1) as u32) {
                    if name_node.kind() == "identifier" {
                        if let Ok(text) = name_node.utf8_text(source.as_bytes()) {
                            imports.push((text.to_string(), line, stmt.to_string()));
                            import_lines.insert(line);
                        }
                    }
                }
            } else {
                // Recurse
                collect_js_import_names(child, source, imports, line, stmt, import_lines);
            }
        }
    }
}

/// Detect commented-out code blocks via regex.
fn find_commented_blocks(content: &str, rel_path: &str, lang: Lang) -> Vec<CommentedBlock> {
    let code_pattern =
        Regex::new(r"[=\(\)\{\}]|def |class |import |return |function |const |let |var |if |for ")
            .unwrap();

    let comment_prefix = match lang {
        Lang::Python => "#",
        Lang::JavaScript | Lang::TypeScript => "//",
    };

    let mut blocks: Vec<CommentedBlock> = Vec::new();
    let mut current_block: Vec<(u32, String)> = Vec::new();

    for (idx, line) in content.lines().enumerate() {
        let trimmed = line.trim();
        let line_num = idx as u32 + 1;

        let is_comment = trimmed.starts_with(comment_prefix) && !trimmed.starts_with("#!");
        // For Python, skip shebangs and encoding declarations
        if lang == Lang::Python && (trimmed.starts_with("#!") || trimmed.starts_with("# -*-")) {
            if !current_block.is_empty() {
                maybe_emit_block(&mut blocks, &current_block, rel_path, &code_pattern);
                current_block.clear();
            }
            continue;
        }

        if is_comment {
            current_block.push((line_num, trimmed.to_string()));
        } else {
            if !current_block.is_empty() {
                maybe_emit_block(&mut blocks, &current_block, rel_path, &code_pattern);
                current_block.clear();
            }
        }
    }

    // Handle trailing block
    if !current_block.is_empty() {
        maybe_emit_block(&mut blocks, &current_block, rel_path, &code_pattern);
    }

    blocks
}

fn maybe_emit_block(
    blocks: &mut Vec<CommentedBlock>,
    current_block: &[(u32, String)],
    rel_path: &str,
    code_pattern: &Regex,
) {
    if current_block.len() < 5 {
        return;
    }

    // Check if at least 40% of lines look like code
    let code_lines = current_block
        .iter()
        .filter(|(_, text)| code_pattern.is_match(text))
        .count();

    if code_lines * 100 / current_block.len() < 40 {
        return; // Probably a real comment block, not commented-out code
    }

    let start = current_block[0].0;
    let end = current_block.last().unwrap().0;
    let preview: String = current_block
        .iter()
        .take(3)
        .map(|(_, text)| text.as_str())
        .collect::<Vec<_>>()
        .join("\n");

    blocks.push(CommentedBlock {
        path: rel_path.to_string(),
        start_line: start,
        end_line: end,
        line_count: current_block.len() as u32,
        preview,
    });
}

#[pyfunction]
pub fn scan_dead_code(path: &str, entry_point_paths: Vec<String>) -> PyResult<DeadCodeResult> {
    let root = Path::new(path);
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Not a directory: {}", path),
        ));
    }

    // Phase 1: Collect all source files and parse them
    let mut file_data: Vec<FileData> = Vec::new();

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
        let lang = match ext {
            "py" => Lang::Python,
            "ts" | "tsx" | "mts" | "cts" => Lang::TypeScript,
            _ => Lang::JavaScript,
        };
        let rel_path = match entry_path.strip_prefix(root) {
            Ok(r) => r.to_string_lossy().to_string(),
            Err(_) => continue,
        };
        let content = match fs::read_to_string(entry_path) {
            Ok(c) => c,
            Err(_) => continue,
        };

        file_data.push(parse_file(&content, &rel_path, lang));
    }

    // Phase 2: Check unused imports (per-file)
    let mut unused_imports: Vec<UnusedImport> = Vec::new();
    for fd in &file_data {
        if fd.has_star_import || fd.is_init {
            continue; // Can't reliably check these
        }
        for (name, line, stmt) in &fd.imports {
            if !fd.used_identifiers.contains(name.as_str()) {
                unused_imports.push(UnusedImport {
                    path: fd.rel_path.clone(),
                    line: *line,
                    name: name.clone(),
                    import_statement: stmt.clone(),
                });
            }
        }
    }

    // Phase 3: Check unused definitions (cross-file)
    // Build global set of all identifiers used across all files
    let mut global_identifiers: HashSet<String> = HashSet::new();
    for fd in &file_data {
        for id in &fd.used_identifiers {
            global_identifiers.insert(id.clone());
        }
    }

    let entry_set: HashSet<&str> = entry_point_paths.iter().map(|s| s.as_str()).collect();

    let mut unused_definitions: Vec<UnusedDefinition> = Vec::new();
    for fd in &file_data {
        if fd.is_init {
            continue; // __init__.py definitions are re-exports
        }
        for (name, line, kind) in &fd.definitions {
            // Skip if used anywhere globally
            if global_identifiers.contains(name.as_str()) {
                continue;
            }
            // Skip names starting with _ (private convention) in same file
            if name.starts_with('_') {
                continue;
            }
            unused_definitions.push(UnusedDefinition {
                path: fd.rel_path.clone(),
                line: *line,
                name: name.clone(),
                kind: kind.clone(),
            });
        }
    }

    // Phase 4: Orphan files (files not imported by anyone and not entry points)
    // Reuse module_map logic inline — collect all local imports
    let mut imported_files: HashSet<String> = HashSet::new();
    // Simple approach: if a file's stem appears in any import statement, it's used
    let all_rel_paths: HashSet<String> = file_data.iter().map(|fd| fd.rel_path.clone()).collect();

    for fd in &file_data {
        for (name, _, _) in &fd.imports {
            // Try to match import name to a file
            // Python: "from .utils import X" → name might be just the imported symbol
            // But we stored module names in module_map, here we have symbol names
            // Simpler: check if any file stem matches
        }
        // Also check used_identifiers that match file stems
        for id in &fd.used_identifiers {
            for rel in &all_rel_paths {
                let stem = Path::new(rel)
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("");
                if stem == id.as_str() {
                    imported_files.insert(rel.clone());
                }
            }
        }
    }

    let orphan_files: Vec<String> = all_rel_paths
        .iter()
        .filter(|f| {
            !imported_files.contains(*f)
                && !entry_set.contains(f.as_str())
                && !f.ends_with("__init__.py")
                && !f.ends_with("conftest.py")
                && !f.contains("/test")
                && !f.starts_with("test")
                && !f.ends_with("setup.py")
        })
        .cloned()
        .collect();

    // Phase 5: Commented-out code blocks
    let mut commented_blocks: Vec<CommentedBlock> = Vec::new();
    for entry in WalkBuilder::new(root)
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
        .build()
        .flatten()
    {
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
        let lang = match ext {
            "py" => Lang::Python,
            "ts" | "tsx" | "mts" | "cts" => Lang::TypeScript,
            _ => Lang::JavaScript,
        };
        let rel_path = match entry_path.strip_prefix(root) {
            Ok(r) => r.to_string_lossy().to_string(),
            Err(_) => continue,
        };
        let content = match fs::read_to_string(entry_path) {
            Ok(c) => c,
            Err(_) => continue,
        };
        commented_blocks.extend(find_commented_blocks(&content, &rel_path, lang));
    }

    Ok(DeadCodeResult {
        unused_imports,
        unused_definitions,
        orphan_files,
        commented_blocks,
    })
}
```

- [ ] **Step 2: Add `regex` dependency to Cargo.toml if not present**

Check `crates/health/Cargo.toml` — if `regex` is not listed, add:
```toml
regex = "1"
```

- [ ] **Step 3: Update lib.rs — register dead_code module**

```rust
//! health — project health scanner for vibe coders.

mod common;
mod dead_code;
mod entry_points;
mod file_tree;
mod module_map;
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

    m.add_class::<module_map::ModuleInfo>()?;
    m.add_class::<module_map::ModuleMapResult>()?;
    m.add_function(wrap_pyfunction!(module_map::scan_module_map, m)?)?;

    m.add_class::<dead_code::UnusedImport>()?;
    m.add_class::<dead_code::UnusedDefinition>()?;
    m.add_class::<dead_code::CommentedBlock>()?;
    m.add_class::<dead_code::DeadCodeResult>()?;
    m.add_function(wrap_pyfunction!(dead_code::scan_dead_code, m)?)?;

    Ok(())
}
```

- [ ] **Step 4: Build and verify**

Run:
```bash
cd crates/health && PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH" maturin build --release 2>&1 | tail -5
```
Expected: builds successfully

```bash
python3 -m pip install --user --break-system-packages --force-reinstall target/wheels/health-*.whl
python3 -c "import health; print(dir(health))"
```
Expected: shows `scan_dead_code`, `DeadCodeResult`, etc.

- [ ] **Step 5: Quick smoke test**

```bash
python3 -c "
import health
r = health.scan_dead_code('.', ['gui/app.py', 'core/parser.py'])
print(f'Unused imports: {len(r.unused_imports)}')
print(f'Unused defs: {len(r.unused_definitions)}')
print(f'Orphan files: {len(r.orphan_files)}')
print(f'Commented blocks: {len(r.commented_blocks)}')
for ui in r.unused_imports[:3]:
    print(f'  {ui.path}:{ui.line} — {ui.name}')
"
```

- [ ] **Step 6: Commit**

```bash
git add crates/health/src/dead_code.rs crates/health/src/lib.rs crates/health/Cargo.toml crates/health/Cargo.lock
git commit -m "feat: add dead_code module — unused imports/defs, orphans, commented code (Rust)"
```

---

### Task 2: Python orchestrator + tips

**Files:**
- Create: `core/health/dead_code.py`
- Modify: `core/health/tips.py`
- Modify: `core/health/models.py`
- Modify: `core/health/project_map.py`

- [ ] **Step 1: Add dead code tips to tips.py**

Append to `core/health/tips.py`:

```python
def tip_unused_import(name: str, path: str, line: int) -> str:
    return (
        f"{name} imported in {path}:{line} but never used. "
        f"Unused import — like buying groceries and leaving them in the trunk. "
        f"Remove it, nothing will break."
    )


def tip_unused_function(name: str, path: str) -> str:
    return (
        f"{name}() in {path} — defined but never called anywhere in the project. "
        f"Dead code. Delete or use it."
    )


def tip_unused_class(name: str, path: str) -> str:
    return (
        f"class {name} in {path} — exists but nobody uses it. Dead weight. "
        f"Delete or use it."
    )


def tip_commented_code(path: str, start: int, count: int) -> str:
    return (
        f"{count} lines of commented-out code in {path}:{start}. "
        f"That's not backup — git is your backup. Delete it."
    )
```

- [ ] **Step 2: Add dead_code fields to HealthReport in models.py**

Add to `HealthReport` dataclass:

```python
    unused_imports: list[dict] = field(default_factory=list)
    unused_definitions: list[dict] = field(default_factory=list)
    commented_blocks: list[dict] = field(default_factory=list)
```

- [ ] **Step 3: Create dead_code.py orchestrator**

```python
# core/health/dead_code.py
"""Dead code check orchestrator — wraps Rust scan_dead_code into findings."""

from __future__ import annotations

import logging

from core.health.models import HealthFinding, HealthReport
from core.health import tips

log = logging.getLogger(__name__)


def run_dead_code_checks(
    report: HealthReport,
    health_rs,
    project_dir: str,
    entry_point_paths: list[str],
) -> None:
    """Run dead code checks and append findings to report."""
    try:
        result = health_rs.scan_dead_code(project_dir, entry_point_paths)
    except Exception as e:
        log.error("dead_code scan error: %s", e)
        return

    # Unused imports
    report.unused_imports = [
        {"path": ui.path, "line": ui.line, "name": ui.name, "statement": ui.import_statement}
        for ui in result.unused_imports
    ]
    for ui in result.unused_imports[:20]:  # cap at 20 findings
        report.findings.append(HealthFinding(
            check_id="dead.unused_imports",
            title=f"Unused: {ui.name}",
            severity="medium",
            message=tips.tip_unused_import(ui.name, ui.path, ui.line),
        ))

    # Unused definitions
    report.unused_definitions = [
        {"path": ud.path, "line": ud.line, "name": ud.name, "kind": ud.kind}
        for ud in result.unused_definitions
    ]
    for ud in result.unused_definitions[:20]:
        tip_fn = tips.tip_unused_class if ud.kind == "class" else tips.tip_unused_function
        report.findings.append(HealthFinding(
            check_id="dead.unused_definitions",
            title=f"Unused {ud.kind}: {ud.name}",
            severity="medium",
            message=tip_fn(ud.name, ud.path),
        ))

    # Orphan files (reuse from Rust result)
    for orphan in result.orphan_files[:10]:
        report.findings.append(HealthFinding(
            check_id="dead.orphan_files",
            title=f"Orphan: {orphan}",
            severity="low",
            message=tips.tip_orphan(orphan),
        ))

    # Commented-out code
    report.commented_blocks = [
        {
            "path": cb.path,
            "start_line": cb.start_line,
            "end_line": cb.end_line,
            "line_count": cb.line_count,
            "preview": cb.preview,
        }
        for cb in result.commented_blocks
    ]
    for cb in result.commented_blocks[:10]:
        report.findings.append(HealthFinding(
            check_id="dead.commented_code",
            title=f"Commented code: {cb.path}:{cb.start_line}",
            severity="low",
            message=tips.tip_commented_code(cb.path, cb.start_line, cb.line_count),
        ))
```

- [ ] **Step 4: Integrate into run_all_checks in project_map.py**

After the monsters check block (after `except Exception as e: log.error("monsters scan error: %s", e)`), add:

```python
        # Phase 2: Dead Code
        try:
            from core.health.dead_code import run_dead_code_checks
            entry_paths = [ep["path"] for ep in report.entry_points]
            run_dead_code_checks(report, health_rs, project_dir, entry_paths)
        except Exception as e:
            log.error("dead_code scan error: %s", e)
```

- [ ] **Step 5: Commit**

```bash
git add core/health/dead_code.py core/health/tips.py core/health/models.py core/health/project_map.py
git commit -m "feat: add dead code Python orchestrator + tips + integrate into run_all_checks"
```

---

### Task 3: i18n + GUI rendering

**Files:**
- Modify: `i18n/en.py`
- Modify: `i18n/ua.py`
- Modify: `gui/pages/health_page.py`

- [ ] **Step 1: Add English strings**

Add to `i18n/en.py` before closing `}`:

```python
    # Dead Code
    "health_section_unused_imports": "Unused Imports",
    "health_section_unused_defs": "Unused Functions/Classes",
    "health_section_orphans": "Orphan Files",
    "health_section_commented": "Commented-Out Code",
    "health_dead_code_header": "Dead Code",
    "health_dead_total": "{} unused imports, {} unused definitions, {} commented blocks",
```

- [ ] **Step 2: Add Ukrainian strings**

Add to `i18n/ua.py` before closing `}`:

```python
    # Dead Code
    "health_section_unused_imports": "Невикористані імпорти",
    "health_section_unused_defs": "Невикористані функції/класи",
    "health_section_orphans": "Файли-сироти",
    "health_section_commented": "Закоментований код",
    "health_dead_code_header": "Мертвий код",
    "health_dead_total": "{} невикористаних імпортів, {} невикористаних визначень, {} блоків коментарів",
```

- [ ] **Step 3: Add dead code sections to health_page.py**

In `_render_report()`, add to the `sections` dict:

```python
            "dead.unused_imports": (_t("health_section_unused_imports"), []),
            "dead.unused_definitions": (_t("health_section_unused_defs"), []),
            "dead.orphan_files": (_t("health_section_orphans"), []),
            "dead.commented_code": (_t("health_section_commented"), []),
```

After the configs rendering block (before system warnings), add:

```python
        # Dead Code sections
        for dead_key in ["dead.unused_imports", "dead.unused_definitions", "dead.orphan_files", "dead.commented_code"]:
            dead_findings = sections.get(dead_key, ("", []))[1]
            if dead_findings:
                section_title = sections[dead_key][0]
                group = self._make_group(f"{section_title} ({len(dead_findings)})")
                gl = group.layout()
                for f in dead_findings[:15]:  # cap display at 15 per section
                    row = self._make_finding_row(f)
                    gl.addWidget(row)
                if len(dead_findings) > 15:
                    more = QLabel(f"  ... and {len(dead_findings) - 15} more")
                    more.setStyleSheet("color: #808080; font-style: italic;")
                    gl.addWidget(more)
                self._content_layout.addWidget(group)
```

- [ ] **Step 4: Commit**

```bash
git add i18n/en.py i18n/ua.py gui/pages/health_page.py
git commit -m "feat: add dead code i18n strings + GUI rendering"
```

---

### Task 4: Tests + integration

**Files:**
- Create: `tests/test_health_dead_code.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_health_dead_code.py
"""Tests for dead code detection."""

from core.health.project_map import run_all_checks


def test_unused_import_detected(tmp_path):
    """Python file with unused import should be flagged."""
    (tmp_path / "app.py").write_text(
        "import os\nimport sys\n\nprint(sys.argv)\n"
    )
    report = run_all_checks(str(tmp_path))
    unused = [f for f in report.findings if f.check_id == "dead.unused_imports"]
    names = [f.title for f in unused]
    assert any("os" in n for n in names), f"Expected unused 'os', got: {names}"


def test_used_import_not_flagged(tmp_path):
    """Used import should NOT be flagged."""
    (tmp_path / "app.py").write_text(
        "import os\n\nprint(os.getcwd())\n"
    )
    report = run_all_checks(str(tmp_path))
    unused = [f for f in report.findings if f.check_id == "dead.unused_imports"]
    names = [f.title for f in unused]
    assert not any("os" in n for n in names), f"os should not be flagged: {names}"


def test_unused_function_detected(tmp_path):
    """Function defined but never called should be flagged."""
    (tmp_path / "utils.py").write_text(
        "def helper():\n    pass\n\ndef unused_func():\n    pass\n"
    )
    (tmp_path / "main.py").write_text(
        "from utils import helper\nhelper()\n"
    )
    report = run_all_checks(str(tmp_path))
    unused_defs = [f for f in report.findings if f.check_id == "dead.unused_definitions"]
    names = [f.title for f in unused_defs]
    assert any("unused_func" in n for n in names), f"Expected unused_func, got: {names}"


def test_decorated_function_not_flagged(tmp_path):
    """Decorated functions should NOT be flagged (framework registration)."""
    (tmp_path / "routes.py").write_text(
        "from flask import Flask\napp = Flask(__name__)\n\n"
        "@app.route('/')\ndef index():\n    return 'hi'\n"
    )
    report = run_all_checks(str(tmp_path))
    unused_defs = [f for f in report.findings if f.check_id == "dead.unused_definitions"]
    names = [f.title for f in unused_defs]
    assert not any("index" in n for n in names), f"Decorated index should not be flagged: {names}"


def test_commented_code_detected(tmp_path):
    """Block of commented-out code should be flagged."""
    lines = [
        "x = 1",
        "# def old_function():",
        "#     x = 1",
        "#     y = 2",
        "#     return x + y",
        "#     if x > 0:",
        "#         print(x)",
        "y = 2",
    ]
    (tmp_path / "app.py").write_text("\n".join(lines))
    report = run_all_checks(str(tmp_path))
    commented = [f for f in report.findings if f.check_id == "dead.commented_code"]
    assert len(commented) >= 1, f"Expected commented code block, got: {commented}"


def test_small_comment_not_flagged(tmp_path):
    """Less than 5 comment lines should NOT be flagged."""
    (tmp_path / "app.py").write_text(
        "# This is a comment\n# Another comment\n# Third one\nx = 1\n"
    )
    report = run_all_checks(str(tmp_path))
    commented = [f for f in report.findings if f.check_id == "dead.commented_code"]
    assert len(commented) == 0


def test_init_py_skipped(tmp_path):
    """__init__.py definitions should not be flagged as unused."""
    pkg = tmp_path / "mypackage"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("def public_api():\n    pass\n")
    report = run_all_checks(str(tmp_path))
    unused_defs = [f for f in report.findings if f.check_id == "dead.unused_definitions"]
    names = [f.title for f in unused_defs]
    assert not any("public_api" in n for n in names)


def test_star_import_file_skipped(tmp_path):
    """Files with star imports should be skipped for unused import check."""
    (tmp_path / "app.py").write_text(
        "from os.path import *\nimport json\n\nprint(join('a', 'b'))\n"
    )
    report = run_all_checks(str(tmp_path))
    unused = [f for f in report.findings if f.check_id == "dead.unused_imports"]
    # json might be flagged but the star import file should be skipped entirely
    # Actually: star import sets has_star_import, skipping the whole file
    assert not any("json" in f.title for f in unused)
```

- [ ] **Step 2: Run tests**

Run:
```bash
python -m pytest tests/test_health_dead_code.py -v
```
Expected: all pass

- [ ] **Step 3: Run full test suite**

Run:
```bash
python -m pytest tests/test_health_models.py tests/test_health_project_map.py tests/test_health_dead_code.py tests/test_activity_tracker.py tests/test_file_explainer.py tests/test_activity_models.py tests/test_history.py tests/test_config.py tests/test_platform.py -v
```
Expected: all pass (85+ tests)

- [ ] **Step 4: Full integration smoke test**

Run:
```bash
python3 -c "
from core.health.project_map import run_all_checks
report = run_all_checks('/home/dchuprina/claude-monitor')
print(f'Total findings: {len(report.findings)}')
for f in report.findings:
    print(f'  [{f.severity:8s}] {f.check_id}: {f.title}')
"
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_health_dead_code.py
git commit -m "test: add dead code detection tests"
```

---

## Summary

| Task | What | Language | Files |
|------|------|---------|-------|
| 1 | dead_code.rs — Rust scanner | Rust | `crates/health/src/dead_code.rs`, `lib.rs` |
| 2 | Python orchestrator + tips | Python | `core/health/dead_code.py`, `tips.py`, `models.py`, `project_map.py` |
| 3 | i18n + GUI rendering | Python | `i18n/en.py`, `i18n/ua.py`, `gui/pages/health_page.py` |
| 4 | Tests + integration | Python | `tests/test_health_dead_code.py` |
