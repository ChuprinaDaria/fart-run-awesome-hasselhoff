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
            if node.kind() == "import_statement" || node.kind() == "import_from_statement" {
                // Try named fields first, then scan children
                let module_text = node
                    .child_by_field_name("module_name")
                    .or_else(|| node.child_by_field_name("name"))
                    .and_then(|n| n.utf8_text(source.as_bytes()).ok().map(|s| s.to_string()));

                if let Some(text) = module_text {
                    imports.push(text);
                } else {
                    // Fallback: scan children for dotted_name or relative_import
                    for i in 0..node.child_count() {
                        if let Some(child) = node.child(i as u32) {
                            if child.kind() == "dotted_name"
                                || child.kind() == "relative_import"
                            {
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
        "js" => source_dir.join(imp),
        _ => return None,
    };

    let rel = relative_path.strip_prefix(root).ok()?;
    let rel_str = rel.to_string_lossy().to_string();

    if all_files.contains(&rel_str) {
        return Some(rel_str);
    }

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
        let index = format!("{}/index.{}", rel_str, ext);
        if all_files.contains(&index) {
            return Some(index);
        }
    }

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
            let rel_str = rel.to_string_lossy().to_string();
            all_files.insert(rel_str.clone());
            source_files.push((entry_path.to_path_buf(), rel_str));
        }
    }

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
