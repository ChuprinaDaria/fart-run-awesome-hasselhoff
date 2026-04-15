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
    pub kind: String,
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
    content: String,
    imports: Vec<(String, u32, String)>,
    definitions: Vec<(String, u32, String)>,
    used_identifiers: HashSet<String>,
    has_star_import: bool,
    is_init: bool,
}

#[derive(Clone, Copy, PartialEq)]
enum Lang {
    Python,
    JavaScript,
    TypeScript,
}

fn parse_file(content: &str, rel_path: &str, lang: Lang) -> FileData {
    let is_init = rel_path.ends_with("__init__.py");

    let mut parser = tree_sitter::Parser::new();
    let ts_lang = match lang {
        Lang::Python => tree_sitter_python::LANGUAGE.into(),
        Lang::JavaScript => tree_sitter_javascript::LANGUAGE.into(),
        Lang::TypeScript => tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
    };
    let empty = FileData {
        rel_path: rel_path.to_string(),
        lang,
        content: content.to_string(),
        imports: vec![],
        definitions: vec![],
        used_identifiers: HashSet::new(),
        has_star_import: false,
        is_init,
    };
    if parser.set_language(&ts_lang).is_err() {
        return empty;
    }
    let tree = match parser.parse(content, None) {
        Some(t) => t,
        None => return empty,
    };

    let mut imports: Vec<(String, u32, String)> = Vec::new();
    let mut definitions: Vec<(String, u32, String)> = Vec::new();
    let mut used_identifiers: HashSet<String> = HashSet::new();
    let mut import_lines: HashSet<u32> = HashSet::new();
    let mut def_lines: HashSet<u32> = HashSet::new();
    let mut has_star_import = false;
    let mut decorated_lines: HashSet<u32> = HashSet::new();

    let mut cursor = tree.walk();

    crate::common::walk_nodes(&mut cursor, &mut |node| {
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

                    for i in 0..node.child_count() {
                        if let Some(child) = node.child(i as u32) {
                            if child.kind() == "import_list" {
                                for j in 0..child.child_count() {
                                    if let Some(name_node) = child.child(j as u32) {
                                        if name_node.kind() == "dotted_name"
                                            || name_node.kind() == "aliased_import"
                                        {
                                            let name = if name_node.kind() == "aliased_import" {
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
                } else if node.kind() == "import_statement" {
                    let stmt_text = node
                        .utf8_text(content.as_bytes())
                        .unwrap_or("")
                        .to_string();
                    for i in 0..node.child_count() {
                        if let Some(child) = node.child(i as u32) {
                            if child.kind() == "dotted_name" || child.kind() == "aliased_import" {
                                let name = if child.kind() == "aliased_import" {
                                    child
                                        .child_by_field_name("alias")
                                        .and_then(|n| n.utf8_text(content.as_bytes()).ok())
                                        .unwrap_or("")
                                } else {
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
                    let end_line = node.end_position().row as u32 + 2;
                    decorated_lines.insert(end_line);
                }
            }
            Lang::JavaScript | Lang::TypeScript => {
                if node.kind() == "import_statement" {
                    let stmt_text = node
                        .utf8_text(content.as_bytes())
                        .unwrap_or("")
                        .to_string();
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
                // const X = require('Y')
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

        // Collect all identifiers for usage tracking
        if node.kind() == "identifier" || node.kind() == "property_identifier" {
            let node_line = node.start_position().row as u32 + 1;
            if !import_lines.contains(&node_line) && !def_lines.contains(&node_line) {
                if let Ok(text) = node.utf8_text(content.as_bytes()) {
                    used_identifiers.insert(text.to_string());
                }
            }
        }
    });

    // Filter out decorated definitions
    definitions.retain(|(_, line, _)| !decorated_lines.contains(line));

    // Filter out Python dunders and test functions
    if lang == Lang::Python {
        definitions.retain(|(name, _, kind)| {
            if kind == "function" {
                !name.starts_with("__") && !name.starts_with("test_")
            } else {
                !name.starts_with("Test")
            }
        });
    }

    FileData {
        rel_path: rel_path.to_string(),
        lang,
        content: content.to_string(),
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
    if node.kind() == "identifier" {
        if let Ok(text) = node.utf8_text(source.as_bytes()) {
            imports.push((text.to_string(), line, stmt.to_string()));
            import_lines.insert(line);
        }
        return;
    }

    for i in 0..node.child_count() {
        if let Some(child) = node.child(i as u32) {
            if child.kind() == "named_imports" {
                for j in 0..child.child_count() {
                    if let Some(spec) = child.child(j as u32) {
                        if spec.kind() == "import_specifier" {
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
                if let Ok(text) = child.utf8_text(source.as_bytes()) {
                    imports.push((text.to_string(), line, stmt.to_string()));
                    import_lines.insert(line);
                }
            } else if child.kind() == "namespace_import" {
                let last_idx = child.child_count().saturating_sub(1) as u32;
                if let Some(name_node) = child.child(last_idx) {
                    if name_node.kind() == "identifier" {
                        if let Ok(text) = name_node.utf8_text(source.as_bytes()) {
                            imports.push((text.to_string(), line, stmt.to_string()));
                            import_lines.insert(line);
                        }
                    }
                }
            } else {
                collect_js_import_names(child, source, imports, line, stmt, import_lines);
            }
        }
    }
}

/// Detect commented-out code blocks via regex.
fn find_commented_blocks(content: &str, rel_path: &str, lang: Lang) -> Vec<CommentedBlock> {
    use std::sync::LazyLock;
    static CODE_PATTERN: LazyLock<Regex> = LazyLock::new(|| {
        Regex::new(r"[=\(\)\{\}]|def |class |import |return |function |const |let |var |if |for ")
            .unwrap()
    });
    let code_pattern = &*CODE_PATTERN;

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

    let code_lines = current_block
        .iter()
        .filter(|(_, text)| code_pattern.is_match(text))
        .count();

    if code_lines * 100 / current_block.len() < 40 {
        return;
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

    // Phase 1: Parse all source files
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
            Ok(r) => crate::common::normalize_path(&r.to_string_lossy()),
            Err(_) => continue,
        };
        let content = match fs::read_to_string(entry_path) {
            Ok(c) => c,
            Err(_) => continue,
        };
        file_data.push(parse_file(&content, &rel_path, lang));
    }

    // Phase 2: Unused imports (per-file)
    let mut unused_imports: Vec<UnusedImport> = Vec::new();
    for fd in &file_data {
        if fd.has_star_import || fd.is_init {
            continue;
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

    // Phase 3: Unused definitions (cross-file)
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
            continue;
        }
        for (name, line, kind) in &fd.definitions {
            if global_identifiers.contains(name.as_str()) {
                continue;
            }
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

    // Phase 4: Orphan files
    let all_rel_paths: HashSet<String> = file_data.iter().map(|fd| fd.rel_path.clone()).collect();
    let mut imported_files: HashSet<String> = HashSet::new();
    for fd in &file_data {
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

    // Phase 5: Commented-out code (reuse stored content, no re-read)
    let mut commented_blocks: Vec<CommentedBlock> = Vec::new();
    for fd in &file_data {
        commented_blocks.extend(find_commented_blocks(&fd.content, &fd.rel_path, fd.lang));
    }

    Ok(DeadCodeResult {
        unused_imports,
        unused_definitions,
        orphan_files,
        commented_blocks,
    })
}
