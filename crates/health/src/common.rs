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
    "target",           // Rust/Cargo, also general build output
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "env",
    ".egg-info",
    // Go / PHP (Composer)
    "vendor",
    // Java / Kotlin
    ".gradle",
    ".idea",
    "out",
    // C / C++
    "cmake-build-debug",
    "cmake-build-release",
    // Ruby
    ".bundle",
    // General
    ".cache",
    "coverage",
    ".coverage",
    ".terraform",
];

/// Source file extensions we care about for analysis.
pub const SOURCE_EXTENSIONS: &[&str] = &[
    // Python
    "py",
    // JavaScript / TypeScript
    "js", "ts", "jsx", "tsx", "mjs", "mts", "cjs", "cts",
    // Rust
    "rs",
    // Go
    "go",
    // C / C++
    "c", "h", "cpp", "hpp", "cc", "cxx", "hxx",
    // Java / Kotlin
    "java", "kt", "kts",
    // Ruby
    "rb",
    // PHP
    "php",
    // Swift
    "swift",
    // C#
    "cs",
];

/// Check if a directory entry should be skipped.
/// Checks both hardcoded names AND detects non-standard Python venvs
/// (by looking for pyvenv.cfg inside the directory).
pub fn should_skip(name: &str) -> bool {
    ALWAYS_SKIP.iter().any(|s| *s == name)
}

/// Extended skip check that also detects non-standard virtualenvs
/// by looking for `pyvenv.cfg`. Use in filter_entry where you have
/// access to the full path.
pub fn should_skip_entry(entry: &ignore::DirEntry) -> bool {
    if let Some(name) = entry.file_name().to_str() {
        if should_skip(name) {
            return true;
        }
    }
    // Detect non-standard Python venvs (e.g. tg-session-env/)
    if entry.file_type().map(|ft| ft.is_dir()).unwrap_or(false) {
        if entry.path().join("pyvenv.cfg").exists() {
            return true;
        }
    }
    false
}

/// Recursively walk all nodes in a tree-sitter tree, calling f on each.
pub fn walk_nodes<F>(cursor: &mut tree_sitter::TreeCursor, f: &mut F)
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

/// Normalize path separators to forward slashes (Windows compatibility).
pub fn normalize_path(path: &str) -> String {
    path.replace('\\', "/")
}
