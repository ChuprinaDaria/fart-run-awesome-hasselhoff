# Claude Status Monitor — Don't Panic, It's Not Your Code

> "API ліг, а вайбкодер думає що зламав production."

## Problem

Vibe coder works with AI. Something stops working — Haiku explanations disappear, AI features go silent. The person panics: "I broke something." In reality, Anthropic API is having a bad day. Zero visibility into whether the problem is theirs or upstream.

Current state: changelog_watcher.py checks Claude version at startup, shows a popup on update. No API health monitoring, no status display, no "it's not you" message.

---

## 1. Statusbar

Permanent horizontal bar at the bottom of the window, visible from every page.

```
+--------------------------------------------------------------+
|  Claude 1.0.20 | API: OK | Checked 2 min ago                |
+--------------------------------------------------------------+
```

### States:

| Indicator | Text | Statusbar background |
|---|---|---|
| All good | `API: OK` | Default (gray) |
| Degradation | `API: Degraded` | Yellow |
| Outage | `API: Down` | Red |
| Can't reach status page | `API: Unknown` | Gray |
| Claude not installed | `Claude: not found` | Gray |

Click on statusbar navigates to Overview page with detailed Claude Status block.

Version updates on startup + every status check (5 min). If version changes — existing popup fires + statusbar shows new version.

---

## 2. Status Checker

### Source:

Anthropic public status page (Atlassian Statuspage).

Primary endpoint: `https://status.anthropic.com/api/v2/status.json`

Response:
```json
{
  "status": {
    "indicator": "none",
    "description": "All Systems Operational"
  }
}
```

Detail endpoint (for Overview): `https://status.anthropic.com/api/v2/components.json`

### Indicator mapping:

| indicator | Our status |
|---|---|
| `none` | OK |
| `minor` | Degraded |
| `major` | Down |
| `critical` | Down |

### Schedule:

- On app startup
- Every 5 minutes (QTimer)
- Instantly when HaikuClient reports an API error

### API:

```python
class StatusChecker:
    def __init__(self, db: HistoryDB)

    def check_now(self) -> StatusResult
        # 1. GET status.anthropic.com/api/v2/status.json
        # 2. Parse indicator
        # 3. GET claude --version (throttled — once per 5 min, not every call)
        # 4. Save to SQLite
        # 5. Return StatusResult

    def get_last_status(self) -> StatusResult | None
        # From SQLite cache

    def get_status_history(self, hours: int = 24) -> list[StatusResult]
        # For Overview timeline — returns only state transitions
```

```python
@dataclass
class StatusResult:
    timestamp: str
    api_indicator: str      # "none", "minor", "major", "critical"
    api_description: str    # "All Systems Operational"
    claude_version: str | None
    response_time_ms: int
```

### Timeout/fallback:

- HTTP timeout: 5 seconds
- Status page unreachable: `API: Unknown`, NOT red (could be local network)
- Never blocks UI — everything runs in QThread

---

## 3. Overview Page — Claude Status Block

New block at top of Overview page, before existing Budget/Tokens:

```
+- Claude Code ----------------------------------------+
|                                                       |
|  Version: 1.0.20                                      |
|  API: OK -- All Systems Operational                   |
|  Last check: 14:32 (2 min ago)      [Check Now]      |
|                                                       |
|  --- Last 24h ---                                     |
|                                                       |
|  14:32  OK                                            |
|  13:45  Degraded -- Increased API latency             |
|  13:35  OK                                            |
|                                                       |
|  --- Version History ---                              |
|                                                       |
|  1.0.20  detected Apr 15, 14:00                       |
|  1.0.19  detected Apr 12, 09:30                       |
|  1.0.18  detected Apr 05, 11:15                       |
|                                                       |
|  [Show Full Changelog]                                |
|                                                       |
+-------------------------------------------------------+
```

### Three parts:

1. **Current status** -- version, API status, last check time, manual Check Now button
2. **Status history (24h)** -- from SQLite, shows only transitions (OK -> Degraded -> OK). If all day OK: one line "All day: OK"
3. **Version history** -- from existing `claude_versions` table. When each version was detected.

### When API: Degraded or Down:

Block gets yellow/red border. Extra line:

```
+- Claude Code ----------------------------------------+
|                                                       |
|  Version: 1.0.20                                      |
|  API: Down -- Major outage in progress                |
|  Last check: 14:32 (2 min ago)      [Check Now]      |
|                                                       |
|  If AI features aren't working right now, it's not    |
|  your code. Anthropic is having issues. Wait it out.  |
|                                                       |
+-------------------------------------------------------+
```

If Haiku available -- generates contextual message: "Anthropic API is experiencing issues. Your Haiku explanations and AI summaries won't work until it's back. Your code and save points are fine."

---

