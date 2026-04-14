# Phase 4: Security Scanner Expansion (Rust/C)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the Rust sentinel crate with new scanners (container escape, supply chain, git hooks, env leak detection), add a C-based fast filesystem scanner, add Quick Fix buttons to the Security GUI tab, and add a Security Score widget.

**Architecture:** Extend `crates/sentinel/` with new Rust modules. New C library `crates/fscan/` for fast filesystem traversal. Python bindings via PyO3 (Rust) and ctypes (C). Security GUI gets "Fix" buttons per finding type.

**Tech Stack:** Rust (PyO3, sysinfo, regex, rayon), C (POSIX nftw/Windows FindFirstFile), Python 3.11+, PyQt5

**Depends on:** Phase 0+1 (platform layer)

---

## File Structure

### New Rust modules:
- `crates/sentinel/src/container_escape.rs` — Docker/container escape detection
- `crates/sentinel/src/supply_chain.rs` — Lock file hash verification
- `crates/sentinel/src/git_hooks.rs` — Git hooks audit
- `crates/sentinel/src/env_leak.rs` — Process environment variable scanning

### New C library:
- `crates/fscan/fscan.h` — Header file
- `crates/fscan/fscan_linux.c` — Linux nftw implementation
- `crates/fscan/fscan_macos.c` — macOS fts implementation
- `crates/fscan/fscan_windows.c` — Windows FindFirstFile implementation
- `crates/fscan/Makefile` — Cross-platform build
- `crates/fscan/fscan.py` — Python ctypes wrapper

### Modified files:
- `crates/sentinel/src/lib.rs` — Register new modules
- `crates/sentinel/Cargo.toml` — New dependencies if needed
- `plugins/security_scan/scanners.py` — Wire new scanners
- `gui/pages/security.py` — Quick Fix buttons, Security Score
- `gui/security_explanations.py` — New finding explanations
- `i18n/en.py` — New strings
- `i18n/ua.py` — New strings

### Test files:
- `tests/test_security_scanners.py` — Extended scanner tests
- `tests/test_fscan.py` — Filesystem scanner tests

---

### Task 1: Container escape detection (Rust)

**Files:**
- Create: `crates/sentinel/src/container_escape.rs`
- Modify: `crates/sentinel/src/lib.rs`

- [ ] **Step 1: Create container_escape.rs**

