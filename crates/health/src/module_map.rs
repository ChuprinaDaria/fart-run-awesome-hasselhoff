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
            if node.kind() == "import_from_statement" {
                // `from X import Y, Z as W` -> emit "X.Y" and "X.Z"
                // so resolver can target the specific file/attribute, not just X/__init__.
                let module_text = node
                    .child_by_field_name("module_name")
                    .and_then(|n| n.utf8_text(source.as_bytes()).ok().map(|s| s.to_string()));

                // Gather imported names from `import_list` / `aliased_import` / `dotted_name` children.
                // Skip `import *` (cannot resolve a specific target).
                let mut names: Vec<String> = Vec::new();
                let mut has_star = false;
                let module_name_id = node.child_by_field_name("module_name").map(|n| n.id());
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i as u32) {
                        match child.kind() {
                            "wildcard_import" => has_star = true,
                            "dotted_name" => {
                                // The module_name child is the source of the import; every
                                // other dotted_name sibling is an imported name.
                                if module_name_id != Some(child.id()) {
                                    if let Ok(t) = child.utf8_text(source.as_bytes()) {
                                        names.push(t.to_string());
                                    }
                                }
                            }
                            "aliased_import" => {
                                if let Some(name_node) = child.child_by_field_name("name") {
                                    if let Ok(t) = name_node.utf8_text(source.as_bytes()) {
                                        names.push(t.to_string());
                                    }
                                }
                            }
                            _ => {}
                        }
                    }
                }

                if let Some(module) = module_text {
                    if has_star || names.is_empty() {
                        imports.push(module);
                    } else {
                        // For `from . import x` or `from .. import x`, `module` is
                        // already the dot prefix — concat without adding another dot.
                        // For `from .pkg import x` / `from core.pkg import x`,
                        // join with a dot separator.
                        let joiner = if module.ends_with('.') { "" } else { "." };
                        for n in names {
                            imports.push(format!("{}{}{}", module, joiner, n));
                        }
                    }
                } else {
                    // Relative-only form: `from . import x` — no module_name field.
                    // Fall back to the old behavior: emit the first relative_import child.
                    for i in 0..node.child_count() {
                        if let Some(child) = node.child(i as u32) {
                            if child.kind() == "relative_import" {
                                if let Ok(t) = child.utf8_text(source.as_bytes()) {
                                    // Attach each imported name: "..x" -> ["..x.Y", "..x.Z"]
                                    if names.is_empty() {
                                        imports.push(t.to_string());
                                    } else {
                                        for n in &names {
                                            imports.push(format!("{}.{}", t, n));
                                        }
                                    }
                                }
                                break;
                            }
                        }
                    }
                }
            } else if node.kind() == "import_statement" {
                // `import foo.bar [as baz]` -> emit "foo.bar"
                for i in 0..node.child_count() {
                    if let Some(child) = node.child(i as u32) {
                        match child.kind() {
                            "dotted_name" => {
                                if let Ok(t) = child.utf8_text(source.as_bytes()) {
                                    imports.push(t.to_string());
                                }
                            }
                            "aliased_import" => {
                                if let Some(name_node) = child.child_by_field_name("name") {
                                    if let Ok(t) = name_node.utf8_text(source.as_bytes()) {
                                        imports.push(t.to_string());
                                    }
                                }
                            }
                            _ => {}
                        }
                    }
                }
            }
        }
        "js" => {
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
                                    if let Some(arg) = args.child(1_u32) {
                                        if arg.kind() == "string" {
                                            if let Ok(text) = arg.utf8_text(source.as_bytes()) {
                                                let cleaned =
                                                    text.trim_matches(|c| c == '\'' || c == '"');
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

/// Check if an import string looks like a local import we can resolve.
///
/// `package_roots` is the set of top-level directories in the project
/// (e.g. {"core", "plugins", "gui"}). A Python import is local if it
/// either starts with `.` (relative) or its first dotted segment is
/// one of those roots (absolute project-rooted import).
fn is_local_import(imp: &str, lang: &str, package_roots: &HashSet<String>) -> bool {
    match lang {
        "python" => {
            if imp.starts_with('.') {
                return true;
            }
            let first = imp.split('.').next().unwrap_or("");
            !first.is_empty() && package_roots.contains(first)
        }
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
    match lang {
        "python" => resolve_python_import(imp, source_file, root, all_files),
        "js" => resolve_js_import(imp, source_file, root, all_files),
        _ => None,
    }
}

fn resolve_python_import(
    imp: &str,
    source_file: &Path,
    root: &Path,
    all_files: &HashSet<String>,
) -> Option<String> {
    // Relative imports: `.foo`, `..foo.bar` — resolve against source_file's dir.
    // Absolute imports: `core.foo.bar` — resolve against project root.
    let (base, module) = if imp.starts_with('.') {
        let dots = imp.chars().take_while(|c| *c == '.').count();
        let module = &imp[dots..];
        let mut base = source_file.parent()?.to_path_buf();
        for _ in 1..dots {
            base = base.parent()?.to_path_buf();
        }
        (base, module.to_string())
    } else {
        (root.to_path_buf(), imp.to_string())
    };

    if module.is_empty() {
        return None;
    }

    // Walk up the module path, trying the longest prefix first.
    // For `core.context7_mcp.build_context7_directive`, try:
    //   1. core/context7_mcp/build_context7_directive.py
    //   2. core/context7_mcp/build_context7_directive/__init__.py
    //   3. core/context7_mcp.py
    //   4. core/context7_mcp/__init__.py
    // The first hit wins. This handles both `from pkg.mod import fn`
    // (where fn is an attribute — step 3 wins) and
    // `from pkg import submod` (where submod is a file — step 1 wins
    // after names are appended).
    let parts: Vec<&str> = module.split('.').collect();
    for take in (1..=parts.len()).rev() {
        let prefix = parts[..take].join("/");
        let file_path = base.join(format!("{}.py", prefix));
        if let Some(rel) = try_rel(&file_path, root) {
            if all_files.contains(&rel) {
                return Some(rel);
            }
        }
        let init_path = base.join(format!("{}/__init__.py", prefix));
        if let Some(rel) = try_rel(&init_path, root) {
            if all_files.contains(&rel) {
                return Some(rel);
            }
        }
    }

    None
}

fn resolve_js_import(
    imp: &str,
    source_file: &Path,
    root: &Path,
    all_files: &HashSet<String>,
) -> Option<String> {
    let source_dir = source_file.parent()?;
    let target = source_dir.join(imp);
    let rel = try_rel(&target, root)?;
    if all_files.contains(&rel) {
        return Some(rel);
    }
    for ext in &["js", "ts", "jsx", "tsx", "mjs", "mts"] {
        let with_ext = format!("{}.{}", rel, ext);
        if all_files.contains(&with_ext) {
            return Some(with_ext);
        }
        let index = format!("{}/index.{}", rel, ext);
        if all_files.contains(&index) {
            return Some(index);
        }
    }
    None
}

fn try_rel(p: &Path, root: &Path) -> Option<String> {
    p.strip_prefix(root)
        .ok()
        .map(|r| r.to_string_lossy().replace('\\', "/"))
}

#[pyfunction]
pub fn scan_module_map(path: &str, entry_point_paths: Vec<String>) -> PyResult<ModuleMapResult> {
    let root = Path::new(path);
    if !root.is_dir() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            format!("Not a directory: {}", path),
        ));
    }

    let mut all_files: HashSet<String> = HashSet::new();
    let mut source_files: Vec<(PathBuf, String)> = Vec::new();

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
            let rel_str = rel.to_string_lossy().replace('\\', "/");
            all_files.insert(rel_str.clone());
            source_files.push((entry_path.to_path_buf(), rel_str));
        }
    }

    // Top-level directory names that contain at least one source file —
    // used to classify absolute Python imports as local.
    let package_roots: HashSet<String> = all_files
        .iter()
        .filter_map(|f| f.split('/').next())
        .filter(|s| !s.is_empty() && !s.ends_with(".py") && !s.contains('.'))
        .map(|s| s.to_string())
        .collect();

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

        let mut resolved = Vec::new();
        for imp in &raw_imports {
            if is_local_import(imp, lang, &package_roots) {
                if let Some(resolved_path) =
                    resolve_local_import(imp, abs_path, root, &all_files, lang)
                {
                    // Don't count a file as importing itself.
                    if &resolved_path != rel_path {
                        resolved.push(resolved_path.clone());
                        *imported_by.entry(resolved_path).or_insert(0) += 1;
                    }
                }
            }
        }

        file_imports.insert(rel_path.clone(), resolved);
    }

    let mut modules: Vec<ModuleInfo> = Vec::new();
    for (rel_path, imports) in &file_imports {
        let count = imported_by.get(rel_path).copied().unwrap_or(0);
        modules.push(ModuleInfo {
            path: rel_path.clone(),
            imports: imports.clone(),
            imported_by_count: count,
        });
    }

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

    // Orphan candidates
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
