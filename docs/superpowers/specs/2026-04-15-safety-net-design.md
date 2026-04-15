# Safety Net — Save / Rollback / Pick for Vibe Coders

> "Save before the boss fight. Load when you die. Loot the corpse."

## Problem

Vibe coder works with AI. AI changes 30 files. Half of them break everything. Now what?

- No save point to go back to
- No way to grab the working parts from the broken attempt
- Git exists but vibe coder doesn't know it (or fears it)
- Existing Snapshots track environment (docker, ports, configs) but NOT code

## Solution

New sidebar page "Safety Net" with three actions:

1. **Save** — snapshot all code before risky AI session
2. **Rollback** — return to save point, keep broken attempt in backup
3. **Pick** — grab working files from the broken attempt

Every action comes with a short teaching moment explaining what git did and why. Not a lecture — 1-2 sentences after the button click, when the person is curious.

---

## 1. Save Point

### What happens when user clicks "Save Point":

1. Check if git repo exists. If not — offer `git init` with explanation
2. Run `pre_save_warnings()` — catch .env in git, node_modules without .gitignore
3. `git add .`
4. `git commit -m "Save Point: {label}"`
5. `git tag savepoint-{N}`
6. Save metadata to SQLite

### Pre-save warnings:

- `.env` file tracked by git: "Your .env might have passwords. Add to .gitignore?"
- `node_modules` without .gitignore: "node_modules is 40,000 library files. No need to save them. Add to .gitignore?"
- No git repo: full git init flow with explanation

### UI after save:

```
+- Results -------------------------------------------+
|                                                      |
|  Saved. Save Point #4 "before auth feature"          |
|                                                      |
|  Saved: 23 files, 1,847 lines                       |
|  Branch: main                                        |
|  Commit: a1b2c3d                                     |
|                                                      |
+- What happened -------------------------------------+
|                                                      |
|  Git remembered your code exactly as it is now.      |
|  You can always come back here.                      |
|                                                      |
|  (git commit = save, git tag = bookmark)             |
|                                                      |
+------------------------------------------------------+
```

### Git config missing flow:

If first `git commit` fails with "Please tell me who you are" — show dialog:

```
+- Git needs your name --------------------------------+
|                                                       |
|  First time using git here.                           |
|  It needs a name and email for save history.          |
|  (This is just a label, not a login.)                 |
|                                                       |
|  Name:  [                           ]                 |
|  Email: [                           ]                 |
|                                                       |
|               [ OK ]    [ Cancel ]                    |
|                                                       |
+-------------------------------------------------------+
```

Runs `git config user.name` + `git config user.email` (local, not global).

---

## 2. Rollback

### Confirmation dialog (Win95 MessageBox):

```
+- Rollback -------------------------------------------+
|                                                       |
|  Return to Save Point #4 "before auth feature"?      |
|                                                       |
|  Current changes (12 files) will be saved to a        |
|  separate branch. Nothing will be lost.               |
|                                                       |
|               [ OK ]    [ Cancel ]                    |
|                                                       |
+-------------------------------------------------------+
```

### Under the hood:

1. `git add .` + `git commit -m "backup before rollback to savepoint-4"`
2. `git branch backup/{timestamp}`
3. `git reset --hard savepoint-{N}`
4. Save backup to SQLite

### UI after rollback:

```
+- Results --------------------------------------------+
|                                                       |
|  Done. Code restored to Save Point #4.                |
|                                                       |
|  Your recent changes saved to: backup/2026-04-15...   |
|  Files restored: 23                                   |
|                                                       |
+- What happened --------------------------------------+
|                                                       |
|  Git kept both versions -- the broken one in a        |
|  backup branch, and your save point here. Switched    |
|  you back. Nothing deleted.                           |
|                                                       |
|  (git branch + git reset)                             |
|                                                       |
|  Want to grab working parts from the broken version?  |
|  Use [Pick Changes] below.                            |
|                                                       |
+-------------------------------------------------------+
```