```rust
//! Container escape detection — /.dockerenv, namespace leaks, CAP_SYS_ADMIN.

use pyo3::prelude::*;

#[pyclass]
#[derive(Clone)]
pub struct ContainerEscapeFinding {
    #[pyo3(get)]
    pub severity: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub evidence: String,
}

#[pyfunction]
pub fn scan_container_escape() -> Vec<ContainerEscapeFinding> {
    let mut findings = Vec::new();

    // Check if we're inside a container
    let in_container = std::path::Path::new("/.dockerenv").exists()
        || std::fs::read_to_string("/proc/1/cgroup")
            .map(|s| s.contains("docker") || s.contains("containerd") || s.contains("kubepods"))
            .unwrap_or(false);

    if !in_container {
        // Host-side checks

        // Check for containers with CAP_SYS_ADMIN
        #[cfg(target_os = "linux")]
        {
            if let Ok(entries) = std::fs::read_dir("/proc") {
                for entry in entries.flatten() {
                    let status_path = entry.path().join("status");
                    if let Ok(content) = std::fs::read_to_string(&status_path) {
                        // Check CapEff for SYS_ADMIN (bit 21)
                        for line in content.lines() {
                            if line.starts_with("CapEff:") {
                                if let Some(hex) = line.split_whitespace().nth(1) {
                                    if let Ok(caps) = u64::from_str_radix(hex.trim(), 16) {
                                        if caps & (1 << 21) != 0 {
                                            // Check if this is a container process
                                            let cgroup_path = entry.path().join("cgroup");
                                            if let Ok(cgroup) = std::fs::read_to_string(&cgroup_path) {
                                                if cgroup.contains("docker") || cgroup.contains("containerd") {
                                                    let pid = entry.file_name().to_string_lossy().to_string();
                                                    let cmdline = std::fs::read_to_string(entry.path().join("cmdline"))
                                                        .unwrap_or_default()
                                                        .replace('\0', " ");
                                                    findings.push(ContainerEscapeFinding {
                                                        severity: "critical".into(),
                                                        description: format!(
                                                            "Container process PID {} has CAP_SYS_ADMIN — potential escape vector: {}",
                                                            pid, cmdline.chars().take(100).collect::<String>()
                                                        ),
                                                        evidence: format!("pid:{} caps:{:#x}", pid, caps),
                                                    });
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
        }

        // Check for docker.sock mounted in containers (via docker inspect)
        // This is handled by the Python Docker scanner already

    } else {
        // Inside container — check for escape possibilities
        findings.push(ContainerEscapeFinding {
            severity: "info".into(),
            description: "Running inside a container — limited host visibility".into(),
            evidence: "/.dockerenv exists".into(),
        });

        // Check if /var/run/docker.sock is accessible
        if std::path::Path::new("/var/run/docker.sock").exists() {
            findings.push(ContainerEscapeFinding {
                severity: "critical".into(),
                description: "Docker socket accessible inside container — full host escape possible".into(),
                evidence: "/var/run/docker.sock".into(),
            });
        }

        // Check if /proc/sysrq-trigger is writable
        #[cfg(target_os = "linux")]
        {
            use std::os::unix::fs::MetadataExt;
            if let Ok(meta) = std::fs::metadata("/proc/sysrq-trigger") {
                if meta.mode() & 0o222 != 0 {
                    findings.push(ContainerEscapeFinding {
                        severity: "high".into(),
                        description: "sysrq-trigger writable — can crash host from container".into(),
                        evidence: "/proc/sysrq-trigger".into(),
                    });
                }
            }
        }
    }

    findings
}
```

- [ ] **Step 2: Register in lib.rs**

Add to `crates/sentinel/src/lib.rs`:
```rust
mod container_escape;

// In the sentinel function:
m.add_class::<container_escape::ContainerEscapeFinding>()?;
m.add_function(wrap_pyfunction!(container_escape::scan_container_escape, m)?)?;
```

- [ ] **Step 3: Build and test**

Run: `cd /home/dchuprina/claude-monitor/crates/sentinel && maturin develop`
Run: `python -c "import sentinel; print(sentinel.scan_container_escape())"`
Expected: Empty list or findings depending on environment

- [ ] **Step 4: Wire into Python scanners**

In `plugins/security_scan/scanners.py`, add:
```python
def scan_container_escape() -> list[Finding]:
    """Detect container escape vectors."""
    if not _sentinel_available:
        return []
    findings = []
    for f in sentinel.scan_container_escape():
        findings.append(Finding("container", f.severity, f.description, f.evidence))
    return findings
```

- [ ] **Step 5: Commit**

```bash
git add crates/sentinel/src/container_escape.rs crates/sentinel/src/lib.rs plugins/security_scan/scanners.py
git commit -m "feat: container escape detection — CAP_SYS_ADMIN, docker.sock, sysrq"
```

---

### Task 2: Supply chain scanner (Rust)

**Files:**
- Create: `crates/sentinel/src/supply_chain.rs`
- Modify: `crates/sentinel/src/lib.rs`

- [ ] **Step 1: Create supply_chain.rs**

