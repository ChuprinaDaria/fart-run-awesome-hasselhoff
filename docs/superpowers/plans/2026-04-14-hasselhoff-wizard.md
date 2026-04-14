# Hasselhoff Vibecode Wizard — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Hoff Wizard" tab that auto-detects and installs Git, Cursor, VS Code, and Claude Code with Full Baywatch Hasselhoff + Fart madness on every step.

**Architecture:** New page `gui/pages/hasselhoff_wizard.py` with tool detection, download/install via background QThread, and Hasselhoff phrases/sounds on every event. Tool URLs fetched from `tools.json` hosted in the repo (fetched via raw GitHub URL at runtime). Linux installs via pkexec, Win/Mac via file download + open.

**Tech Stack:** PyQt5, urllib, subprocess, json

---

### Task 1: Create tools.json

**Files:**
- Create: `tools.json`

- [ ] **Step 1: Create tools.json with all tool definitions**
- [ ] **Step 2: Commit**

---

### Task 2: Create hasselhoff_wizard.py page

**Files:**
- Create: `gui/pages/hasselhoff_wizard.py`

- [ ] **Step 1: Create the full wizard page widget**
- [ ] **Step 2: Commit**

---

### Task 3: Add i18n strings

**Files:**
- Modify: `claude_nagger/i18n/en.py`
- Modify: `claude_nagger/i18n/ua.py`

- [ ] **Step 1: Add Hoff Wizard strings to both language files**
- [ ] **Step 2: Commit**

---

### Task 4: Integrate into app.py

**Files:**
- Modify: `gui/app.py`

- [ ] **Step 1: Import, add sidebar item, create page, register in stack**
- [ ] **Step 2: Commit**

---

### Task 5: Smoke test

- [ ] **Step 1: Run the app and verify the wizard tab appears and works**

Run: `cd /home/dchuprina/claude-monitor && python -m gui.app`