### Edge cases:

- No changes after save point: "Nothing to rollback -- code hasn't changed since Save Point #4"
- Save point on different branch: create backup first, then checkout + reset
- Uncommitted changes: auto-commit into backup before rollback

---

## 3. Pick Changes (Loot)

### File list from backup branch:

Under the hood: `git diff --name-status savepoint-4..backup/2026-04-15-14-35`

```
+- Pick Changes from backup/2026-04-15-14-35 ---------+
|                                                       |
|  These files changed in the broken attempt.           |
|  Pick what works. Leave what doesn't.                 |
|                                                       |
|  [ ] + src/auth.py (NEW, 89 lines)                   |
|      Login form handler                               |
|                                                       |
|  [ ] ~ src/app.py (+45 -12)                          |
|      Added routes                                     |
|                                                       |
|  [ ] ~ requirements.txt (+3)                         |
|      Added flask-login, bcrypt, wtforms               |
|                                                       |
|  [ ] + src/templates/login.html (NEW, 34 lines)      |
|      Login page template                              |
|                                                       |
|  [ ] - src/old_auth.py (DELETED)                     |
|      Was: old auth helper                             |
|                                                       |
|         [ Apply Selected ]    [ Cancel ]              |
|                                                       |
+-------------------------------------------------------+
```

### Under the hood "Apply Selected":

1. For each selected file: `git checkout backup/2026-04-15-14-35 -- src/auth.py`
2. `git add {selected files}`
3. `git commit -m "picked from backup/...: auth.py, login.html"`
4. Update SQLite picked_files

### UI after apply:

```
+- Done -----------------------------------------------+
|                                                       |
|  Grabbed 2 files from the broken attempt:             |
|  + src/auth.py                                        |
|  + src/templates/login.html                           |
|                                                       |
+- What happened --------------------------------------+
|                                                       |
|  Git grabbed files from the broken version and put    |
|  them here. The rest stayed behind.                   |
|                                                       |
|  (git checkout <branch> -- <file>)                    |
|                                                       |
+-------------------------------------------------------+
```

### File explanations:

- From existing `file_explainer.py` (60+ patterns)
- If Haiku connected: `batch_explain` what changed in each file
- Filter: no node_modules, __pycache__, .env — source only
- >50 files: group by directory, "select all in folder"

---

## 4. Teaching Moments

Every action has a "What happened" block. Appears AFTER the action when the person sees the result and is curious.

### Principle:

Explain through analogies, not terms. No "repository", "staging area", "HEAD". Only what the person sees.

### Static hints:

| Moment | Text | Git command |
|--------|------|-------------|
| First Save (no git repo) | Git is a time machine for code. Just turned it on for this project. | git init |
| Save Point created | Git remembered your code exactly as it is now. You can always come back here. | git commit + git tag |
| First save ever | This is your first save point. Now you have a safety net. Before any risky change -- save first, break things later. | git commit + git tag |
| .gitignore created | Told git to ignore junk files. They stay on disk but git won't track them. | .gitignore |
| Rollback | Git kept both versions -- the broken one in a backup branch, and your save point here. Switched you back. Nothing deleted. | git branch + git reset |
| Pick Changes | Git grabbed files from one version and put them into another. Like copy-paste between parallel universes. | git checkout branch -- file |
| Branch explain | A branch is a separate copy of your code. Changes here don't touch the original. Like a draft document. | git branch |

### Format in UI:

```
+- What happened --------------------------------------+
|                                                       |
|  Git remembered your code exactly as it is now.       |
|  You can always come back here.                       |
|                                                       |
|  (git commit + git tag)                               |
|                                                       |
+-------------------------------------------------------+
```

Small line in parentheses — real git command. Not required reading, but when the person sees this command in a terminal later, they'll recognize it.

### Progression:

System remembers (SQLite counter) how many save/rollback/pick actions the person did.

| Actions done | Hint behavior |
|---|---|
| 0-5 | Full hint: text + git_command + detail |
| 6-14 | Short: text only |
| 15+ | Hidden, "?" button to show if needed |

### Haiku enrichment:

If API key set — "What happened" is generated by Haiku with file context. Prompt: "Explain to a non-programmer in 2 sentences what just happened. Context: {action} on {file_count} files including {top_files}. Language: {lang}. No jargon."

Cache by action+context hash.

---

## 5. Page Layout

```
+- Safety Net -----------------------------------------+
|                                                       |
|  Project: /home/user/myapp                            |
|                                                       |
|  +- Save -------------------------------------------+|
|  |                                                   ||
|  |  Label: [before auth feature          ]           ||
|  |                                                   ||
|  |  [ Save Point ]                                   ||
|  |                                                   ||
|  |  23 files tracked | branch: main | clean          ||
|  |                                                   ||
|  +---------------------------------------------------+|
|                                                       |
|  +- Save Points ------------------------------------+|
|  |                                                   ||
|  |  #5  14:30  "before auth feature"    [Rollback]   ||
|  |      main | 23 files | a1b2c3d                    ||
|  |                                                   ||
|  |  #4  11:00  "before docker setup"    [Rollback]   ||
|  |      main | 19 files | d4e5f6a                    ||
|  |                                                   ||
|  |  #3  yesterday  "working baseline"   [Rollback]   ||
|  |      main | 15 files | b7c8d9e                    ||
|  |                                                   ||
|  +---------------------------------------------------+|
|                                                       |
|  +- Backups (from rollbacks) -----------------------+|
|  |                                                   ||
|  |  backup/2026-04-15-14-35  [Pick Changes]          ||
|  |  12 files changed from Save Point #4              ||
|  |                                                   ||
|  +---------------------------------------------------+|
|                                                       |
|  +- What happened ----------------------------------+|
|  |                                                   ||
|  |  (last action result + teaching moment here)      ||
|  |                                                   ||
|  +---------------------------------------------------+|
|                                                       |
+-------------------------------------------------------+
```

### Details:

- **Save group** — always on top, always visible. Label input with placeholder "what are you about to do?". Status line: file count, branch, dirty state ("3 unsaved changes" in yellow if dirty).
- **Save Points list** — reverse chronological. Each row: number, time, label, Rollback button. Second line: branch, file count, short hash. Max 20 visible, older — scroll.
- **Backups list** — appears only after rollback. Shows backup branches created during rollbacks. "Pick Changes" button per backup. Hidden if no backups.
- **What happened** — appears after any action. Replaced by next action's result.

### Button states:

- Save Point disabled if no changes since last save ("Nothing new to save")
- Rollback disabled if current state = this save point
- Pick Changes disabled if backup branch already deleted or merged

### Quick-access on other pages:

- Activity page: "Save Point" button in header next to Refresh
- Snapshots page: "Save Code" button next to "Take Snapshot" (snapshot = environment, save = code)

---

## 6. Hasselhoff Mode

Not main text. Random one-liners, 30% chance after each action. Separate label, italic, gray.

```python
HOFF_SAVE = [
    "The Hoff always saves before the stunt.",
    "Even Knight Rider had a backup plan.",
    "Don't hassle the save point.",
]
HOFF_ROLLBACK = [
    "The Hoff has been here before. Literally.",
    "Time travel. The Hoff invented it. Probably.",
    "Back to safety. The Hoff approves.",
]
HOFF_PICK = [
    "The Hoff doesn't leave good code behind.",
    "Selective rescue. Very Baywatch.",
    "Grab what works, leave the drama.",
]
HOFF_EMPTY = [
    "Even the Hoff takes a day off.",
    "Nothing to save. Suspicious.",
]
```

---

## 7. Architecture

### New files:

```
core/
  safety_net.py          # Save, Rollback, Pick logic
  git_educator.py        # Teaching moments + hint progression

gui/pages/
  safety_net_page.py     # UI page

i18n/
  en.py                  # ~40 new strings
  ua.py                  # ~40 new strings
```

### Changes to existing files:

- `core/history.py` — 3 new tables, CRUD methods
- `gui/app.py` — register Safety Net in sidebar between Snapshots and Health, add to `_on_project_changed()`
- `gui/pages/activity.py` — "Save Point" button in header
- `gui/pages/snapshots.py` — "Save Code" button in header
- `i18n/en.py`, `i18n/ua.py` — new strings
- `config.toml` — `[safety_net]` section

### SQLite tables:

**save_points:**
```sql
CREATE TABLE save_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    label TEXT NOT NULL,
    project_dir TEXT NOT NULL,
    branch TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    tag_name TEXT NOT NULL,
    file_count INTEGER DEFAULT 0,
    lines_total INTEGER DEFAULT 0,
    hint_level INTEGER DEFAULT 0
)
```

**rollback_backups:**
```sql
CREATE TABLE rollback_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    project_dir TEXT NOT NULL,
    save_point_id INTEGER NOT NULL,
    backup_branch TEXT NOT NULL,
    backup_commit TEXT NOT NULL,
    files_changed INTEGER DEFAULT 0,
    picked_files TEXT DEFAULT '[]',
    FOREIGN KEY (save_point_id) REFERENCES save_points(id)
)
```

**git_education:**
```sql
CREATE TABLE git_education (
    project_dir TEXT PRIMARY KEY,
    saves_count INTEGER DEFAULT 0,
    rollbacks_count INTEGER DEFAULT 0,
    picks_count INTEGER DEFAULT 0,
    gitignore_created INTEGER DEFAULT 0,
    git_initialized INTEGER DEFAULT 0
)
```

### Config:

```toml
[safety_net]
max_save_points = 20
auto_gitignore = true
show_hints = true
```

### Dependencies: none new. Subprocess git + existing SQLite + existing file_explainer + existing HaikuClient.

---

## 8. core/safety_net.py API

```python
class SafetyNet:
    def __init__(self, project_dir: str, db: HistoryDB)

    # -- Save --
    def can_save(self) -> tuple[bool, str]
    def pre_save_warnings(self) -> list[dict]
    def create_save_point(self, label: str) -> SavePointResult
    def get_save_points(self, limit: int = 20) -> list[dict]

    # -- Rollback --
    def can_rollback(self, save_point_id: int) -> tuple[bool, str]
    def rollback_preview(self, save_point_id: int) -> RollbackPreview
    def rollback(self, save_point_id: int) -> RollbackResult

    # -- Pick --
    def list_pickable_files(self, backup_id: int) -> list[PickableFile]
    def pick_files(self, backup_id: int, paths: list[str]) -> PickResult

    # -- Git Init --
    def ensure_git(self) -> bool
    def fix_gitignore(self, issues: list[str]) -> None
    def set_git_user(self, name: str, email: str) -> None
```

**Dataclasses:**

```python
@dataclass
class SavePointResult:
    id: int
    commit_hash: str
    tag_name: str
    file_count: int
    lines_total: int
    warnings_fixed: list[str]

@dataclass
class RollbackPreview:
    files_affected: int
    current_branch: str
    target_commit: str
    target_label: str

@dataclass
class RollbackResult:
    backup_branch: str
    backup_commit: str
    files_restored: int

@dataclass
class PickableFile:
    path: str
    status: str          # "added", "modified", "deleted"
    additions: int
    deletions: int
    explanation: str     # from file_explainer

@dataclass
class PickResult:
    files_applied: list[str]
    commit_hash: str
```

---

## 9. core/git_educator.py API