```rust
//! Supply chain scanner — verify lock file integrity, detect tampered dependencies.

use pyo3::prelude::*;
use std::path::Path;

#[pyclass]
#[derive(Clone)]
pub struct SupplyChainFinding {
    #[pyo3(get)]
    pub severity: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub path: String,
}

/// Suspicious patterns in lock files that indicate tampering
const SUSPICIOUS_URLS: &[&str] = &[
    "pastebin.com",
    "raw.githubusercontent.com",  // Not always bad, but unusual in lock files
    "bit.ly",
    "tinyurl.com",
    "ngrok.io",
    "serveo.net",
    "localhost:",
    "127.0.0.1",
    "0.0.0.0",
];

const SUSPICIOUS_INSTALL_SCRIPTS: &[&str] = &[
    "curl ",
    "wget ",
    "powershell ",
    "eval(",
    "exec(",
    "child_process",
    "net.connect",
    "/dev/tcp/",
    "base64 -d",
    "base64 --decode",
];

#[pyfunction]
pub fn scan_supply_chain(scan_paths: Vec<String>) -> Vec<SupplyChainFinding> {
    let mut findings = Vec::new();

    for base in &scan_paths {
        let base_path = Path::new(base);
        if !base_path.is_dir() {
            continue;
        }

        // Walk directories (max depth 4)
        scan_dir(base_path, &mut findings, 4);
    }

    findings
}

fn scan_dir(dir: &Path, findings: &mut Vec<SupplyChainFinding>, depth: u32) {
    if depth == 0 {
        return;
    }
    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };

    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();

        // Skip node_modules, .git, __pycache__
        if name == "node_modules" || name == ".git" || name == "__pycache__" || name.starts_with(".") {
            continue;
        }

        if path.is_dir() {
            scan_dir(&path, findings, depth - 1);
            continue;
        }

        // Check lock files
        match name.as_str() {
            "package-lock.json" | "yarn.lock" | "pnpm-lock.yaml" => {
                check_npm_lock(&path, findings);
            }
            "Pipfile.lock" | "poetry.lock" => {
                check_python_lock(&path, findings);
            }
            _ => {}
        }
    }
}

fn check_npm_lock(path: &Path, findings: &mut Vec<SupplyChainFinding>) {
    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(_) => return,
    };

    let path_str = path.to_string_lossy().to_string();

    // Check for suspicious resolved URLs
    for url_pattern in SUSPICIOUS_URLS {
        if content.contains(url_pattern) {
            findings.push(SupplyChainFinding {
                severity: "high".into(),
                description: format!(
                    "Lock file contains suspicious URL pattern '{}' — possible dependency hijack",
                    url_pattern
                ),
                path: path_str.clone(),
            });
        }
    }

    // Check for install scripts with suspicious commands
    for pattern in SUSPICIOUS_INSTALL_SCRIPTS {
        if content.contains(pattern) {
            findings.push(SupplyChainFinding {
                severity: "critical".into(),
                description: format!(
                    "Lock file references suspicious install command '{}' — possible supply chain attack",
                    pattern
                ),
                path: path_str.clone(),
            });
        }
    }

    // Check for HTTP (non-HTTPS) resolved URLs
    if content.contains("\"resolved\": \"http://") {
        findings.push(SupplyChainFinding {
            severity: "high".into(),
            description: "Lock file has HTTP (not HTTPS) resolved URLs — vulnerable to MITM".into(),
            path: path_str,
        });
    }
}

fn check_python_lock(path: &Path, findings: &mut Vec<SupplyChainFinding>) {
    let content = match std::fs::read_to_string(path) {
        Ok(c) => c,
        Err(_) => return,
    };

    let path_str = path.to_string_lossy().to_string();

    for url_pattern in SUSPICIOUS_URLS {
        if content.contains(url_pattern) {
            findings.push(SupplyChainFinding {
                severity: "high".into(),
                description: format!(
                    "Python lock file contains suspicious URL '{}' — check dependency sources",
                    url_pattern
                ),
                path: path_str.clone(),
            });
        }
    }
}
```

- [ ] **Step 2: Register in lib.rs**

Add to `crates/sentinel/src/lib.rs`:
```rust
mod supply_chain;

m.add_class::<supply_chain::SupplyChainFinding>()?;
m.add_function(wrap_pyfunction!(supply_chain::scan_supply_chain, m)?)?;
```

