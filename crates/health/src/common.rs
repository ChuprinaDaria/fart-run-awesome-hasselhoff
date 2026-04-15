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
