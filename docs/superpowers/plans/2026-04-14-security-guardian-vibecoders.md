# Security Guardian for Vibe Coders — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand security scanning with secret detection, autostart persistence checks, suspicious package scanning, CPU anomaly detection, extended process signatures, and a blocking Hasselhoff critical alert dialog with Coursera education links.

**Architecture:** 2 new Rust modules (`secrets.rs`, `autostart.rs`) + extended `processes.rs` + new Python scanner `scan_suspicious_packages()` + `CriticalAlertDialog` in GUI + Coursera links in explanations. All new scanners wire through existing `plugin.py` → `scanners.py` → GUI pipeline.

**Tech Stack:** Rust (PyO3, sysinfo, regex), Python (PyQt5, Levenshtein), existing sentinel + scanners infrastructure.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `crates/sentinel/Cargo.toml` | MODIFY | Add `regex` and `rayon` deps |
| `crates/sentinel/src/secrets.rs` | CREATE | Secret pattern scanner (regex-based, parallel walk) |
| `crates/sentinel/src/autostart.rs` | CREATE | Shell RC, systemd user, XDG autostart scanner |
| `crates/sentinel/src/processes.rs` | MODIFY | Extended sigs + CPU anomaly + /tmp process detection |
| `crates/sentinel/src/lib.rs` | MODIFY | Export new modules + pyfunction bindings |
| `plugins/security_scan/scanners.py` | MODIFY | Python wrappers for new Rust scanners + `scan_suspicious_packages()` |
| `plugins/security_scan/plugin.py` | MODIFY | Wire new scanners into `collect()` |
| `gui/security_explanations.py` | MODIFY | New explanation entries + Coursera links + patterns |
| `gui/pages/security.py` | MODIFY | `CriticalAlertDialog` class + education link in detail panel |
| `claude_nagger/i18n/en.py` | MODIFY | New i18n strings for alerts/dialogs |
| `claude_nagger/i18n/ua.py` | MODIFY | Ukrainian translations |

---

### Task 1: Add regex and rayon to Cargo.toml

**Files:**
- Modify: `crates/sentinel/Cargo.toml`

- [ ] **Step 1: Add dependencies**

```toml
[dependencies]
pyo3 = { version = "0.25", features = ["extension-module"] }
sysinfo = "0.36"
regex = "1"
rayon = "1.10"

[target.'cfg(unix)'.dependencies]
libc = "0.2"
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/dchuprina/claude-monitor/crates/sentinel && cargo check`
Expected: Compiles without errors

- [ ] **Step 3: Commit**

```bash
git add crates/sentinel/Cargo.toml
git commit -m "feat(sentinel): add regex and rayon dependencies for secret scanner"
```

---

### Task 2: Secret Scanner — `secrets.rs`

**Files:**
- Create: `crates/sentinel/src/secrets.rs`

- [ ] **Step 1: Create secrets.rs with SecretFinding struct and patterns**