- [ ] **Step 3: Build and test**

Run: `cd /home/dchuprina/claude-monitor/crates/sentinel && maturin develop`
Run: `python -c "import sentinel; print(sentinel.scan_supply_chain(['/home/dchuprina']))"`

- [ ] **Step 4: Wire into Python scanners**

In `plugins/security_scan/scanners.py`:
```python
def scan_supply_chain(scan_paths: list[Path]) -> list[Finding]:
    """Scan lock files for supply chain attack indicators."""
    if not _sentinel_available:
        return []
    path_strs = [str(p) for p in scan_paths]
    findings = []
    for f in sentinel.scan_supply_chain(path_strs):
        findings.append(Finding("packages", f.severity, f.description, f.path))
    return findings
```

- [ ] **Step 5: Commit**

```bash
git add crates/sentinel/src/supply_chain.rs crates/sentinel/src/lib.rs plugins/security_scan/scanners.py
git commit -m "feat: supply chain scanner — lock file integrity, suspicious URLs, HTTP deps"
```

---

### Task 3: Git hooks audit (Rust)

**Files:**
- Create: `crates/sentinel/src/git_hooks.rs`
- Modify: `crates/sentinel/src/lib.rs`

- [ ] **Step 1: Create git_hooks.rs**

```rust
//! Git hooks auditor — detect suspicious scripts in .git/hooks/.

use pyo3::prelude::*;
use std::path::Path;

#[pyclass]
#[derive(Clone)]
pub struct GitHookFinding {
    #[pyo3(get)]
    pub severity: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub path: String,
}

const SUSPICIOUS_COMMANDS: &[&str] = &[
    "curl ", "wget ", "nc ", "ncat ", "netcat ",
    "eval ", "exec(", "base64",
    "/dev/tcp/", "python -c", "python3 -c",
    "powershell", "cmd /c",
    "| sh", "| bash", "| zsh",
    "chmod +x /tmp", "chmod 777",
];

const DANGEROUS_HOOKS: &[&str] = &[
    "pre-commit", "post-commit", "pre-push", "post-checkout",
    "post-merge", "pre-rebase",
];

#[pyfunction]
pub fn scan_git_hooks(scan_paths: Vec<String>) -> Vec<GitHookFinding> {
    let mut findings = Vec::new();

    for base in &scan_paths {
        let base_path = Path::new(base);
        scan_for_git_dirs(base_path, &mut findings, 3);
    }

    findings
}

fn scan_for_git_dirs(dir: &Path, findings: &mut Vec<GitHookFinding>, depth: u32) {
    if depth == 0 {
        return;
    }

    let git_dir = dir.join(".git");
    if git_dir.is_dir() {
        let hooks_dir = git_dir.join("hooks");
        if hooks_dir.is_dir() {
            check_hooks(&hooks_dir, findings, dir);
        }
    }

    let entries = match std::fs::read_dir(dir) {
        Ok(e) => e,
        Err(_) => return,
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if path.is_dir() && !name.starts_with(".") && name != "node_modules" && name != "__pycache__" {
            scan_for_git_dirs(&path, findings, depth - 1);
        }
    }
}

fn check_hooks(hooks_dir: &Path, findings: &mut Vec<GitHookFinding>, project_dir: &Path) {
    let entries = match std::fs::read_dir(hooks_dir) {
        Ok(e) => e,
        Err(_) => return,
    };

    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();

        // Skip .sample files
        if name.ends_with(".sample") {
            continue;
        }

        // Only check dangerous hooks
        if !DANGEROUS_HOOKS.iter().any(|h| name.starts_with(h)) {
            continue;
        }

        let content = match std::fs::read_to_string(&path) {
            Ok(c) => c,
            Err(_) => continue,
        };

        let path_str = path.to_string_lossy().to_string();
        let project = project_dir.file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_default();

        for pattern in SUSPICIOUS_COMMANDS {
            if content.to_lowercase().contains(&pattern.to_lowercase()) {
                findings.push(GitHookFinding {
                    severity: "critical".into(),
                    description: format!(
                        "Git hook '{}' in project '{}' contains suspicious command: {}",
                        name, project, pattern.trim()
                    ),
                    path: path_str.clone(),
                });
                break; // One finding per hook is enough
            }
        }

        // Check if hook downloads and executes
        if (content.contains("curl") || content.contains("wget"))
            && (content.contains("| sh") || content.contains("| bash") || content.contains("exec"))
        {
            findings.push(GitHookFinding {
                severity: "critical".into(),
                description: format!(
                    "Git hook '{}' in project '{}' downloads and executes code — potential backdoor",
                    name, project
                ),
                path: path_str,
            });
        }
    }
}
```