```python
class GitEducator:
    def __init__(self, project_dir: str, db: HistoryDB, haiku=None)
    def get_hint(self, action: str, context: dict) -> Hint | None
    def bump_counter(self, action: str) -> None
    def should_show_hints(self) -> bool
```

```python
@dataclass
class Hint:
    text: str           # human explanation
    git_command: str     # real git command in parentheses
    detail: str | None   # Haiku-generated context or None
```

---

## 10. Error Handling

| Situation | Behavior |
|---|---|
| git not installed | "Git not found. Install it: (link). Git is needed to save your code." |
| git init fails | "Could not initialize git. Check folder permissions." |
| git add fails (permission) | "Some files can't be saved -- check file permissions." |
| commit fails (no user) | Git config dialog (name + email input) |
| tag exists | Auto-increment: savepoint-5 -> savepoint-6 |
| reset fails (merge in progress) | "Can't rollback -- there's a merge in progress. Finish or cancel it first." |
| backup branch exists | Append suffix: backup/2026-04-15-14-35-2 |
| checkout file fails | "Could not grab {file} -- may have been deleted. Skipping." Per-file, doesn't stop the whole pick |
| SQLite write fails | Log warning, git operation already succeeded -- git data matters more than metadata |
| Disk full | "Disk full. Free some space before saving." (catch OSError) |

---

## 11. Cross-Platform

| Component | Approach |
|---|---|
| git binary | `shutil.which("git")` — works everywhere, same as activity_tracker.py |
| .gitignore | pathlib — cross-platform paths |
| SQLite | stdlib sqlite3 |
| file_explainer | pathlib patterns |
| line counting | Python `sum(1 for _ in open(f))`, no shell commands |

---

## 12. Testing

```
tests/
  test_safety_net.py       # core logic
  test_git_educator.py     # hints + progression
```

**test_safety_net.py:**
- `test_create_save_point` — tmp git repo, save, verify tag + commit + SQLite
- `test_save_no_changes` — can_save() returns False
- `test_save_gitignore_warning` — .env triggers pre_save_warnings
- `test_rollback` — save, change files, rollback, verify files restored + backup branch exists
- `test_rollback_no_changes` — can_rollback() False if state = save point
- `test_pick_files` — save, change 5 files, rollback, pick 2, verify only 2 appeared
- `test_pick_empty` — list_pickable_files on identical backup = []
- `test_ensure_git` — non-git dir, verify git init
- `test_fix_gitignore` — creates .gitignore with correct content
- `test_git_config_missing` — catches "please tell me who you are"
- `test_max_save_points` — after 20, oldest deleted (tag + SQLite)

**test_git_educator.py:**
- `test_hint_first_save` — returns save_first hint
- `test_hint_progression` — after 15 actions should_show_hints() = False
- `test_bump_counter` — counters increment
- `test_haiku_hint` — mock HaikuClient returns contextual hint

All tests use `tmp_path` fixture — isolated git repos, zero side effects.

---

## 13. i18n

~40 new keys EN + UA:

- `safety_title`, `safety_save_label`, `safety_save_btn`, `safety_save_placeholder`
- `safety_status_clean`, `safety_status_dirty`, `safety_status_no_git`
- `safety_rollback_btn`, `safety_rollback_confirm`, `safety_rollback_done`
- `safety_pick_btn`, `safety_pick_title`, `safety_pick_apply`, `safety_pick_done`
- `safety_hint_*` — all teaching moments EN + UA
- `safety_warn_env`, `safety_warn_node_modules`, `safety_warn_no_changes`
- `safety_git_init_title`, `safety_git_init_explain`
- `safety_sidebar` — sidebar label

---

## 14. Scope Exclusions

- No git diff content viewer (only name + status + stats)
- No merge between save points
- No partial save (save = always everything)
- No auto-save before AI sessions (manual only)
- No GitHub/GitLab integration (local git only)
- No undo for pick (if grabbed a file, it's here; rollback again if needed)
- No line-level cherry-pick (file-level only)