```rust
//! Secret scanner — detects hardcoded API keys, tokens, passwords in source files.
//!
//! Scans ALL directories (with smart skips) using compiled regex patterns.
//! Parallel directory walk via rayon for performance.

use pyo3::prelude::*;
use rayon::prelude::*;
use regex::Regex;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// Max file size to scan (1MB). Larger files are binary/generated.
const MAX_FILE_SIZE: u64 = 1_048_576;

/// Max directory depth.
const MAX_DEPTH: usize = 10;

#[pyclass]
#[derive(Clone)]
pub struct SecretFinding {
    #[pyo3(get)]
    pub severity: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub line_number: usize,
    #[pyo3(get)]
    pub secret_type: String,
}

#[pymethods]
impl SecretFinding {
    fn __repr__(&self) -> String {
        format!(
            "SecretFinding(type='{}', path='{}', line={})",
            self.secret_type, self.path, self.line_number
        )
    }
}

struct SecretPattern {
    name: &'static str,
    regex: Regex,
    description: &'static str,
}

fn build_patterns() -> Vec<SecretPattern> {
    vec![
        SecretPattern {
            name: "aws_access_key",
            regex: Regex::new(r"AKIA[0-9A-Z]{16}").unwrap(),
            description: "AWS Access Key ID",
        },
        SecretPattern {
            name: "aws_secret_key",
            regex: Regex::new(r#"(?i)aws_secret_access_key\s*[=:]\s*["']?([A-Za-z0-9/+=]{40})"#).unwrap(),
            description: "AWS Secret Access Key",
        },
        SecretPattern {
            name: "github_token",
            regex: Regex::new(r"ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|ghs_[A-Za-z0-9]{36}|ghu_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}").unwrap(),
            description: "GitHub Token",
        },
        SecretPattern {
            name: "openai_key",
            regex: Regex::new(r"sk-[A-Za-z0-9]{20,}").unwrap(),
            description: "OpenAI API Key",
        },
        SecretPattern {
            name: "anthropic_key",
            regex: Regex::new(r"sk-ant-[A-Za-z0-9\-]{20,}").unwrap(),
            description: "Anthropic API Key",
        },
        SecretPattern {
            name: "stripe_key",
            regex: Regex::new(r"sk_live_[A-Za-z0-9]{24,}|sk_test_[A-Za-z0-9]{24,}|pk_live_[A-Za-z0-9]{24,}|pk_test_[A-Za-z0-9]{24,}").unwrap(),
            description: "Stripe API Key",
        },
        SecretPattern {
            name: "slack_token",
            regex: Regex::new(r"xox[bpors]-[A-Za-z0-9\-]{10,}").unwrap(),
            description: "Slack Token",
        },
        SecretPattern {
            name: "private_key",
            regex: Regex::new(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----").unwrap(),
            description: "Private Key",
        },
        SecretPattern {
            name: "generic_secret",
            regex: Regex::new(r#"(?i)(password|passwd|pwd|secret|token|api_key|apikey|api-key)\s*[=:]\s*["']([^"'\s]{8,})["']"#).unwrap(),
            description: "Hardcoded secret",
        },
        SecretPattern {
            name: "database_url",
            regex: Regex::new(r"(?i)(postgres|mysql|mongodb|redis)://[^:]+:[^@]+@").unwrap(),
            description: "Database URL with credentials",
        },
        SecretPattern {
            name: "bearer_token",
            regex: Regex::new(r#"(?i)["']Bearer\s+[A-Za-z0-9\-._~+/]+=*["']"#).unwrap(),
            description: "Hardcoded Bearer Token",
        },
        SecretPattern {
            name: "google_api_key",
            regex: Regex::new(r"AIza[0-9A-Za-z\-_]{35}").unwrap(),
            description: "Google API Key",
        },
        SecretPattern {
            name: "telegram_bot_token",
            regex: Regex::new(r"[0-9]{8,10}:[A-Za-z0-9_-]{35}").unwrap(),
            description: "Telegram Bot Token",
        },
    ]
}

/// Directories to always skip.
const SKIP_DIRS: &[&str] = &[
    "node_modules", ".git", "__pycache__", "target", ".cargo", ".rustup",
    "venv", ".venv", ".local", ".cache", ".npm", ".yarn", ".pnpm",
    "dist", "build", ".next", ".nuxt", "coverage",
    // System dirs
    "proc", "sys", "dev", "run", "snap",
];

/// File extensions to scan.
const SCAN_EXTENSIONS: &[&str] = &[
    "py", "js", "ts", "jsx", "tsx", "rb", "go", "java", "rs", "php",
    "env", "txt", "md", "yaml", "yml", "json", "toml", "cfg", "ini", "conf",
    "sh", "bash", "zsh", "properties", "xml",
];

fn should_scan_file(path: &Path) -> bool {
    // Check extension
    let ext = path.extension()
        .and_then(|e| e.to_str())
        .unwrap_or("");

    let name = path.file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("");

    // Always scan .env files regardless of extension
    if name.starts_with(".env") {
        return true;
    }

    if SCAN_EXTENSIONS.iter().any(|e| ext.eq_ignore_ascii_case(e)) {
        // Check file size
        if let Ok(meta) = path.metadata() {
            return meta.len() <= MAX_FILE_SIZE;
        }
    }
    false
}

fn collect_files(base: &Path, max_depth: usize) -> Vec<PathBuf> {
    let mut files = Vec::new();
    collect_files_recursive(base, &mut files, 0, max_depth);
    files
}

fn collect_files_recursive(dir: &Path, files: &mut Vec<PathBuf>, depth: usize, max_depth: usize) {
    if depth > max_depth {
        return;
    }
    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name();
        let name_str = name.to_string_lossy();

        if path.is_dir() {
            let name_lower = name_str.to_lowercase();
            if SKIP_DIRS.iter().any(|d| name_lower == *d) {
                continue;
            }
            // Skip hidden dirs except .config (for autostart detection elsewhere)
            if name_str.starts_with('.') && name_str != ".config" && name_str != ".env" {
                continue;
            }
            collect_files_recursive(&path, files, depth + 1, max_depth);
        } else if path.is_file() && should_scan_file(&path) {
            files.push(path);
        }
    }
}

/// False positive patterns — skip lines matching these.
fn is_false_positive(line: &str, secret_name: &str) -> bool {
    let lower = line.to_lowercase();
    // Skip comments, examples, docs
    let trimmed = lower.trim();
    if trimmed.starts_with("//") || trimmed.starts_with('#') || trimmed.starts_with("<!--") {
        // But if it contains an actual key pattern, still flag it
        if secret_name != "generic_secret" {
            return false; // Real keys in comments are still secrets
        }
        return true;
    }
    // Skip placeholder values
    if lower.contains("xxx") || lower.contains("your_") || lower.contains("example")
        || lower.contains("placeholder") || lower.contains("<your") || lower.contains("fixme")
        || lower.contains("todo") || lower.contains("changeme") || lower.contains("replace_me")
    {
        return true;
    }
    // Skip test fixtures and mock data
    if lower.contains("test") && (lower.contains("mock") || lower.contains("fake") || lower.contains("dummy")) {
        return true;
    }
    false
}

/// Scan all directories for hardcoded secrets.
#[pyfunction]
#[pyo3(signature = (scan_paths=None))]
pub fn scan_secrets(scan_paths: Option<Vec<String>>) -> Vec<SecretFinding> {
    let paths: Vec<PathBuf> = scan_paths
        .unwrap_or_else(|| vec![dirs_home().to_string_lossy().to_string()])
        .into_iter()
        .map(|p| {
            let expanded = if p.starts_with('~') {
                dirs_home().join(&p[2..])
            } else {
                PathBuf::from(p)
            };
            expanded
        })
        .collect();

    let patterns = build_patterns();

    // Collect all files first
    let mut all_files = Vec::new();
    for base in &paths {
        all_files.extend(collect_files(base, MAX_DEPTH));
    }

    // Parallel scan with rayon
    let findings = Mutex::new(Vec::new());

    all_files.par_iter().for_each(|file_path| {
        let content = match std::fs::read_to_string(file_path) {
            Ok(c) => c,
            Err(_) => return, // Binary file or permission error
        };

        let path_str = file_path.to_string_lossy().to_string();

        for (line_num, line) in content.lines().enumerate() {
            for pattern in &patterns {
                if pattern.regex.is_match(line) && !is_false_positive(line, pattern.name) {
                    let mut f = findings.lock().unwrap();
                    f.push(SecretFinding {
                        severity: "critical".to_string(),
                        description: format!(
                            "{} found in {}:{}",
                            pattern.description, path_str, line_num + 1
                        ),
                        path: path_str.clone(),
                        line_number: line_num + 1,
                        secret_type: pattern.name.to_string(),
                    });
                    break; // One finding per line
                }
            }
        }
    });

    findings.into_inner().unwrap()
}

fn dirs_home() -> PathBuf {
    #[cfg(unix)]
    {
        std::env::var("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("/root"))
    }
    #[cfg(windows)]
    {
        std::env::var("USERPROFILE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("C:\\Users"))
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/dchuprina/claude-monitor/crates/sentinel && cargo check`
Expected: Compiles (lib.rs not updated yet, so `secrets` module unused — that's OK)

- [ ] **Step 3: Commit**

```bash
git add crates/sentinel/src/secrets.rs
git commit -m "feat(sentinel): add secret scanner — regex-based, parallel walk with rayon"
```

---

### Task 3: Autostart Persistence Scanner — `autostart.rs`

**Files:**
- Create: `crates/sentinel/src/autostart.rs`

- [ ] **Step 1: Create autostart.rs**

```rust
//! Autostart persistence scanner — shell RC files, systemd user services, XDG autostart.
//!
//! Detects malicious persistence mechanisms that AI agents might inject.

use pyo3::prelude::*;
use std::path::PathBuf;

/// Suspicious patterns in shell RC / autostart files.
const SUSPICIOUS_PATTERNS: &[(&str, &str, &str)] = &[
    ("curl|bash", "critical", "Pipe-to-shell in autostart: {}"),
    ("curl|sh", "critical", "Pipe-to-shell in autostart: {}"),
    ("wget|bash", "critical", "Pipe-to-shell in autostart: {}"),
    ("wget|sh", "critical", "Pipe-to-shell in autostart: {}"),
    ("curl -s|", "critical", "Silent curl piped in autostart: {}"),
    ("eval $(curl", "critical", "Remote eval in autostart: {}"),
    ("eval $(wget", "critical", "Remote eval in autostart: {}"),
    ("base64 -d", "critical", "Base64 decode in autostart: {}"),
    ("base64 --decode", "critical", "Base64 decode in autostart: {}"),
    ("/dev/tcp/", "critical", "TCP redirect in autostart: {}"),
    ("nc -e", "critical", "Netcat exec in autostart: {}"),
    ("ncat -e", "critical", "Ncat exec in autostart: {}"),
    ("socat exec:", "critical", "Socat exec in autostart: {}"),
    ("python -c 'import socket", "critical", "Python reverse shell in autostart: {}"),
    ("python3 -c 'import socket", "critical", "Python reverse shell in autostart: {}"),
    ("stratum+tcp://", "critical", "Mining pool in autostart: {}"),
    ("xmrig", "critical", "Cryptominer in autostart: {}"),
    ("minerd", "critical", "Cryptominer in autostart: {}"),
    ("/tmp/.", "high", "Hidden /tmp path in autostart: {}"),
    ("/dev/shm/", "high", "/dev/shm path in autostart: {}"),
];

/// Suspicious PATH additions.
const SUSPICIOUS_PATH_DIRS: &[&str] = &[
    "/tmp", "/dev/shm", "/var/tmp",
];

#[pyclass]
#[derive(Clone)]
pub struct AutostartFinding {
    #[pyo3(get)]
    pub severity: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub path: String,
    #[pyo3(get)]
    pub source_type: String, // "shell_rc", "systemd_user", "xdg_autostart", "xdg_desktop"
    #[pyo3(get)]
    pub line_number: usize,
}

#[pymethods]
impl AutostartFinding {
    fn __repr__(&self) -> String {
        format!(
            "AutostartFinding(severity='{}', type='{}', path='{}', line={})",
            self.severity, self.source_type, self.path, self.line_number
        )
    }
}

/// Scan all autostart persistence points.
#[pyfunction]
pub fn scan_autostart() -> Vec<AutostartFinding> {
    let mut findings = Vec::new();
    let home = dirs_home();

    scan_shell_rc_files(&home, &mut findings);

    #[cfg(target_os = "linux")]
    {
        scan_systemd_user_services(&home, &mut findings);
        scan_xdg_autostart(&home, &mut findings);
    }

    #[cfg(target_os = "macos")]
    {
        scan_launchd_user(&home, &mut findings);
    }

    findings
}

/// Scan shell RC files for suspicious commands.
fn scan_shell_rc_files(home: &std::path::Path, findings: &mut Vec<AutostartFinding>) {
    let rc_files = [
        ".bashrc", ".bash_profile", ".profile", ".zshrc", ".zprofile",
        ".bash_login", ".zlogin",
    ];

    for rc in &rc_files {
        let path = home.join(rc);
        if !path.exists() {
            continue;
        }
        let content = match std::fs::read_to_string(&path) {
            Ok(c) => c,
            Err(_) => continue,
        };
        let path_str = path.to_string_lossy().to_string();

        for (line_num, line) in content.lines().enumerate() {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }
            let line_lower = trimmed.to_lowercase();

            // Check suspicious command patterns
            for &(pattern, severity, desc_template) in SUSPICIOUS_PATTERNS {
                if line_lower.contains(pattern) {
                    findings.push(AutostartFinding {
                        severity: severity.to_string(),
                        description: desc_template.replace("{}", &truncate(trimmed, 120)),
                        path: path_str.clone(),
                        source_type: "shell_rc".to_string(),
                        line_number: line_num + 1,
                    });
                    break;
                }
            }

            // Check suspicious PATH additions
            if line_lower.contains("export path=") || line_lower.contains("path=") {
                for sus_dir in SUSPICIOUS_PATH_DIRS {
                    if line_lower.contains(sus_dir) {
                        findings.push(AutostartFinding {
                            severity: "high".to_string(),
                            description: format!(
                                "Suspicious PATH addition ({}) in {}: {}",
                                sus_dir, rc, truncate(trimmed, 100)
                            ),
                            path: path_str.clone(),
                            source_type: "shell_rc".to_string(),
                            line_number: line_num + 1,
                        });
                        break;
                    }
                }
            }
        }
    }
}

/// Scan systemd user services for suspicious ExecStart.
#[cfg(target_os = "linux")]
fn scan_systemd_user_services(home: &std::path::Path, findings: &mut Vec<AutostartFinding>) {
    let service_dir = home.join(".config/systemd/user");
    let entries = match std::fs::read_dir(&service_dir) {
        Ok(e) => e,
        Err(_) => return,
    };

    let one_day = std::time::Duration::from_secs(86400);
    let now = std::time::SystemTime::now();

    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name();
        let name_str = name.to_string_lossy();

        if !name_str.ends_with(".service") && !name_str.ends_with(".timer") {
            continue;
        }

        let content = match std::fs::read_to_string(&path) {
            Ok(c) => c,
            Err(_) => continue,
        };
        let path_str = path.to_string_lossy().to_string();

        // Check if recently created
        let is_recent = path.metadata()
            .and_then(|m| m.created().or(m.modified()))
            .ok()
            .and_then(|t| now.duration_since(t).ok())
            .map(|d| d < one_day)
            .unwrap_or(false);

        for (line_num, line) in content.lines().enumerate() {
            let trimmed = line.trim();
            if !trimmed.starts_with("ExecStart=") && !trimmed.starts_with("ExecStartPre=") {
                continue;
            }
            let cmd = trimmed.split_once('=').map(|(_, v)| v).unwrap_or("");
            let cmd_lower = cmd.to_lowercase();

            for &(pattern, severity, desc_template) in SUSPICIOUS_PATTERNS {
                if cmd_lower.contains(pattern) {
                    findings.push(AutostartFinding {
                        severity: severity.to_string(),
                        description: desc_template.replace("{}", &format!(
                            "{} (service: {})", truncate(cmd, 100), name_str
                        )),
                        path: path_str.clone(),
                        source_type: "systemd_user".to_string(),
                        line_number: line_num + 1,
                    });
                    break;
                }
            }

            // Flag services running from /tmp or /dev/shm
            if cmd_lower.contains("/tmp/") || cmd_lower.contains("/dev/shm/") || cmd_lower.contains("/var/tmp/") {
                findings.push(AutostartFinding {
                    severity: "critical".to_string(),
                    description: format!(
                        "Systemd user service '{}' runs from temp directory: {}",
                        name_str, truncate(cmd, 100)
                    ),
                    path: path_str.clone(),
                    source_type: "systemd_user".to_string(),
                    line_number: line_num + 1,
                });
            }
        }

        // Flag recently created services
        if is_recent {
            findings.push(AutostartFinding {
                severity: "high".to_string(),
                description: format!(
                    "Recently created systemd user service: {} — verify origin",
                    name_str
                ),
                path: path_str,
                source_type: "systemd_user".to_string(),
                line_number: 0,
            });
        }
    }
}

/// Scan XDG autostart entries.
#[cfg(target_os = "linux")]
fn scan_xdg_autostart(home: &std::path::Path, findings: &mut Vec<AutostartFinding>) {
    let dirs = [
        home.join(".config/autostart"),
        home.join(".local/share/applications"),
    ];

    for dir in &dirs {
        let entries = match std::fs::read_dir(dir) {
            Ok(e) => e,
            Err(_) => continue,
        };

        for entry in entries.flatten() {
            let path = entry.path();
            let name_str = entry.file_name().to_string_lossy().to_string();
            if !name_str.ends_with(".desktop") {
                continue;
            }

            let content = match std::fs::read_to_string(&path) {
                Ok(c) => c,
                Err(_) => continue,
            };
            let path_str = path.to_string_lossy().to_string();

            let mut has_hidden = false;
            let mut has_no_display = false;
            let mut exec_line = String::new();
            let mut exec_line_num = 0;

            for (line_num, line) in content.lines().enumerate() {
                let trimmed = line.trim();
                if trimmed.starts_with("Hidden=true") {
                    has_hidden = true;
                }
                if trimmed.starts_with("NoDisplay=true") {
                    has_no_display = true;
                }
                if trimmed.starts_with("Exec=") {
                    exec_line = trimmed["Exec=".len()..].to_string();
                    exec_line_num = line_num + 1;
                }
            }

            if !exec_line.is_empty() {
                let exec_lower = exec_line.to_lowercase();

                // Check suspicious commands
                for &(pattern, severity, desc_template) in SUSPICIOUS_PATTERNS {
                    if exec_lower.contains(pattern) {
                        findings.push(AutostartFinding {
                            severity: severity.to_string(),
                            description: desc_template.replace("{}", &format!(
                                "{} (desktop: {})", truncate(&exec_line, 100), name_str
                            )),
                            path: path_str.clone(),
                            source_type: "xdg_autostart".to_string(),
                            line_number: exec_line_num,
                        });
                        break;
                    }
                }

                // Hidden + NoDisplay = trying to hide from user
                if has_hidden && has_no_display {
                    findings.push(AutostartFinding {
                        severity: "high".to_string(),
                        description: format!(
                            "Hidden autostart entry '{}' with Hidden=true + NoDisplay=true: {}",
                            name_str, truncate(&exec_line, 100)
                        ),
                        path: path_str.clone(),
                        source_type: "xdg_autostart".to_string(),
                        line_number: exec_line_num,
                    });
                }

                // Exec from temp dirs
                if exec_lower.contains("/tmp/") || exec_lower.contains("/dev/shm/") {
                    findings.push(AutostartFinding {
                        severity: "critical".to_string(),
                        description: format!(
                            "Autostart '{}' runs from temp directory: {}",
                            name_str, truncate(&exec_line, 100)
                        ),
                        path: path_str.clone(),
                        source_type: "xdg_autostart".to_string(),
                        line_number: exec_line_num,
                    });
                }
            }
        }
    }
}

/// Scan macOS user LaunchAgents.
#[cfg(target_os = "macos")]
fn scan_launchd_user(home: &std::path::Path, findings: &mut Vec<AutostartFinding>) {
    let dir = home.join("Library/LaunchAgents");
    let entries = match std::fs::read_dir(&dir) {
        Ok(e) => e,
        Err(_) => return,
    };

    let one_day = std::time::Duration::from_secs(86400);
    let now = std::time::SystemTime::now();

    for entry in entries.flatten() {
        let path = entry.path();
        if path.extension().map(|e| e != "plist").unwrap_or(true) {
            continue;
        }

        let content = match std::fs::read_to_string(&path) {
            Ok(c) => c,
            Err(_) => continue,
        };
        let path_str = path.to_string_lossy().to_string();
        let name_str = entry.file_name().to_string_lossy().to_string();
        let content_lower = content.to_lowercase();

        for &(pattern, severity, desc_template) in SUSPICIOUS_PATTERNS {
            if content_lower.contains(pattern) {
                findings.push(AutostartFinding {
                    severity: severity.to_string(),
                    description: desc_template.replace("{}", &format!(
                        "LaunchAgent: {}", name_str
                    )),
                    path: path_str.clone(),
                    source_type: "launchd_user".to_string(),
                    line_number: 0,
                });
                break;
            }
        }

        // Flag recently created agents
        let is_recent = path.metadata()
            .and_then(|m| m.created().or(m.modified()))
            .ok()
            .and_then(|t| now.duration_since(t).ok())
            .map(|d| d < one_day)
            .unwrap_or(false);

        if is_recent {
            findings.push(AutostartFinding {
                severity: "high".to_string(),
                description: format!("Recently created LaunchAgent: {} — verify origin", name_str),
                path: path_str,
                source_type: "launchd_user".to_string(),
                line_number: 0,
            });
        }
    }
}

fn truncate(s: &str, max: usize) -> String {
    if s.len() <= max {
        s.to_string()
    } else {
        format!("{}…", &s[..max])
    }
}

fn dirs_home() -> PathBuf {
    #[cfg(unix)]
    {
        std::env::var("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("/root"))
    }
    #[cfg(windows)]
    {
        std::env::var("USERPROFILE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("C:\\Users"))
    }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /home/dchuprina/claude-monitor/crates/sentinel && cargo check`
Expected: Compiles

- [ ] **Step 3: Commit**

```bash
git add crates/sentinel/src/autostart.rs
git commit -m "feat(sentinel): add autostart persistence scanner — shell RC, systemd, XDG"
```

---

### Task 4: Extend Process Scanner — new sigs + CPU anomaly + /tmp detection

**Files:**
- Modify: `crates/sentinel/src/processes.rs`

- [ ] **Step 1: Add new signatures to SUSPICIOUS_NAMES**

Add after existing `("kswapd0", ...)` entry in `SUSPICIOUS_NAMES`:

```rust
    // Tunneling tools
    ("chisel", "high", "Tunneling tool detected: {}"),
    ("ngrok", "high", "Tunnel/expose tool detected: {}"),
    ("cloudflared", "high", "Cloudflare tunnel detected: {}"),
    ("frpc", "high", "Fast reverse proxy client detected: {}"),
    ("bore", "high", "TCP tunnel detected: {}"),

    // Brute force tools
    ("hydra", "critical", "Password brute force tool: {}"),
    ("john", "high", "Password cracker (John the Ripper): {}"),
    ("hashcat", "high", "Hash cracking tool: {}"),
    ("medusa", "critical", "Parallel brute force tool: {}"),

    // Recon/exploit
    ("nmap", "high", "Port scanner detected: {}"),
    ("masscan", "high", "Mass port scanner detected: {}"),
    ("sqlmap", "critical", "SQL injection tool: {}"),
    ("msfconsole", "critical", "Metasploit framework: {}"),
    ("msfvenom", "critical", "Metasploit payload generator: {}"),
```

- [ ] **Step 2: Add /tmp process detection in `scan_processes()`**

Add this block inside the `for (pid, process)` loop in `scan_processes()`, after the existing "Process from unexpected user" block (after line 217):

```rust
        // Process running from temp directories
        let exe_path = process.exe()
            .map(|p| p.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        if !exe_path.is_empty() {
            if exe_path.starts_with("/tmp/") || exe_path.starts_with("/dev/shm/")
                || exe_path.starts_with("/var/tmp/")
            {
                findings.push(ProcessFinding {
                    severity: "critical".to_string(),
                    description: format!(
                        "Process '{}' (PID {}) running from temp directory: {}",
                        name, pid_u32, exe_path
                    ),
                    pid: pid_u32,
                    name: name.clone(),
                    cmdline: truncate(&cmdline, 200),
                    user: user.clone(),
                });
            }

            // Process masquerading — name doesn't match binary
            let exe_name = std::path::Path::new(&*exe_path)
                .file_name()
                .map(|n| n.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            if !exe_name.is_empty() && !name.is_empty()
                && exe_name != name && !exe_name.contains(&name) && !name.contains(&*exe_name)
            {
                // Only flag if binary is from unusual location
                if !exe_path.starts_with("/usr/") && !exe_path.starts_with("/bin/")
                    && !exe_path.starts_with("/sbin/") && !exe_path.starts_with("/snap/")
                    && !exe_path.starts_with("/opt/") && !exe_path.starts_with("/lib/")
                    && !exe_path.contains("/nix/store/")
                {
                    findings.push(ProcessFinding {
                        severity: "high".to_string(),
                        description: format!(
                            "Process masquerading: name='{}' but binary='{}' (PID {})",
                            name, exe_path, pid_u32
                        ),
                        pid: pid_u32,
                        name: name.clone(),
                        cmdline: truncate(&cmdline, 200),
                        user: user.clone(),
                    });
                }
            }
        }
```

- [ ] **Step 3: Lower CPU threshold for unknown processes**

Update the existing CPU check block (around line 167). Replace the `if cpu > 90.0` block with:

```rust
        // High CPU usage detection
        let cpu = process.cpu_usage();
        let run_time = process.run_time();

        if run_time > 60 {
            let known_heavy = [
                "cc1", "cc1plus", "rustc", "cargo", "gcc", "g++", "clang",
                "node", "python", "java", "javac", "webpack", "esbuild",
                "ffmpeg", "blender", "make", "ninja", "cmake",
                "apt", "dpkg", "snap", "flatpak", "pip",
                "xorg", "gnome-shell", "kwin", "firefox", "chrome",
                "chromium", "code", "electron", "vscode",
            ];
            let is_known = known_heavy.iter().any(|k| name.contains(k));

            if cpu > 90.0 && !is_known {
                findings.push(ProcessFinding {
                    severity: "high".to_string(),
                    description: format!(
                        "Process '{}' (PID {}) using {:.0}% CPU for {}s — possible cryptominer",
                        name, pid_u32, cpu, run_time
                    ),
                    pid: pid_u32,
                    name: name.clone(),
                    cmdline: truncate(&cmdline, 200),
                    user: user.clone(),
                });
            } else if cpu > 50.0 && !is_known {
                findings.push(ProcessFinding {
                    severity: "medium".to_string(),
                    description: format!(
                        "Unknown process '{}' (PID {}) using {:.0}% CPU for {}s — investigate",
                        name, pid_u32, cpu, run_time
                    ),
                    pid: pid_u32,
                    name: name.clone(),
                    cmdline: truncate(&cmdline, 200),
                    user: user.clone(),
                });
            }
        }
```

- [ ] **Step 4: Verify it compiles**

Run: `cd /home/dchuprina/claude-monitor/crates/sentinel && cargo check`
Expected: Compiles

- [ ] **Step 5: Commit**

```bash
git add crates/sentinel/src/processes.rs
git commit -m "feat(sentinel): extend process scanner — tunnels, bruteforce, masquerading, CPU anomaly"
```

---

### Task 5: Wire new modules in lib.rs

**Files:**
- Modify: `crates/sentinel/src/lib.rs`

- [ ] **Step 1: Update lib.rs**

Replace the entire file with:

```rust
//! sentinel — fart.run cross-platform host IDS
//!
//! Because your vibe-coded app shouldn't have a cryptominer running next to it.

mod processes;
mod network;
mod filesystem;
mod crontab;
mod secrets;
mod autostart;

use pyo3::prelude::*;

/// sentinel Python module — cross-platform security scanning at native speed.
///
/// Because your vibe-coded app shouldn't have a cryptominer in crontab.
#[pymodule]
fn sentinel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<processes::ProcessFinding>()?;
    m.add_function(wrap_pyfunction!(processes::scan_processes, m)?)?;
    m.add_class::<network::NetworkFinding>()?;
    m.add_function(wrap_pyfunction!(network::scan_network, m)?)?;
    m.add_class::<filesystem::FileFinding>()?;
    m.add_function(wrap_pyfunction!(filesystem::scan_filesystem, m)?)?;
    m.add_class::<crontab::CronFinding>()?;
    m.add_function(wrap_pyfunction!(crontab::scan_scheduled_tasks, m)?)?;
    m.add_class::<secrets::SecretFinding>()?;
    m.add_function(wrap_pyfunction!(secrets::scan_secrets, m)?)?;
    m.add_class::<autostart::AutostartFinding>()?;
    m.add_function(wrap_pyfunction!(autostart::scan_autostart, m)?)?;
    Ok(())
}
```

- [ ] **Step 2: Build the sentinel module**

Run: `cd /home/dchuprina/claude-monitor/crates/sentinel && cargo build`
Expected: Compiles and links successfully

- [ ] **Step 3: Commit**

```bash
git add crates/sentinel/src/lib.rs
git commit -m "feat(sentinel): export secrets + autostart scanners in pymodule"
```

---

### Task 6: Python wrappers + suspicious package scanner

**Files:**
- Modify: `plugins/security_scan/scanners.py`

- [ ] **Step 1: Add Python wrappers for new Rust scanners**

Add after the existing `scan_sentinel_cron()` function (after line 82):

```python
def scan_sentinel_secrets(scan_paths: list[Path]) -> list[Finding]:
    """Detect hardcoded API keys, tokens, passwords in source files."""
    if not _sentinel_available:
        return []
    path_strs = [str(p) for p in scan_paths]
    findings = []
    for sf in sentinel.scan_secrets(path_strs):
        findings.append(Finding("secrets", sf.severity, sf.description, sf.path))
    return findings


def scan_sentinel_autostart() -> list[Finding]:
    """Detect malicious persistence in shell RC, systemd, XDG autostart."""
    if not _sentinel_available:
        return []
    findings = []
    for af in sentinel.scan_autostart():
        findings.append(Finding("autostart", af.severity, af.description, af.path))
    return findings
```

- [ ] **Step 2: Add suspicious package scanner**

Add after the new wrappers:

```python
# ---------------------------------------------------------------------------
# Suspicious package scanner — typosquat & malicious postinstall
# ---------------------------------------------------------------------------

# Popular Python packages — typosquat targets
_POPULAR_PYTHON = [
    "requests", "django", "flask", "numpy", "pandas", "tensorflow",
    "pytorch", "boto3", "pillow", "cryptography", "paramiko", "sqlalchemy",
    "celery", "redis", "psycopg2", "aiohttp", "fastapi", "pydantic",
    "scrapy", "beautifulsoup4", "selenium", "matplotlib", "scipy",
    "scikit-learn", "httpx", "uvicorn", "gunicorn", "alembic",
    "black", "mypy", "pytest", "setuptools", "pip", "wheel",
    "docker", "kubernetes", "anthropic", "openai", "langchain",
    "transformers", "torch", "pyyaml", "jinja2", "click",
]

# Popular NPM packages — typosquat targets
_POPULAR_NPM = [
    "react", "express", "lodash", "axios", "webpack", "next",
    "vue", "angular", "typescript", "eslint", "prettier", "jest",
    "mocha", "chalk", "commander", "dotenv", "cors", "mongoose",
    "sequelize", "prisma", "socket.io", "tailwindcss", "vite",
    "esbuild", "rollup", "postcss", "sass", "nodemon",
]

# Known malicious packages (hardcoded, extend as needed)
_KNOWN_MALICIOUS_PYTHON = {
    "colourama", "python-binance", "python3-dateutil", "jeIlyfish",
    "python-mongo", "pymongodb", "requesocks", "requesrs",
    "python-ftp", "beautifulsup4", "djanga", "djnago",
    "numppy", "pandaas", "urlib3", "urllib", "flaskk",
}

_KNOWN_MALICIOUS_NPM = {
    "crossenv", "cross-env.js", "d3.js", "fabric-js", "ffmepg",
    "gruntcli", "http-proxy.js", "jquery.js", "mariadb", "mongose",
    "mssql.js", "mssql-node", "mysqljs", "nodecaffe", "nodefabric",
    "nodeffmpeg", "nodemailer-js", "nodemssql", "node-openssl",
    "noderequest", "nodesass", "nodesqlite", "node-tkinter",
    "opencv.js", "openssl.js", "proxy.js", "shadowsock", "smb",
    "sqlite.js", "sqliter", "sqlserver",
}


def _levenshtein(s1: str, s2: str) -> int:
    """Simple Levenshtein distance — no external deps needed."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def scan_suspicious_packages(scan_paths: list[Path]) -> list[Finding]:
    """Detect typosquat packages and malicious postinstall scripts."""
    findings = []

    for path in scan_paths:
        # Python: requirements*.txt, Pipfile, pyproject.toml
        for req_file in path.rglob("requirements*.txt"):
            _check_python_packages(req_file, findings)

        for pyproject in path.rglob("pyproject.toml"):
            _check_pyproject_toml(pyproject, findings)

        # NPM: package.json
        for pkg_file in path.rglob("package.json"):
            _check_npm_packages(pkg_file, findings)

    return findings


def _check_python_packages(req_file: Path, findings: list[Finding]) -> None:
    try:
        content = req_file.read_text()
    except (OSError, UnicodeDecodeError):
        return

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Extract package name (before ==, >=, etc.)
        pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("[")[0].strip().lower()
        if not pkg:
            continue

        if pkg in _KNOWN_MALICIOUS_PYTHON:
            findings.append(Finding(
                "packages", "critical",
                f"Known malicious Python package: {pkg} in {req_file}",
                str(req_file),
            ))
            continue

        # Typosquat check
        for popular in _POPULAR_PYTHON:
            if pkg != popular and _levenshtein(pkg, popular) <= 2 and len(pkg) > 3:
                findings.append(Finding(
                    "packages", "high",
                    f"Possible typosquat: '{pkg}' (similar to '{popular}') in {req_file}",
                    str(req_file),
                ))
                break


def _check_pyproject_toml(pyproject: Path, findings: list[Finding]) -> None:
    try:
        content = pyproject.read_text()
    except (OSError, UnicodeDecodeError):
        return

    in_deps = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and "dependencies" in stripped.lower():
            in_deps = True
            continue
        if stripped.startswith("[") and in_deps:
            in_deps = False
            continue
        if in_deps and "=" in stripped:
            pkg = stripped.split("=")[0].strip().strip('"').strip("'").lower()
            if pkg in _KNOWN_MALICIOUS_PYTHON:
                findings.append(Finding(
                    "packages", "critical",
                    f"Known malicious Python package: {pkg} in {pyproject}",
                    str(pyproject),
                ))


def _check_npm_packages(pkg_file: Path, findings: list[Finding]) -> None:
    try:
        data = _json_loads(pkg_file.read_bytes())
    except (OSError, ValueError):
        return

    # Check postinstall/preinstall scripts
    scripts = data.get("scripts", {})
    for hook in ("postinstall", "preinstall", "prepare"):
        cmd = scripts.get(hook, "")
        cmd_lower = cmd.lower()
        suspicious_cmds = ["curl", "wget", "eval", "exec", "child_process", "http.get", "net.connect"]
        for sus in suspicious_cmds:
            if sus in cmd_lower:
                findings.append(Finding(
                    "packages", "critical",
                    f"Suspicious {hook} script in {pkg_file}: {cmd[:100]}",
                    str(pkg_file),
                ))
                break

    # Check dependency names
    all_deps = {}
    for dep_key in ("dependencies", "devDependencies"):
        all_deps.update(data.get(dep_key, {}))

    for pkg_name in all_deps:
        name_lower = pkg_name.lower()
        if name_lower in _KNOWN_MALICIOUS_NPM:
            findings.append(Finding(
                "packages", "critical",
                f"Known malicious npm package: {pkg_name} in {pkg_file}",
                str(pkg_file),
            ))
            continue

        for popular in _POPULAR_NPM:
            if name_lower != popular and _levenshtein(name_lower, popular) <= 2 and len(name_lower) > 3:
                findings.append(Finding(
                    "packages", "high",
                    f"Possible typosquat: '{pkg_name}' (similar to '{popular}') in {pkg_file}",
                    str(pkg_file),
                ))
                break
```

- [ ] **Step 3: Update imports in scanners.py**

No new imports needed — everything uses existing `Finding`, `Path`, `_json_loads`.

- [ ] **Step 4: Commit**

```bash
git add plugins/security_scan/scanners.py
git commit -m "feat(security): add Python wrappers for secrets/autostart + suspicious package scanner"
```

---

### Task 7: Wire new scanners in plugin.py

**Files:**
- Modify: `plugins/security_scan/plugin.py`

- [ ] **Step 1: Update imports**

Replace the imports block (lines 11-22) with:

```python
from plugins.security_scan.scanners import (
    scan_docker_security,
    scan_env_in_git,
    scan_exposed_ports,
    scan_pip_audit,
    scan_npm_audit,
    scan_sentinel_processes,
    scan_sentinel_network,
    scan_sentinel_filesystem,
    scan_sentinel_cron,
    scan_sentinel_secrets,
    scan_sentinel_autostart,
    scan_suspicious_packages,
    Finding,
)
```

- [ ] **Step 2: Add new scanner calls in `collect()`**

Add these lines in the `collect()` method, after the existing sentinel scanner calls (after line 95):

```python
        # New scanners
        all_findings.extend(scan_sentinel_secrets(self._scan_paths))
        all_findings.extend(scan_sentinel_autostart())
        all_findings.extend(scan_suspicious_packages(self._scan_paths))
```

- [ ] **Step 3: Commit**

```bash
git add plugins/security_scan/plugin.py
git commit -m "feat(security): wire secrets, autostart, package scanners into plugin"
```

---

### Task 8: Coursera links + new explanations in security_explanations.py

**Files:**
- Modify: `gui/security_explanations.py`

- [ ] **Step 1: Add COURSERA_LINKS dict and new explanation entries**

Add after the `from claude_nagger.i18n import get_language` import (line 14):

```python
# === Coursera education links (free courses) ===
COURSERA_LINKS: dict[str, dict[str, str]] = {
    "secrets": {
        "url": "https://www.coursera.org/learn/packt-fundamentals-of-secure-software-dqsu3",
        "title": "Fundamentals of Secure Software",
    },
    "malware": {
        "url": "https://www.coursera.org/professional-certificates/google-cybersecurity",
        "title": "Google Cybersecurity Professional Certificate",
    },
    "cybersecurity_intro": {
        "url": "https://www.coursera.org/learn/cybersecurity-for-everyone",
        "title": "Cybersecurity for Everyone",
    },
    "python": {
        "url": "https://www.coursera.org/learn/python",
        "title": "Programming for Everybody (Python)",
    },
    "frontend": {
        "url": "https://www.coursera.org/learn/developing-frontend-apps-with-react",
        "title": "Developing Front-End Apps with React",
    },
    "ai_agents": {
        "url": "https://www.coursera.org/specializations/ai-agents",
        "title": "AI Agent Developer Specialization",
    },
    "linux_security": {
        "url": "https://www.coursera.org/learn/securing-linux-systems",
        "title": "Securing Linux Systems",
    },
    "docker": {
        "url": "https://www.coursera.org/learn/docker-basics-for-devops",
        "title": "Docker Basics for DevOps",
    },
    "network": {
        "url": "https://www.coursera.org/learn/crypto",
        "title": "Cryptography I (Stanford)",
    },
    "llm_security": {
        "url": "https://www.coursera.org/learn/generative-ai-llm-security",
        "title": "Generative AI and LLM Security",
    },
    "supply_chain": {
        "url": "https://www.coursera.org/courses?query=application%20security",
        "title": "Application Security Courses",
    },
}

# Maps finding type to Coursera course category
_TYPE_TO_COURSE: dict[str, str] = {
    "secrets": "secrets",
    "autostart": "linux_security",
    "packages": "supply_chain",
    "process": "malware",
    "network": "network",
    "cron": "linux_security",
    "filesystem": "linux_security",
    "docker": "docker",
    "deps": "supply_chain",
    "config": "secrets",
    "system": "cybersecurity_intro",
}
```

- [ ] **Step 2: Add new explanation entries to `_EXPLANATIONS_EN`**

Add before the closing `}` of `_EXPLANATIONS_EN`:

```python
    ("secrets", "api_key"): {
        "what": "A hardcoded API key or token was found in your source code.",
        "risk": "Anyone who reads this file gets access to your API account. Bots scan GitHub for these.",
        "fix": "1. Move secret to .env file\n2. echo '.env' >> .gitignore\n3. Use os.environ.get('KEY_NAME')\n4. ROTATE the exposed key immediately — it's compromised.",
    },
    ("secrets", "private_key"): {
        "what": "A private key (SSH, TLS, etc.) is stored in your code directory.",
        "risk": "Private keys grant server access. If pushed to git, anyone can impersonate your server.",
        "fix": "chmod 600 <key_file>\nmv <key_file> ~/.ssh/ or a vault\nNever commit private keys.",
    },
    ("secrets", "database_url"): {
        "what": "A database connection string with credentials is hardcoded.",
        "risk": "Anyone reading this file can connect to your database and read/modify/delete all data.",
        "fix": "Move to .env:\n  DATABASE_URL=postgres://...\nLoad in code:\n  os.environ['DATABASE_URL']",
    },
    ("autostart", "shell_rc"): {
        "what": "Your shell startup file (.bashrc, .zshrc, etc.) contains a suspicious command.",
        "risk": "This runs EVERY TIME you open a terminal. Malware uses this to survive reboots.",
        "fix": "1. Open the file: nano ~/.bashrc\n2. Find and remove the suspicious line\n3. source ~/.bashrc",
    },
    ("autostart", "systemd_user"): {
        "what": "A systemd user service was created or contains suspicious commands.",
        "risk": "User services auto-start. Malware creates them to persist after reboots.",
        "fix": "systemctl --user stop <service>\nsystemctl --user disable <service>\nrm ~/.config/systemd/user/<service>",
    },
    ("autostart", "xdg_autostart"): {
        "what": "A desktop autostart entry contains suspicious commands or is hidden.",
        "risk": "Runs on every GUI login. Hidden entries (NoDisplay=true) are trying to avoid detection.",
        "fix": "rm ~/.config/autostart/<file>.desktop\nCheck: ls -la ~/.config/autostart/",
    },
    ("packages", "typosquat"): {
        "what": "A package name is suspiciously similar to a popular package — possible typosquatting.",
        "risk": "Typosquat packages contain malware. 'requesrs' instead of 'requests' = data theft.",
        "fix": "1. Check the package name carefully\n2. pip show <package> — verify author and homepage\n3. If malicious: pip uninstall <package>",
    },
    ("packages", "malicious"): {
        "what": "This package is on the known-malicious list. It was published to steal data.",
        "risk": "CRITICAL: This package may have already exfiltrated data, credentials, or SSH keys.",
        "fix": "IMMEDIATELY:\n1. pip uninstall <package> / npm uninstall <package>\n2. Rotate ALL credentials\n3. Check ~/.ssh, ~/.aws, ~/.env for exfiltration signs",
    },
    ("packages", "postinstall"): {
        "what": "A package.json has a postinstall/preinstall script with suspicious commands.",
        "risk": "Runs automatically when you npm install. Can download and execute malware.",
        "fix": "1. Check scripts section in package.json\n2. Remove suspicious postinstall/preinstall\n3. npm install --ignore-scripts (safe mode)",
    },
    ("process", "tunnel"): {
        "what": "A tunneling tool is running — it exposes your local services to the internet.",
        "risk": "ngrok/chisel/cloudflared can expose your dev server, databases, or admin panels to anyone.",
        "fix": "kill -9 <PID>\nIf intentional, restrict access with authentication.",
    },
    ("process", "bruteforce"): {
        "what": "A password cracking/brute force tool is running on your machine.",
        "risk": "If you didn't start this, someone may be using your machine for attacks.",
        "fix": "kill -9 <PID>\nCheck who started it: ps aux | grep <PID>\ncrontab -l",
    },
    ("process", "masquerading"): {
        "what": "Process name doesn't match its binary — it's pretending to be something else.",
        "risk": "Malware renames itself to look like system processes to avoid detection.",
        "fix": "ls -la /proc/<PID>/exe\nkill -9 <PID>\nCheck startup: crontab -l && systemctl list-timers",
    },
    ("process", "temp_exec"): {
        "what": "A process is running from /tmp or /dev/shm — legitimate programs don't do this.",
        "risk": "Malware drops payloads in temp directories because they're writable by everyone.",
        "fix": "kill -9 <PID>\nrm /tmp/<binary>\nCheck persistence: crontab -l",
    },
```

- [ ] **Step 3: Add same entries to `_EXPLANATIONS_UA`**

Add before the closing `}` of `_EXPLANATIONS_UA`:

```python
    ("secrets", "api_key"): {
        "what": "В коді знайдено захардкоджений API ключ або токен.",
        "risk": "Хто прочитає файл — отримає доступ до вашого API акаунту. Боти сканують GitHub на такі ключі.",
        "fix": "1. Перенесіть секрет в .env файл\n2. echo '.env' >> .gitignore\n3. Використовуйте os.environ.get('KEY_NAME')\n4. РОТУЙТЕ ключ — він вже скомпрометований.",
    },
    ("secrets", "private_key"): {
        "what": "Приватний ключ (SSH, TLS тощо) лежить у директорії з кодом.",
        "risk": "Приватні ключі дають доступ до серверів. Якщо в git — хто завгодно зайде на ваш сервер.",
        "fix": "chmod 600 <key_file>\nmv <key_file> ~/.ssh/ або vault\nНіколи не комітьте приватні ключі.",
    },
    ("secrets", "database_url"): {
        "what": "URL бази даних з логіном/паролем захардкоджений у коді.",
        "risk": "Хто прочитає файл — може підключитися до БД і прочитати/змінити/видалити всі дані.",
        "fix": "Перенесіть в .env:\n  DATABASE_URL=postgres://...\nВ коді:\n  os.environ['DATABASE_URL']",
    },
    ("autostart", "shell_rc"): {
        "what": "У файлі автозапуску оболонки (.bashrc, .zshrc) знайдено підозрілу команду.",
        "risk": "Виконується КОЖНОГО РАЗУ при відкритті термінала. Малварь так переживає перезавантаження.",
        "fix": "1. Відкрийте файл: nano ~/.bashrc\n2. Знайдіть і видаліть підозрілий рядок\n3. source ~/.bashrc",
    },
    ("autostart", "systemd_user"): {
        "what": "Створено systemd user service з підозрілими командами.",
        "risk": "User-сервіси стартують автоматично. Малварь створює їх для persistence.",
        "fix": "systemctl --user stop <service>\nsystemctl --user disable <service>\nrm ~/.config/systemd/user/<service>",
    },
    ("autostart", "xdg_autostart"): {
        "what": "Запис автозапуску десктопу містить підозрілі команди або прихований.",
        "risk": "Запускається при кожному вході в GUI. Hidden=true — намагається сховатися.",
        "fix": "rm ~/.config/autostart/<file>.desktop\nПеревірте: ls -la ~/.config/autostart/",
    },
    ("packages", "typosquat"): {
        "what": "Ім'я пакету підозріло схоже на популярний — можливий typosquatting.",
        "risk": "Typosquat пакети містять малварь. 'requesrs' замість 'requests' = крадіжка даних.",
        "fix": "1. Перевірте назву пакету уважно\n2. pip show <package> — перевірте автора\n3. Якщо малварь: pip uninstall <package>",
    },
    ("packages", "malicious"): {
        "what": "Цей пакет у списку відомо шкідливих. Він створений для крадіжки даних.",
        "risk": "КРИТИЧНО: Пакет міг вже вкрасти облікові дані, SSH ключі або змінні оточення.",
        "fix": "НЕГАЙНО:\n1. pip uninstall <package> / npm uninstall <package>\n2. Ротуйте ВСІ облікові дані\n3. Перевірте ~/.ssh, ~/.aws, ~/.env",
    },
    ("packages", "postinstall"): {
        "what": "package.json має postinstall/preinstall скрипт з підозрілими командами.",
        "risk": "Виконується автоматично при npm install. Може завантажити і запустити малварь.",
        "fix": "1. Перевірте секцію scripts в package.json\n2. Видаліть підозрілі скрипти\n3. npm install --ignore-scripts (безпечний режим)",
    },
    ("process", "tunnel"): {
        "what": "Працює тунелювання — ваші локальні сервіси стають доступними з інтернету.",
        "risk": "ngrok/chisel/cloudflared можуть відкрити вашу БД, dev-сервер або адмінку для всіх.",
        "fix": "kill -9 <PID>\nЯкщо навмисно — обмежте доступ автентифікацією.",
    },
    ("process", "bruteforce"): {
        "what": "На машині працює інструмент підбору паролів / brute force.",
        "risk": "Якщо не ви запустили — хтось використовує вашу машину для атак.",
        "fix": "kill -9 <PID>\nХто запустив: ps aux | grep <PID>\ncrontab -l",
    },
    ("process", "masquerading"): {
        "what": "Ім'я процесу не відповідає бінарнику — прикидається іншою програмою.",
        "risk": "Малварь перейменовується під системні процеси щоб уникнути виявлення.",
        "fix": "ls -la /proc/<PID>/exe\nkill -9 <PID>\nПеревірте: crontab -l && systemctl list-timers",
    },
    ("process", "temp_exec"): {
        "what": "Процес запущений з /tmp або /dev/shm — легітимні програми так не роблять.",
        "risk": "Малварь кидає payload-и в temp директорії, бо туди може писати будь-хто.",
        "fix": "kill -9 <PID>\nrm /tmp/<binary>\nПеревірте persistence: crontab -l",
    },
```

- [ ] **Step 4: Add new regex patterns to `_PATTERNS` list**

Add before the `]` closing `_PATTERNS`:

```python
    # Secrets
    (re.compile(r"AWS Access Key|AWS Secret", re.I), ("secrets", "api_key")),
    (re.compile(r"GitHub Token|ghp_|gho_|github_pat_", re.I), ("secrets", "api_key")),
    (re.compile(r"OpenAI API Key|sk-[A-Za-z0-9]", re.I), ("secrets", "api_key")),
    (re.compile(r"Anthropic API Key|sk-ant-", re.I), ("secrets", "api_key")),
    (re.compile(r"Stripe.*Key|sk_live_|pk_live_", re.I), ("secrets", "api_key")),
    (re.compile(r"Slack Token|xox[bpors]-", re.I), ("secrets", "api_key")),
    (re.compile(r"Google API Key|AIza", re.I), ("secrets", "api_key")),
    (re.compile(r"Telegram Bot Token", re.I), ("secrets", "api_key")),
    (re.compile(r"Hardcoded secret|Bearer Token|generic_secret", re.I), ("secrets", "api_key")),
    (re.compile(r"Private Key|PRIVATE KEY", re.I), ("secrets", "private_key")),
    (re.compile(r"Database URL with credentials|postgres://|mysql://|mongodb://", re.I), ("secrets", "database_url")),
    # Autostart
    (re.compile(r"autostart.*shell_rc|\.bashrc|\.zshrc|\.profile.*suspicious", re.I), ("autostart", "shell_rc")),
    (re.compile(r"systemd user service|\.service.*suspicious", re.I), ("autostart", "systemd_user")),
    (re.compile(r"autostart.*desktop|XDG|Hidden.*NoDisplay", re.I), ("autostart", "xdg_autostart")),
    (re.compile(r"Suspicious PATH addition", re.I), ("autostart", "shell_rc")),
    (re.compile(r"Pipe-to-shell in autostart|Remote eval in autostart", re.I), ("autostart", "shell_rc")),
    # Packages
    (re.compile(r"typosquat|similar to '", re.I), ("packages", "typosquat")),
    (re.compile(r"Known malicious.*package", re.I), ("packages", "malicious")),
    (re.compile(r"postinstall|preinstall.*script.*suspicious", re.I), ("packages", "postinstall")),
    # Extended process
    (re.compile(r"[Tt]unnel.*detected|ngrok|chisel|cloudflare", re.I), ("process", "tunnel")),
    (re.compile(r"brute force|hydra|hashcat|john.*ripper|medusa", re.I), ("process", "bruteforce")),
    (re.compile(r"masquerad|name.*doesn't match|pretending", re.I), ("process", "masquerading")),
    (re.compile(r"running from temp|/tmp.*process|/dev/shm.*process", re.I), ("process", "temp_exec")),
    (re.compile(r"[Pp]ort scanner|nmap|masscan", re.I), ("process", "bruteforce")),
    (re.compile(r"SQL injection|sqlmap", re.I), ("process", "bruteforce")),
    (re.compile(r"Metasploit.*framework|msfconsole|msfvenom", re.I), ("process", "bruteforce")),
```

- [ ] **Step 5: Add `get_course_link()` function**

Add at the end of the file, after `get_human_description()`:

```python
def get_course_link(finding_type: str, description: str) -> dict[str, str] | None:
    """Return Coursera course info for a finding, or None."""
    # First try to match by finding type
    course_key = _TYPE_TO_COURSE.get(finding_type)
    if course_key and course_key in COURSERA_LINKS:
        return COURSERA_LINKS[course_key]
    return None
```

- [ ] **Step 6: Add new human description patterns to `_HUMAN_EN`**

Add before the `]` closing `_HUMAN_EN`:

```python
    # Secrets
    (re.compile(r"AWS Access Key ID found in (.+)"), r"AWS КЛЮЧ захардкоджений у \1 — РОТУЙТЕ НЕГАЙНО!"),
    (re.compile(r"AWS Secret Access Key found in (.+)"), r"AWS SECRET KEY у \1 — РОТУЙТЕ!"),
    (re.compile(r"GitHub Token found in (.+)"), r"GitHub TOKEN у \1 — ротуйте на github.com/settings/tokens!"),
    (re.compile(r"OpenAI API Key found in (.+)"), r"OpenAI КЛЮЧ у \1 — хтось AI-шить за ваш рахунок!"),
    (re.compile(r"Anthropic API Key found in (.+)"), r"Anthropic КЛЮЧ у \1 — ротуйте на console.anthropic.com!"),
    (re.compile(r"Stripe API Key found in (.+)"), r"Stripe КЛЮЧ у \1 — можуть вкрасти гроші!"),
    (re.compile(r"Hardcoded secret found in (.+)"), r"СЕКРЕТ захардкоджений у \1 — перенесіть в .env!"),
    (re.compile(r"Database URL with credentials found in (.+)"), r"ПАРОЛЬ ДО БД у \1 — перенесіть в .env!"),
    (re.compile(r"Private Key found in (.+)"), r"ПРИВАТНИЙ КЛЮЧ у \1 — не комітьте в git!"),
    (re.compile(r"Google API Key found in (.+)"), r"Google API KEY у \1 — ротуйте!"),
    (re.compile(r"Telegram Bot Token found in (.+)"), r"Telegram BOT TOKEN у \1 — ротуйте через @BotFather!"),
    (re.compile(r"Slack Token found in (.+)"), r"Slack TOKEN у \1 — ротуйте в api.slack.com!"),
    # Autostart
    (re.compile(r"Pipe-to-shell in autostart: (.+)"), r"CURL|BASH В АВТОЗАПУСКУ: \1 — WTF!"),
    (re.compile(r"Remote eval in autostart: (.+)"), r"EVAL В АВТОЗАПУСКУ: \1 — видаліть негайно!"),
    (re.compile(r"Cryptominer in autostart: (.+)"), r"МАЙНЕР В АВТОЗАПУСКУ: \1 — видаліть!"),
    (re.compile(r"Suspicious PATH addition.*: (.+)"), r"ПІДОЗРІЛИЙ PATH: \1 — можливий хіджак"),
    (re.compile(r"Recently created systemd user service: (.+)"), r"НОВИЙ systemd сервіс: \1 — перевірте!"),
    (re.compile(r"Hidden autostart entry '(.+)'.*: (.+)"), r"ПРИХОВАНИЙ автозапуск '\1': \2 — підозріло!"),
    (re.compile(r"Autostart '(.+)' runs from temp.*: (.+)"), r"АВТОЗАПУСК З /tmp '\1': \2 — малварь!"),
    # Packages
    (re.compile(r"Known malicious Python package: (.+) in (.+)"), r"ШКІДЛИВИЙ ПАКЕТ: \1 у \2 — ВИДАЛІТЬ НЕГАЙНО!"),
    (re.compile(r"Known malicious npm package: (.+) in (.+)"), r"ШКІДЛИВИЙ NPM ПАКЕТ: \1 у \2 — ВИДАЛІТЬ!"),
    (re.compile(r"Possible typosquat: '(.+)' \(similar to '(.+)'\) in (.+)"), r"TYPOSQUAT? '\1' (схоже на '\2') у \3 — перевірте!"),
    (re.compile(r"Suspicious (.+) script in (.+): (.+)"), r"ПІДОЗРІЛИЙ \1 скрипт у \2: \3"),
    # Extended process
    (re.compile(r"Tunneling tool detected: (.+)"), r"ТУНЕЛЬ: \1 — ваші сервіси відкриті в інтернет!"),
    (re.compile(r"Tunnel/expose tool detected: (.+)"), r"NGROK/ТУНЕЛЬ: \1 — локальні сервіси в інтернеті!"),
    (re.compile(r"Password brute force tool: (.+)"), r"БРУТФОРС: \1 — хтось ламає паролі!"),
    (re.compile(r"Password cracker.*: (.+)"), r"КРЕКЕР ПАРОЛІВ: \1 — перевірте хто запустив!"),
    (re.compile(r"SQL injection tool: (.+)"), r"SQL INJECTION TOOL: \1 — активна атака!"),
    (re.compile(r"Metasploit framework: (.+)"), r"METASPLOIT: \1 — хакерський фреймворк!"),
    (re.compile(r"Process masquerading.*name='(.+)' but binary='(.+)'.*PID (\d+)"), r"МАСКУВАННЯ: '\1' насправді '\2' (PID \3)!"),
    (re.compile(r"Process '(.+)'.*running from temp directory: (.+)"), r"ПРОЦЕС З TEMP: '\1' запущений з \2 — малварь!"),
    (re.compile(r"Unknown process '(.+)'.*using (.+)% CPU.*PID (\d+)"), r"НЕВІДОМИЙ процес '\1' жере \2% CPU (PID \3) — перевірте!"),
```

- [ ] **Step 7: Commit**

```bash
git add gui/security_explanations.py
git commit -m "feat(gui): add Coursera education links + explanations for all new scanner types"
```

---

### Task 9: Critical Alert Dialog + education link in detail panel

**Files:**
- Modify: `gui/pages/security.py`

- [ ] **Step 1: Add imports**

Add to the imports section (after line 9):

```python
from PyQt5.QtWidgets import QDialog, QDialogButtonBox
from gui.security_explanations import get_course_link
```

- [ ] **Step 2: Add CriticalAlertDialog class**

Add after the `SEVERITY_COLORS` dict (after line 20):

```python
class CriticalAlertDialog(QDialog):
    """Blocking modal dialog for CRITICAL findings — Hasselhoff is NOT happy."""

    # Track shown finding descriptions to avoid repeats
    _shown_findings: set[str] = set()

    def __init__(self, finding: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚨 " + _t("hasselhoff_angry"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.setModal(True)
        self.setStyleSheet("""
            QDialog {
                background: #1a0000;
                border: 3px solid #cc0000;
            }
            QLabel {
                color: #ffffff;
                font-size: 13px;
            }
        """)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel("🚨 " + _t("hasselhoff_angry").upper() + " 🚨")
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #ff0000; padding: 10px;")
        layout.addWidget(header)

        # Finding detail
        desc = finding.get("description", "")
        detail = QLabel(desc)
        detail.setWordWrap(True)
        detail.setStyleSheet("font-size: 14px; color: #ffcc00; padding: 8px; background: #2a0000; border: 1px solid #550000;")
        layout.addWidget(detail)

        # Fart
        fart = QLabel("💨 *ПРРРРТ* 💨")
        fart.setAlignment(Qt.AlignCenter)
        fart.setStyleSheet("font-size: 18px; padding: 8px;")
        layout.addWidget(fart)

        # Explanation
        from gui.security_explanations import get_explanation
        explanation = get_explanation(finding.get("type", ""), desc)

        what_header = QLabel("ЩО ЦЕ:")
        what_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #ff8c00; padding-top: 8px;")
        layout.addWidget(what_header)
        what_text = QLabel(explanation["what"])
        what_text.setWordWrap(True)
        what_text.setStyleSheet("padding: 4px 8px;")
        layout.addWidget(what_text)

        risk_header = QLabel("ЧОМУ ЦЕ ПОГАНО:")
        risk_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #ff0000; padding-top: 8px;")
        layout.addWidget(risk_header)
        risk_text = QLabel(explanation["risk"])
        risk_text.setWordWrap(True)
        risk_text.setStyleSheet("padding: 4px 8px; color: #ff6666;")
        layout.addWidget(risk_text)

        fix_header = QLabel("ЯК ФІКСИТИ:")
        fix_header.setStyleSheet("font-weight: bold; font-size: 14px; color: #00ff00; padding-top: 8px;")
        layout.addWidget(fix_header)
        fix_text = QTextEdit(explanation["fix"])
        fix_text.setReadOnly(True)
        fix_text.setMaximumHeight(80)
        fix_text.setStyleSheet("background: #0a0a1e; color: #00ff00; font-family: 'Courier New'; font-size: 12px; border: 1px solid #004400;")
        layout.addWidget(fix_text)

        # Coursera link
        course = get_course_link(finding.get("type", ""), desc)
        if course:
            course_label = QLabel(
                f'📚 <a href="{course["url"]}" style="color: #66ccff;">'
                f'{_t("learn_more")}: {course["title"]}</a>'
            )
            course_label.setOpenExternalLinks(True)
            course_label.setStyleSheet("padding: 8px; font-size: 13px;")
            layout.addWidget(course_label)

        # Button
        btn = QPushButton(_t("understood"))
        btn.setStyleSheet(
            "font-size: 14px; font-weight: bold; padding: 10px 30px; "
            "background: #cc0000; color: white; border: 2px outset #ff0000;"
        )
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignCenter)

    @classmethod
    def show_if_new(cls, finding: dict, parent=None) -> bool:
        """Show dialog only if this finding hasn't been shown before. Returns True if shown."""
        key = finding.get("description", "")
        if key in cls._shown_findings:
            return False
        cls._shown_findings.add(key)
        dialog = cls(finding, parent)
        dialog.exec_()
        return True
```

- [ ] **Step 3: Add Coursera link to detail panel**

In the `SecurityPage.__init__()` method, add after `self.detail_fix` widget (after line 88):

```python
        self.detail_course = QLabel("")
        self.detail_course.setOpenExternalLinks(True)
        self.detail_course.setStyleSheet("padding: 4px; font-size: 12px;")
        self.detail_course.hide()
```

And add to `detail_layout` after the fix widget (after line 95):

```python
        detail_layout.addWidget(QLabel("📚 " + _t("learn_more_label")))
        detail_layout.addWidget(self.detail_course)
```

- [ ] **Step 4: Update `_on_row_selected` to show course link**

Replace the `_on_row_selected` method (lines 147-156):

```python
    def _on_row_selected(self, row, _col, _prev_row, _prev_col):
        if row < 0 or row >= len(self._findings):
            self.detail_panel.hide()
            return
        finding = self._findings[row]
        explanation = get_explanation(finding.get("type", ""), finding.get("description", ""))
        self.detail_what.setText(explanation["what"])
        self.detail_risk.setText(explanation["risk"])
        self.detail_fix.setPlainText(explanation["fix"])

        course = get_course_link(finding.get("type", ""), finding.get("description", ""))
        if course:
            self.detail_course.setText(
                f'<a href="{course["url"]}" style="color: #4488ff;">{course["title"]}</a>'
            )
            self.detail_course.show()
        else:
            self.detail_course.hide()

        self.detail_panel.show()
```

- [ ] **Step 5: Add method to trigger critical dialogs from update_data**

Add at the end of the `update_data()` method (after line 145):

```python
        # Show blocking dialogs for new CRITICAL findings
        for f in findings:
            if f.get("severity") == "critical":
                CriticalAlertDialog.show_if_new(f, self)
```

- [ ] **Step 6: Commit**

```bash
git add gui/pages/security.py
git commit -m "feat(gui): add CriticalAlertDialog with Hasselhoff + fart + Coursera links"
```

---

### Task 10: i18n strings

**Files:**
- Modify: `claude_nagger/i18n/en.py`
- Modify: `claude_nagger/i18n/ua.py`

- [ ] **Step 1: Add new strings to en.py**

Add to the STRINGS dict:

```python
    # Security Guardian
    "hasselhoff_angry": "Hasselhoff is NOT happy!",
    "understood": "Got it, I'll fix it",
    "learn_more": "Learn more (free course)",
    "learn_more_label": "Learn more:",
    "scanning": "Scanning...",
    "critical_found": "CRITICAL issue found!",
```

- [ ] **Step 2: Add Ukrainian translations to ua.py**

Add to the STRINGS dict:

```python
    # Security Guardian
    "hasselhoff_angry": "Хассельхоф ДУЖЕ незадоволений!",
    "understood": "Зрозумів, піду фіксити",
    "learn_more": "Вивчити (безкоштовний курс)",
    "learn_more_label": "Вивчити:",
    "scanning": "Сканування...",
    "critical_found": "Знайдено КРИТИЧНУ проблему!",
```

- [ ] **Step 3: Commit**

```bash
git add claude_nagger/i18n/en.py claude_nagger/i18n/ua.py
git commit -m "feat(i18n): add Security Guardian strings — EN + UA"
```

---

### Task 11: Build and smoke test

**Files:** None (verification only)

- [ ] **Step 1: Build Rust sentinel**

Run: `cd /home/dchuprina/claude-monitor/crates/sentinel && cargo build --release`
Expected: Compiles successfully

- [ ] **Step 2: Install sentinel into Python env**

Run: `cd /home/dchuprina/claude-monitor && pip install -e . 2>/dev/null; cd crates/sentinel && maturin develop --release 2>/dev/null || cargo build --release`
Expected: Module available or .so built

- [ ] **Step 3: Quick Python import test**

Run:
```bash
cd /home/dchuprina/claude-monitor && python3 -c "
try:
    import sentinel
    print('sentinel imported OK')
    print('scan_secrets:', hasattr(sentinel, 'scan_secrets'))
    print('scan_autostart:', hasattr(sentinel, 'scan_autostart'))
    print('SecretFinding:', hasattr(sentinel, 'SecretFinding'))
    print('AutostartFinding:', hasattr(sentinel, 'AutostartFinding'))
except ImportError as e:
    print(f'sentinel not importable: {e}')
"
```
Expected: All attributes available

- [ ] **Step 4: Test scanners.py imports**

Run:
```bash
cd /home/dchuprina/claude-monitor && python3 -c "
from plugins.security_scan.scanners import (
    scan_sentinel_secrets, scan_sentinel_autostart, scan_suspicious_packages
)
print('All new scanners importable')
"
```
Expected: No import errors

- [ ] **Step 5: Test GUI imports**

Run:
```bash
cd /home/dchuprina/claude-monitor && python3 -c "
from gui.pages.security import CriticalAlertDialog, SecurityPage
from gui.security_explanations import get_course_link, COURSERA_LINKS
print(f'CriticalAlertDialog: OK')
print(f'Coursera links: {len(COURSERA_LINKS)} courses')
print('get_course_link(\"secrets\", \"test\"):', get_course_link('secrets', 'test'))
"
```
Expected: All imports work, 11 courses loaded

- [ ] **Step 6: Commit all remaining changes (if any)**

```bash
git add -A
git commit -m "feat: Security Guardian for Vibe Coders — complete implementation"
```