- [ ] **Step 2: Register in lib.rs**

```rust
mod git_hooks;

m.add_class::<git_hooks::GitHookFinding>()?;
m.add_function(wrap_pyfunction!(git_hooks::scan_git_hooks, m)?)?;
```

- [ ] **Step 3: Build, test, wire into Python, commit**

```bash
cd /home/dchuprina/claude-monitor/crates/sentinel && maturin develop
```

Add to `plugins/security_scan/scanners.py`:
```python
def scan_git_hooks(scan_paths: list[Path]) -> list[Finding]:
    """Audit git hooks for suspicious scripts."""
    if not _sentinel_available:
        return []
    path_strs = [str(p) for p in scan_paths]
    findings = []
    for f in sentinel.scan_git_hooks(path_strs):
        findings.append(Finding("config", f.severity, f.description, f.path))
    return findings
```

```bash
git add crates/sentinel/src/git_hooks.rs crates/sentinel/src/lib.rs plugins/security_scan/scanners.py
git commit -m "feat: git hooks auditor — detect curl|sh, suspicious commands in hooks"
```

---

### Task 4: Environment variable leak detection (Rust)

**Files:**
- Create: `crates/sentinel/src/env_leak.rs`
- Modify: `crates/sentinel/src/lib.rs`

- [ ] **Step 1: Create env_leak.rs**

