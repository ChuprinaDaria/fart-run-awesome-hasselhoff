//! Check 2.1–2.4 — Dead Code Detection.
//!
//! Single pass per file: tree-sitter parse → collect imports, definitions, identifiers.
//! Cross-file: check if definitions are used anywhere.
//! Commented-out code detection re-parses stripped comment blocks.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

use ignore::WalkBuilder;
use pyo3::prelude::*;

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

/// Names that pytest (and unittest-via-pytest) call automatically in any
/// class or module under a test scope. They look like dead code because
/// nothing in the source calls them directly — the test runner does.
const PYTEST_LIFECYCLE_NAMES: &[&str] = &[
    // pytest xunit-style functions and methods
    "setup_function",
    "teardown_function",
    "setup_method",
    "teardown_method",
    "setup_class",
    "teardown_class",
    "setup_module",
    "teardown_module",
    // unittest-style names that pytest also honors
    "setUp",
    "tearDown",
    "setUpClass",
    "tearDownClass",
    "setUpModule",
    "tearDownModule",
    "asyncSetUp",
    "asyncTearDown",
];

/// Return true if this file lives in a scope where pytest will pick up
/// lifecycle hooks automatically: anything under `tests/`, any
/// `test_*.py` / `*_test.py`, or a `conftest.py`.
fn is_pytest_scope(rel_path: &str) -> bool {
    let path = rel_path.replace('\\', "/");
    if path.starts_with("tests/") || path.contains("/tests/") {
        return true;
    }
    let file_name = path.rsplit('/').next().unwrap_or(&path);
    if file_name == "conftest.py" {
        return true;
    }
    if file_name.starts_with("test_") && file_name.ends_with(".py") {
        return true;
    }
    if file_name.ends_with("_test.py") {
        return true;
    }
    false
}

/// Check whether the given source line carries a `# noqa` marker that
/// silences unused-import warnings for this line.
///
/// Rules (mirroring pyflakes/flake8/ruff conventions):
/// - `# noqa` (no code) — silences everything, including F401.
/// - `# noqa: F401` — silences F401 (unused import).
/// - `# noqa: F401, F811` — comma-separated list; matches if F401 is in it.
/// - `# noqa: E501` — does NOT silence F401 (wrong code).
/// - Case-insensitive. JS equivalent handled via explicit check below.
fn has_noqa_unused_import(line_text: &str, lang: Lang) -> bool {
    let lower = line_text.to_ascii_lowercase();
    match lang {
        Lang::Python => {
            let Some(idx) = lower.find("# noqa") else {
                return false;
            };
            let rest = &lower[idx + "# noqa".len()..];
            let trimmed = rest.trim_start();
            if !trimmed.starts_with(':') {
                // Bare `# noqa` — silences everything.
                return true;
            }
            // `# noqa: <codes>` — look for f401 in the comma list.
            let codes_part = &trimmed[1..]; // skip ':'
            codes_part
                .split(|c: char| c == ',' || c.is_whitespace())
                .any(|tok| tok.trim() == "f401")
        }
        Lang::JavaScript | Lang::TypeScript => {
            // `// eslint-disable-line no-unused-vars` (or next-line, or bare disable-line)
            lower.contains("eslint-disable-line")
                || lower.contains("eslint-disable-next-line")
        }
    }
}