## 4. HaikuClient Integration — Instant Check on Error

Current behavior: `HaikuClient.ask()` returns `None` on error. User sees blank space, doesn't know why.

### Change:

HaikuClient gets an error callback:

```python
class HaikuClient:
    def __init__(self, ..., on_api_error=None):
        self._on_api_error = on_api_error

    def ask(self, prompt, max_tokens=200) -> str | None:
        try:
            # ... existing logic ...
        except Exception as e:
            if self._on_api_error:
                self._on_api_error(str(e))
            return None
```

In app.py:

```python
def _on_haiku_error(self, error_msg):
    self._status_checker.check_now()  # background thread
    # statusbar updates automatically from result
```

### Two failure modes, two messages:

1. **API is down** (status page confirms): statusbar goes yellow/red. User sees it's not their fault.
2. **API is OK but Haiku fails** (bad key, rate limit): where Haiku text should be, show:
   `(Haiku unavailable -- check API key in Settings)`

---

## 5. Architecture

### New files:

```
core/
  status_checker.py        # StatusChecker class, HTTP to status.anthropic.com

gui/
  statusbar.py             # QStatusBar widget: version + API status
```

### Changes to existing files:

- `core/history.py` -- new table `api_status_log`, CRUD methods
- `core/haiku_client.py` -- `on_api_error` callback parameter
- `gui/app.py` -- create StatusChecker, QTimer 5 min, create statusbar, connect haiku error to instant check, statusbar click to overview
- `gui/pages/overview.py` -- Claude Status block at top
- `i18n/en.py`, `i18n/ua.py` -- ~15 new strings
- `config.toml` -- `[status]` section

### SQLite:

**New table `api_status_log`:**

```sql
CREATE TABLE api_status_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    indicator TEXT NOT NULL,
    description TEXT NOT NULL,
    claude_version TEXT DEFAULT '',
    response_time_ms INTEGER DEFAULT 0
)
```

Pruning: keep 7 days, delete older on each check.

### Config:

```toml
[status]
check_interval_minutes = 5
enabled = true
```

### Dependencies: none new. `urllib.request` for status page JSON (stdlib).

---

## 6. Hasselhoff

- `API: OK` -- random 10%: "The Hoff is watching. All clear."
- `API: Down` -- "Even the Hoff can't fix this one. Wait."
- Version changed -- "The Hoff upgraded. New powers unlocked."

---

## 7. i18n

~15 new keys EN + UA:

- `status_ok`, `status_degraded`, `status_down`, `status_unknown`
- `status_checked_ago`, `status_check_now`
- `status_dont_panic` -- "If AI features aren't working, it's not your code."
- `status_haiku_unavailable` -- "Haiku unavailable -- check API key in Settings"
- `status_all_day_ok` -- "All day: OK"
- `status_version_history`, `status_last_24h`
- `status_claude_not_found`

---

## 8. Error Handling

| Situation | Behavior |
|---|---|
| status.anthropic.com unreachable | `API: Unknown`, gray, not red |
| JSON parse error | `API: Unknown`, log warning |
| claude --version fails | Version shows "unknown", status check continues |
| SQLite write fails | Log warning, statusbar still updates from in-memory result |
| Network flap (down then up quickly) | History shows both transitions |
| Status page returns unexpected indicator | Map to Unknown, log the raw value |

---

## 9. Testing

```
tests/
  test_status_checker.py
```

- `test_parse_status_ok` -- mock JSON indicator "none" -> OK
- `test_parse_status_degraded` -- indicator "minor" -> Degraded
- `test_parse_status_down` -- indicator "major" -> Down
- `test_timeout` -- status page unreachable -> Unknown, no crash
- `test_save_and_load` -- SQLite persistence round-trip
- `test_history_pruning` -- records older than 7 days deleted
- `test_status_transitions` -- get_status_history returns only changes
- `test_haiku_error_triggers_check` -- callback fires check_now()
- `test_version_check_throttle` -- claude --version called max once per 5 min

All tests mock HTTP via `unittest.mock.patch` on `urllib.request.urlopen`.

---

## 10. Scope Exclusions

- No changelog content fetching/parsing (only URL link to browser)
- No email/push notifications on status change (desktop app only)
- No per-component status (only overall API status)
- No latency graphing (just response_time_ms in DB for future use)
- No auto-retry of failed Haiku calls when API recovers
- No status page for other providers (OpenAI, etc.)

---

## 11. Cross-Platform

| Component | Approach |
|---|---|
| HTTP request | `urllib.request.urlopen` (stdlib) |
| JSON parsing | `json.loads` (stdlib) |
| claude --version | `subprocess` via existing `get_claude_version()` |
| QStatusBar | Qt native, works on Linux/Mac/Windows |
| SQLite | stdlib sqlite3 |