```rust
//! Environment variable leak detection — scan process environ for exposed secrets.

use pyo3::prelude::*;
use regex::Regex;

#[pyclass]
#[derive(Clone)]
pub struct EnvLeakFinding {
    #[pyo3(get)]
    pub severity: String,
    #[pyo3(get)]
    pub description: String,
    #[pyo3(get)]
    pub process: String,
}

lazy_static::lazy_static! {
    static ref SECRET_PATTERNS: Vec<(&'static str, Regex)> = vec![
        ("AWS Access Key", Regex::new(r"AKIA[0-9A-Z]{16}").unwrap()),
        ("GitHub Token", Regex::new(r"gh[pousr]_[A-Za-z0-9_]{36,}").unwrap()),
        ("Anthropic API Key", Regex::new(r"sk-ant-[A-Za-z0-9_-]{40,}").unwrap()),
        ("OpenAI API Key", Regex::new(r"sk-[A-Za-z0-9]{40,}").unwrap()),
        ("Stripe Key", Regex::new(r"[sr]k_live_[A-Za-z0-9]{20,}").unwrap()),
        ("Slack Token", Regex::new(r"xox[bporas]-[A-Za-z0-9-]{10,}").unwrap()),
        ("Database URL with creds", Regex::new(r"(postgres|mysql|mongodb)://[^:]+:[^@]+@").unwrap()),
    ];
}

#[pyfunction]
pub fn scan_env_leaks() -> Vec<EnvLeakFinding> {
    let mut findings = Vec::new();

    #[cfg(target_os = "linux")]
    {
        if let Ok(entries) = std::fs::read_dir("/proc") {
            for entry in entries.flatten() {
                let pid = entry.file_name().to_string_lossy().to_string();
                if !pid.chars().all(|c| c.is_ascii_digit()) {
                    continue;
                }

                let environ_path = entry.path().join("environ");
                let environ = match std::fs::read_to_string(&environ_path) {
                    Ok(e) => e,
                    Err(_) => continue,
                };

                let cmdline = std::fs::read_to_string(entry.path().join("cmdline"))
                    .unwrap_or_default()
                    .replace('\0', " ")
                    .chars().take(80).collect::<String>();

                for (name, pattern) in SECRET_PATTERNS.iter() {
                    if pattern.is_match(&environ) {
                        findings.push(EnvLeakFinding {
                            severity: "high".into(),
                            description: format!(
                                "{} found in environment of PID {} ({})",
                                name, pid, cmdline
                            ),
                            process: format!("pid:{}", pid),
                        });
                        break; // One finding per process
                    }
                }
            }
        }
    }

    #[cfg(target_os = "macos")]
    {
        // macOS: use ps + env reading (limited by SIP)
        // Fallback: check current process environment only
        for (key, value) in std::env::vars() {
            let combined = format!("{}={}", key, value);
            for (name, pattern) in SECRET_PATTERNS.iter() {
                if pattern.is_match(&combined) {
                    findings.push(EnvLeakFinding {
                        severity: "high".into(),
                        description: format!("{} exposed in environment variable {}", name, key),
                        process: "current".into(),
                    });
                    break;
                }
            }
        }
    }

    #[cfg(target_os = "windows")]
    {
        // Windows: check current process environment
        for (key, value) in std::env::vars() {
            let combined = format!("{}={}", key, value);
            for (name, pattern) in SECRET_PATTERNS.iter() {
                if pattern.is_match(&combined) {
                    findings.push(EnvLeakFinding {
                        severity: "high".into(),
                        description: format!("{} exposed in environment variable {}", name, key),
                        process: "current".into(),
                    });
                    break;
                }
            }
        }
    }

    findings
}
```

- [ ] **Step 2: Add lazy_static to Cargo.toml**

In `crates/sentinel/Cargo.toml`, add:
```toml
lazy_static = "1"
```

- [ ] **Step 3: Register, build, wire, commit**

Register in lib.rs, build, add Python wrapper, commit:
```bash
git add crates/sentinel/src/env_leak.rs crates/sentinel/src/lib.rs crates/sentinel/Cargo.toml plugins/security_scan/scanners.py
git commit -m "feat: env leak detection — API keys, tokens, DB creds in process environ"
```

---

### Task 5: Quick Fix buttons in Security tab

**Files:**
- Modify: `gui/pages/security.py`
- Modify: `i18n/en.py`
- Modify: `i18n/ua.py`

- [ ] **Step 1: Add i18n strings**

In `i18n/en.py`:
```python
"fix_button": "Fix",
"fix_confirm_title": "Apply Fix?",
"fix_confirm_msg": "This will run:\n\n{}\n\nContinue?",
"fix_success": "Fix applied successfully!",
"fix_error": "Fix failed: {}",
"no_fix_available": "No automatic fix available — follow manual instructions",
```

In `i18n/ua.py`:
```python
"fix_button": "Виправити",
"fix_confirm_title": "Застосувати виправлення?",
"fix_confirm_msg": "Буде виконано:\n\n{}\n\nПродовжити?",
"fix_success": "Виправлення застосовано!",
"fix_error": "Помилка: {}",
"no_fix_available": "Автоматичне виправлення недоступне — слідуйте інструкціям",
```

- [ ] **Step 2: Define fix recipes per finding type**

In `gui/pages/security.py`, add fix recipe mapping:

```python
from core.platform import get_platform

# Finding type + description keyword → fix command
FIX_RECIPES: dict[str, dict[str, list[str]]] = {
    "config": {
        ".env file committed": ["git", "rm", "--cached", "{source}"],
    },
    "system": {
        "firewall": {
            "linux": ["ufw", "enable"],
            "macos": ["pfctl", "-e"],
            "windows": ["netsh", "advfirewall", "set", "allprofiles", "state", "on"],
        },
        "password auth": "PasswordAuthentication no → /etc/ssh/sshd_config",
        "root login": "PermitRootLogin no → /etc/ssh/sshd_config",
    },
    "docker": {
        "runs as root": "Add USER directive to Dockerfile:\nUSER 1000:1000",
        "latest tag": "Pin image version: e.g., python:3.11-slim instead of python:latest",
    },
}
```

- [ ] **Step 3: Add Fix button to detail panel**

In the Security page's detail panel (shown when clicking a finding), add a "Fix" button:

```python
self.fix_btn = QPushButton(_t("fix_button"))
self.fix_btn.setStyleSheet(
    "background: #000080; color: white; border: 2px outset #4040c0; "
    "padding: 4px 16px; font-weight: bold;"
)
self.fix_btn.clicked.connect(self._apply_fix)
self.fix_btn.setVisible(False)
# Add to detail panel layout
```

- [ ] **Step 4: Implement _apply_fix with confirmation**

```python
def _apply_fix(self):
    """Apply automatic fix for the selected finding."""
    finding = self._selected_finding
    if not finding:
        return

    recipe = self._get_fix_recipe(finding)
    if not recipe:
        QMessageBox.information(self, _t("fix_button"), _t("no_fix_available"))
        return

    if isinstance(recipe, str):
        # Manual instruction, not a command
        QMessageBox.information(self, _t("fix_button"), recipe)
        return

    # Command to run — confirm first (Win95 style)
    from gui.win95_popup import Win95Popup
    cmd_str = " ".join(recipe)
    reply = QMessageBox.question(
        self, _t("fix_confirm_title"),
        _t("fix_confirm_msg").format(cmd_str),
        QMessageBox.Yes | QMessageBox.No,
    )
    if reply != QMessageBox.Yes:
        return

    # Execute
    import subprocess
    platform = get_platform()
    try:
        # Elevate if needed for system commands
        if any(k in cmd_str for k in ("ufw", "pfctl", "netsh", "sshd")):
            recipe = platform.elevate_command(recipe)

        result = subprocess.run(recipe, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            self.status_label.setText(_t("fix_success"))
        else:
            self.status_label.setText(_t("fix_error").format(result.stderr[:100]))
    except Exception as e:
        self.status_label.setText(_t("fix_error").format(str(e)))
```

- [ ] **Step 5: Run tests, commit**

```bash
git add gui/pages/security.py i18n/en.py i18n/ua.py
git commit -m "feat: Quick Fix buttons in Security tab — auto-fix with confirmation"
```

---

### Task 6: Security Score widget

**Files:**
- Modify: `gui/pages/overview.py`
- Modify: `gui/app.py`

- [ ] **Step 1: Add Security Score to Overview**

In `gui/pages/overview.py`, add after infra_group:

```python
# --- Security Score ---
self.security_group = QGroupBox("Security Score")
sec_layout = QHBoxLayout()

self.security_score = QLabel("--")
self.security_score.setStyleSheet(
    "font-size: 36px; font-weight: bold; color: #000080; "
    "border: 2px inset #808080; background: white; padding: 8px; min-width: 80px;"
)
self.security_score.setAlignment(Qt.AlignCenter)
sec_layout.addWidget(self.security_score)

self.security_breakdown = QLabel("")
self.security_breakdown.setWordWrap(True)
self.security_breakdown.setStyleSheet("padding: 4px; font-size: 11px;")
sec_layout.addWidget(self.security_breakdown, stretch=1)

self.security_group.setLayout(sec_layout)
layout.addWidget(self.security_group)
```

Add update method:

```python
def update_security_score(self, findings: list[dict]) -> None:
    """Calculate and display security score 0-100."""
    if not findings:
        self.security_score.setText("100")
        self.security_score.setStyleSheet(
            "font-size: 36px; font-weight: bold; color: #006600; "
            "border: 2px inset #808080; background: white; padding: 8px; min-width: 80px;"
        )
        self.security_breakdown.setText("No issues found")
        return

    # Score calculation: start at 100, deduct per finding
    deductions = {"critical": 20, "high": 10, "medium": 3, "low": 1}
    total_deduction = 0
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low")
        counts[sev] = counts.get(sev, 0) + 1
        total_deduction += deductions.get(sev, 1)

    score = max(0, 100 - total_deduction)
    color = "#006600" if score >= 80 else ("#cc8800" if score >= 50 else "#cc0000")

    self.security_score.setText(str(score))
    self.security_score.setStyleSheet(
        f"font-size: 36px; font-weight: bold; color: {color}; "
        "border: 2px inset #808080; background: white; padding: 8px; min-width: 80px;"
    )

    breakdown_parts = []
    for sev in ("critical", "high", "medium", "low"):
        if counts[sev] > 0:
            breakdown_parts.append(f"{counts[sev]} {sev}")
    self.security_breakdown.setText(" | ".join(breakdown_parts))
```

- [ ] **Step 2: Wire score update from app.py**

In `gui/app.py`, in `_on_scan_done`:
```python
self.page_overview.update_security_score(findings)
```

- [ ] **Step 3: Run tests, commit**

```bash
git add gui/pages/overview.py gui/app.py
git commit -m "feat: Security Score widget on Overview — 0-100 with severity breakdown"
```

---

### Task 7: Wire all new scanners into security scan flow

**Files:**
- Modify: `gui/app.py`

- [ ] **Step 1: Add new scanners to _run_security_scan**

In the `scan()` function inside `_run_security_scan`, add:

```python
from plugins.security_scan.scanners import (
    # ... existing imports ...
    scan_container_escape,
    scan_supply_chain,
    scan_git_hooks,
    scan_env_leaks,
    scan_port_conflicts,
)

# After existing sentinel scanners:
findings.extend(scan_container_escape())
findings.extend(scan_supply_chain(scan_paths))
findings.extend(scan_git_hooks(scan_paths))
findings.extend(scan_env_leaks())
findings.extend(scan_port_conflicts(ports))
```

- [ ] **Step 2: Add Python wrapper for env_leaks**

In `plugins/security_scan/scanners.py`:
```python
def scan_env_leaks() -> list[Finding]:
    """Detect API keys and tokens in process environment variables."""
    if not _sentinel_available:
        return []
    findings = []
    for f in sentinel.scan_env_leaks():
        findings.append(Finding("secrets", f.severity, f.description, f.process))
    return findings
```

- [ ] **Step 3: Run full test suite, commit**

```bash
git add gui/app.py plugins/security_scan/scanners.py
git commit -m "feat: wire all new security scanners — container, supply chain, git hooks, env leaks"
```

---

### Task 8: Final validation

- [ ] **Step 1: Build sentinel**

Run: `cd /home/dchuprina/claude-monitor/crates/sentinel && maturin develop`
Expected: Success

- [ ] **Step 2: Run full test suite**

Run: `cd /home/dchuprina/claude-monitor && python -m pytest tests/ -v --tb=short`
Expected: All PASS

- [ ] **Step 3: Run a security scan manually**

Run: `cd /home/dchuprina/claude-monitor && python -c "
from plugins.security_scan.scanners import *
from pathlib import Path
paths = [Path.home()]
print('Container:', len(scan_container_escape()))
print('Supply chain:', len(scan_supply_chain(paths)))
print('Git hooks:', len(scan_git_hooks(paths)))
print('Env leaks:', len(scan_env_leaks()))
"`
Expected: Numbers printed, no crashes

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: Phase 4 complete — expanded security scanners with Rust"
```