/// Return true if this identifier is the name being declared (function,
/// class, method) or lives inside an import statement's name list.
/// False for every usage site, including type hints and decorator targets.
fn is_decl_or_import_name(node: tree_sitter::Node) -> bool {
    // Case 1: direct parent is a declaration node and this identifier
    // is its `name` field.
    if let Some(parent) = node.parent() {
        match parent.kind() {
            "function_definition"
            | "class_definition"
            | "function_declaration"
            | "class_declaration"
            | "method_definition" => {
                if parent.child_by_field_name("name").map(|n| n.id()) == Some(node.id()) {
                    return true;
                }
            }
            _ => {}
        }
    }

    // Case 2: identifier lives anywhere inside an import statement's
    // name list. Walk up until we hit an import statement (true) or a
    // non-import statement/block boundary (false).
    let mut cur = node.parent();
    while let Some(p) = cur {
        match p.kind() {
            "import_statement" | "import_from_statement" => return true,
            // Statement/block boundaries — once we cross one of these,
            // we're out of the import's scope.
            "function_definition"
            | "class_definition"
            | "function_declaration"
            | "class_declaration"
            | "method_definition"
            | "if_statement"
            | "for_statement"
            | "while_statement"
            | "try_statement"
            | "with_statement"
            | "expression_statement"
            | "assignment"
            | "augmented_assignment"
            | "return_statement"
            | "decorator"
            | "call"
            | "block"
            | "module"
            | "program" => return false,
            _ => cur = p.parent(),
        }
    }
    false
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
    // NB: import_lines/def_lines are maintained for now but no longer
    // consulted by the usage-tracking logic (Task 12 — it used to exclude
    // identifiers on import/def lines, which killed type-hint references
    // like `aiosqlite.Connection` in `def f(db: aiosqlite.Connection)`).
    // Left in place in case future checks need per-line import/def maps.
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

                    // Imported names are siblings of `module_name` (and sit
                    // inside `import_list` only when parentheses are used).
                    // Walk every direct child and collect dotted_name /
                    // aliased_import nodes, skipping the one that is the
                    // `module_name` field.
                    let module_name_id = node.child_by_field_name("module_name").map(|n| n.id());
                    for i in 0..node.child_count() {
                        if let Some(child) = node.child(i as u32) {
                            match child.kind() {
                                "dotted_name" | "aliased_import" => {
                                    if module_name_id == Some(child.id()) {
                                        continue;
                                    }
                                    let name = if child.kind() == "aliased_import" {
                                        child
                                            .child_by_field_name("alias")
                                            .and_then(|n| n.utf8_text(content.as_bytes()).ok())
                                            .unwrap_or("")
                                    } else {
                                        child.utf8_text(content.as_bytes()).unwrap_or("")
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
                                // Parenthesized form: `from X import (Y, Z)`
                                // — names live inside an import_list child.
                                "import_list" => {
                                    for j in 0..child.child_count() {
                                        if let Some(name_node) = child.child(j as u32) {
                                            if name_node.kind() == "dotted_name"
                                                || name_node.kind() == "aliased_import"
                                            {
                                                let name = if name_node.kind() == "aliased_import"
                                                {
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
                                _ => {}
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

        // Collect all identifiers for usage tracking — but skip the
        // identifier that is itself the declared name (function/class)
        // or an imported name. Type hints on the same line as `def`
        // must still count as usages (Task 12).
        if node.kind() == "identifier" || node.kind() == "property_identifier" {
            if !is_decl_or_import_name(node) {
                if let Ok(text) = node.utf8_text(content.as_bytes()) {
                    used_identifiers.insert(text.to_string());
                }
            }
        }
    });

    // Filter out decorated definitions
    definitions.retain(|(_, line, _)| !decorated_lines.contains(line));

    // Filter out Python dunders and test functions. If the file is a
    // test-scope file (tests/**, test_*.py, *_test.py, conftest.py),
    // also drop pytest / unittest lifecycle hooks that pytest invokes
    // automatically — they look dead but are not.
    if lang == Lang::Python {
        let is_test_file = is_pytest_scope(rel_path);
        definitions.retain(|(name, _, kind)| {
            if kind == "function" {
                if name.starts_with("__") || name.starts_with("test_") {
                    return false;
                }
                if is_test_file && PYTEST_LIFECYCLE_NAMES.contains(&name.as_str()) {
                    return false;
                }
                true
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

/// Detect commented-out code blocks.
///
/// Strategy (Task 13): identify contiguous comment blocks of ≥5 lines,
/// strip the comment prefix, and feed the result to tree-sitter.
/// A block is real commented-out code iff:
///   - the parse succeeds with zero `ERROR` nodes, AND
///   - it contains at least one non-trivial statement (not just bare
///     identifiers like a TODO list).
/// English prose fails both checks.
fn find_commented_blocks(content: &str, rel_path: &str, lang: Lang) -> Vec<CommentedBlock> {
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

        // Shebangs and encoding declarations are boundaries, not content.
        if lang == Lang::Python && (trimmed.starts_with("#!") || trimmed.starts_with("# -*-")) {
            if !current_block.is_empty() {
                maybe_emit_block(&mut blocks, &current_block, rel_path, lang);
                current_block.clear();
            }
            continue;
        }

        if is_comment {
            current_block.push((line_num, trimmed.to_string()));
        } else if !current_block.is_empty() {
            maybe_emit_block(&mut blocks, &current_block, rel_path, lang);
            current_block.clear();
        }
    }

    if !current_block.is_empty() {
        maybe_emit_block(&mut blocks, &current_block, rel_path, lang);
    }

    blocks
}

/// Strip the leading `# ` or `// ` (and any amount of whitespace) from one
/// comment line, returning the payload. Preserves indentation beyond the
/// marker so the result reparses cleanly.
fn strip_comment_prefix(line: &str, lang: Lang) -> String {
    let marker = match lang {
        Lang::Python => "#",
        Lang::JavaScript | Lang::TypeScript => "//",
    };
    let trimmed = line.trim_start();
    if let Some(rest) = trimmed.strip_prefix(marker) {
        // Drop ONE leading space if present — preserve any structural
        // indentation after that (important for nested code).
        rest.strip_prefix(' ').unwrap_or(rest).to_string()
    } else {
        trimmed.to_string()
    }
}

/// Return true if the parsed tree has at least one ERROR node anywhere.
fn tree_has_errors(node: tree_sitter::Node) -> bool {
    if node.is_error() || node.kind() == "ERROR" {
        return true;
    }
    for i in 0..node.child_count() {
        if let Some(c) = node.child(i as u32) {
            if tree_has_errors(c) {
                return true;
            }
        }
    }
    false
}

/// Return true if the module body contains only trivial expression
/// statements whose sole content is a single identifier — the typical
/// shape of an english TODO list or bullet-point comment.
fn only_trivial_identifiers(root: tree_sitter::Node, source: &str) -> bool {
    let mut statement_count = 0usize;
    let mut trivial_count = 0usize;

    for i in 0..root.named_child_count() {
        let stmt = match root.named_child(i as u32) {
            Some(n) => n,
            None => continue,
        };
        if stmt.kind() == "comment" {
            continue;
        }
        statement_count += 1;

        // Classify each statement. Trivial: expression_statement whose
        // only named child is an identifier or a string (a line like
        // "os" or "investigate the memory leak" (which parses as
        // identifier sequence → ERROR, caught earlier)).
        let is_trivial = stmt.kind() == "expression_statement"
            && stmt.named_child_count() == 1
            && stmt
                .named_child(0)
                .map(|c| matches!(c.kind(), "identifier" | "string"))
                .unwrap_or(false);
        if is_trivial {
            trivial_count += 1;
        }
    }

    let _ = source; // reserved for richer heuristics later
    statement_count > 0 && trivial_count == statement_count
}

fn maybe_emit_block(
    blocks: &mut Vec<CommentedBlock>,
    current_block: &[(u32, String)],
    rel_path: &str,
    lang: Lang,
) {
    if current_block.len() < 5 {
        return;
    }

    // Strip comment markers and feed the raw body to tree-sitter.
    let stripped: String = current_block
        .iter()
        .map(|(_, text)| strip_comment_prefix(text, lang))
        .collect::<Vec<_>>()
        .join("\n");

    let ts_lang = match lang {
        Lang::Python => tree_sitter_python::LANGUAGE.into(),
        Lang::JavaScript => tree_sitter_javascript::LANGUAGE.into(),
        Lang::TypeScript => tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into(),
    };
    let mut parser = tree_sitter::Parser::new();
    if parser.set_language(&ts_lang).is_err() {
        return;
    }
    let tree = match parser.parse(&stripped, None) {
        Some(t) => t,
        None => return,
    };
    let root = tree.root_node();

    // Any syntax error → treat as prose.
    if tree_has_errors(root) {
        return;
    }

    // An empty parse is not code.
    if root.named_child_count() == 0 {
        return;
    }

    // TODO-list / single-identifier-per-line shapes are prose even
    // though they parse cleanly (`os\nsys\njson\n` is valid Python).
    if only_trivial_identifiers(root, &stripped) {
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
        // Pre-split file content into lines once per file so we can cheaply
        // look up the source line of each import to check for `# noqa`.
        let lines: Vec<&str> = fd.content.lines().collect();
        for (name, line, stmt) in &fd.imports {
            if fd.used_identifiers.contains(name.as_str()) {
                continue;
            }
            // Respect `# noqa` / `# noqa: F401` on the import line.
            let line_text = lines
                .get((*line as usize).saturating_sub(1))
                .copied()
                .unwrap_or("");
            if has_noqa_unused_import(line_text, fd.lang) {
                continue;
            }
            unused_imports.push(UnusedImport {
                path: fd.rel_path.clone(),
                line: *line,
                name: name.clone(),
                import_statement: stmt.clone(),
            });
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
