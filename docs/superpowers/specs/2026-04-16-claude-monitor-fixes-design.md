# Claude Monitor Fixes — Combined Design

**Date:** 2026-04-16
**Order:** 3 → 1 → 2 → 5 → 6 → 4 (user choice "b")

## Scope

Six independent fixes to `claude-monitor` GUI. Each task has a clear
boundary and is small enough to land in a single session. This doc is one
combined spec; implementation happens one task at a time.

## Task 3 — Activity Haiku not analyzing (FIRST)

**Symptom:** Activity Log shows "Loading..." for "Where you stopped" and
"Analyze prompts" button produces nothing, despite API key being set in
Settings (persists to `config.toml`, `HaikuClient.is_available()` returns
`True` when loaded via `core.config.load_config`).

**Two concrete hypotheses:**

1. **Rate gate swallows the second call.** `core/haiku_client.py:55` —
   `if now - self._last_call < self._min_interval: return None`. In
   `HaikuContextThread.run()` we call `client.ask()` twice in a row
   (`context_prompt`, then `summary_prompt`) — the second call fires
   well inside the 5s gate and returns `None`. Primary call should still
   work, but needs verification.

2. **Label lifetime race.** `_where_stopped_label` is recreated by
   `_render_activity()` on every `update_data()` call. If the Haiku
   thread finishes after a re-render, the signal mutates a Qt object
   whose parent widget was deleted (no crash, just no visible change).

**Diagnostic plan (before touching logic):**

- Add `log.info` probes at `HaikuContextThread.run()` entry, after
  `is_available`, after parts assembly, before and after each `ask()`.
- Run the real GUI, select a project with known changes, observe logs.
- Decide fix based on findings.

**Likely fixes:**

- Combine two prompts into one `ask()` so rate gate is hit once.
- In `_on_haiku_ready`, guard with a token that the thread captured at
  launch time and matches the current label's token — old threads no-op.

## Task 1 — Delete Tips page entirely

**Remove:**
- `gui/pages/tips.py`
- `core/tips.py`
- Sidebar entry `("tips", ...)` in `gui/app/main.py`
- `self.page_tips = TipsPage()` and stack registration
- Any `update_tips(...)` calls
- i18n keys `tips_header`, `no_tips`, `tips_require`, `side_tips`,
  plus category icon map if unused elsewhere
- `tests/test_tips*` if present

**Verification:** `grep -r "TipsPage\|tips_header\|TipsEngine\|update_tips"`
after deletion returns zero hits.

## Task 2 — Lock file: one-click = CLAUDE.md + hook

**File:** `gui/pages/frozen_tab.py`

**Remove:**
- `_btn_hook_toggle`
- `_hook_status_lbl`
- `_render_hook_status()`
- `_on_toggle_hook()`
- Calls to them in `_build_ui()` and `_refresh()`
- i18n keys `frozen_hook_on/off/toggle_on/toggle_off/installed/removed`

**Change `_on_add()`:**
After successful `add_frozen_file(...)` and `_sync_claude_md()`, if
`not fm.is_hook_installed()` then `fm.install_hook()`. Silent — no
dialog — since this is now the default behavior. Only show an error if
install fails.

**Row layout fix:** `_make_row()` uses nested `QVBoxLayout` inside
`QHBoxLayout` — path and note can mis-align because the lock icon has no
fixed height. Set a fixed pixel height on the icon and align both layouts
top to fix the "lines don't match" issue.

## Task 5 — Overview + Usage merge (frontend-design)

**Deferred design.** This task needs its own detailed design pass because
the merge affects layout, density, and information hierarchy. When we
reach it:

- Invoke `frontend-design` with the merged page as the target.
- Must keep: Claude Status block, Docker info, Security Score, Hoff
  image + nag + 3 buttons (refresh / nag / Hasselhoff).
- Must absorb from Usage: plan label, today/week breakdown, cache bar,
  model table, project table, weekly trends.
- Must fix: string overflow in existing Overview stat rows.
- Remove `UsagePage`, `("usage", ...)` sidebar entry, and the `page_usage`
  wiring in `gui/app/main.py`.

## Task 6 — Save Points: merge Code + Env (frontend-design + ui-ux-pro-max)

**Deferred design.** Current state: `SavePointsPage` is a QTabWidget with
three tabs (Code / Env / Frozen). User wants Code and Env unified into
one scroll-panel with clearly labeled sections; Frozen stays as a
separate bottom panel (different UX).

When we reach it:
- Invoke `frontend-design` + `ui-ux-pro-max`.
- `SafetyNetPage` and `SnapshotsPage` keep their widgets but lose their
  outer layout; wrapped in labeled sections inside a new combined page.
- One unified save button stays at top (already there).
- Frozen tab stays reachable — either as bottom accordion or as its own
  section below.

## Task 4 — Health findings verification (LAST)

**Goal:** walk through the specific findings the user listed in their
message and verify each against the current codebase.

**Method:** for each finding, run `Grep` / `Read` to confirm.
Categorize as: TRUE (finding matches reality), FALSE (code changed, or
analyzer wrong), or STALE (was true, fixed since).

**Output:** one table, no code changes (this is verification only).

## Non-goals

- Secret-in-git cleanup (user has rotated key many times; not a concern
  for this session).
- Git history rewrite.
- Refactoring `gui/pages/hasselhoff_wizard.py` (754 lines — called out by
  the health scan but not in the user's fix list).

## Order of execution

```
3 (Haiku debug)
 → 1 (Delete Tips)
 → 2 (Lock file simplify)
 → 5 (Overview+Usage merge)
 → 6 (Save Points merge)
 → 4 (Health verify)
```

Each task ends with a verification step and a commit before the next
begins.
