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
