---
name: issues
description: >-
  Manage git-stored issue tracking across backlogs, milestones, and bugs on an
  isolated orphan git branch via git worktree. Use this skill whenever creating,
  updating, querying, commenting on, or closing project issues.
---

# Git Issue Tracker

A minimalist, plain-text issue tracker stored on an isolated orphan git branch (`issues-data`) and mounted in the repository root as a linked `git worktree` under `issues/`.

## Architecture & Isolation

- **Orphan Branch**: All issues and issue history live on `issues-data`. Code branches (`main`, feature branches) never track issue files or merge issue commits.
- **Git Worktree**: The branch is checked out locally into `issues/`. The root `.gitignore` contains `/issues/`.
- **Agent Ergonomics**: Agents read, search, and edit regular markdown files in `issues/` using standard tools, while issuing git operations with `git -C issues`.

### Ensuring Worktree Setup
If `issues/` is missing in a fresh workspace:
```bash
./scripts/setup_issues.sh
# or manually:
git worktree list | grep -q "/issues" || git worktree add issues issues-data
```

## Directory & Dependency Layout

All issues live inside `issues/` organized by backlog folder:

```text
issues/
├── bugs/
│   └── 002-timeout-on-reconnect.md
├── milestone_0/
│   ├── 001-auth-token-refresh.md
│   └── 001-auth-token-refresh/     <-- Companion dir (created only if dependencies exist)
│       ├── children/
│       │   └── 003-session-storage.md -> ../../../milestone_0/003-session-storage.md
│       └── blocked_by/
│           └── 004-crypto-backend.md  -> ../../../milestone_0/004-crypto-backend.md
└── backlog/
```

- **Backlog directories**: Lowercase names representing milestones or categories (e.g., `bugs/`, `milestone_0/`, `backlog/`, `tech-debt/`).
- **File naming**: `<id>-<slug>.md` where `<id>` is a zero-padded 3-digit sequential integer unique across all backlogs (e.g., `001-auth-token-refresh.md`).
- **Filesystem Dependencies (Symlinks)**:
  - Parent/child and blocking relationships are tracked entirely on the filesystem via relative symlinks in companion directories (`<id>-<slug>/children/` and `<id>-<slug>/blocked_by/`).
  - No `## Parent` or `## Blocks` sections are stored in the markdown file; the reverse lookup is performed on demand via the filesystem using `find -L ... -samefile`.

## Standard Issue File Format

Every issue file must strictly adhere to the following markdown structure:

```markdown
# 001: Implement Auth Token Refresh

## Status
open

## Assignee
unassigned

## Description
Short description of the task, bug, or feature request. Include steps to reproduce or relevant context.

## Acceptance Criteria
- [ ] Token refresh endpoint handles expired access tokens
- [ ] Automated unit test verifies refresh rotation
- [ ] `make test` exits 0

## Comments
### 2026-10-18T14:30:00Z agent
Initial investigation completed.
```

### Allowed Status Values
- `open`: Ready for pickup.
- `in_progress`: Actively being worked on by assignee.
- `blocked`: Waiting on external dependency or unresolved question.
- `closed`: Completed and verified.

## Issue Management Tooling (`scripts/issue`)

Agents and developers should use the dedicated `scripts/issue` CLI and web UI instead of manual shell commands. The script automatically discovers the `issues-data` worktree across workspaces and performs git commits on the `issues-data` branch.

### Quick Reference

| Action | CLI Command |
| :--- | :--- |
| **List Issues** | `./scripts/issue list` (or `--status open`, `--backlog milestone_0`, `--json`) |
| **Find Ready Issues** | `./scripts/issue ready` (open issues with zero active blockers) |
| **Inspect Issue** | `./scripts/issue show <id-or-slug>` (e.g. `001` or `#001`) |
| **Next Available ID** | `./scripts/issue next-id` |
| **Create Issue** | `./scripts/issue create <backlog> "<title>" [--description "<desc>"]` |
| **Claim Issue** | `./scripts/issue claim <id> [assignee]` |
| **Update Status** | `./scripts/issue status <id> <open\|in_progress\|blocked\|closed>` |
| **Append Comment** | `./scripts/issue comment <id> "<message>" [--author "<name>"]` |
| **Add Blocker** | `./scripts/issue block <target_id> <blocker_id>` |
| **Remove Blocker** | `./scripts/issue unblock <target_id> <blocker_id>` |
| **Link Child Issue**| `./scripts/issue link <parent_id> <child_id>` |
| **Unlink Child** | `./scripts/issue unlink <parent_id> <child_id>` |
| **Move Backlog** | `./scripts/issue move <id> <new_backlog>` |
| **Close Issue** | `./scripts/issue close <id> ["closing notes"]` (auto-prunes incoming symlinks) |
| **Web UI Viewer** | `./scripts/issue serve [--port 8080]` (or `make issues-ui`) |

---

## Issue Web UI Viewer

A lightweight, zero-dependency read-only web server is provided in `scripts/issue_server.py`.

```bash
# Launch via CLI shortcut or Makefile
./scripts/issue serve --port 8080
# or
make issues-ui
```

### Key UI Features:
- **Instant Search & Status Filters**: Filter in real time by status (Ready, Open, In Progress, Blocked, Closed), Backlog, or text search (`/` shortcut).
- **Interactive Dependency Navigation**: Click any blocked-by, blocks, child, or parent issue card to instantly navigate across the graph.
- **One-Click LLM Copy Toolbar**:
  - `[🤖 Copy for LLM Prompt]`: Generates a formatted markdown summary with issue ID, title, status, relative path, dependencies, description, and criteria.
  - `[📋 Copy ID]`, `[📋 Copy Name]`, `[📄 Copy Path]`, `[📂 Copy Absolute Path]`: Quick single-value copy buttons with instant visual confirmation.
- **Deep Linking**: Full browser history integration via URL hashes (e.g. `http://localhost:8080/#001`).
- **Keyboard Shortcuts**: `j`/`k` (navigate issues), `/` (search), `c` (copy LLM prompt), `p` (copy path), `i` (copy ID).

---

## Under the Hood: Shell Cheatsheet (Manual Workflows)

When scripts are unavailable or when debugging low-level git operations, use `git -C issues` directly:

### 1. Find Next Available ID
```bash
next_id=$(printf "%03d\n" $(($(find issues/ -name "*.md" 2>/dev/null | grep -oE '[0-9]+' | sort -n | tail -1 || echo 0) + 1)))
```

### 2. List Active / Open Issues
```bash
grep -rn -A 1 "^## Status" issues/ | grep -B 1 "open"
```

### 3. Check Readiness / Dependencies
An issue is ready to start when its `blocked_by/` directory is empty or does not exist:
```bash
ls issues/milestone_0/001-target/blocked_by/ 2>/dev/null || echo "No blockers"
```

### 4. Create an Issue
Create `issues/<backlog>/<id>-<slug>.md` populated with the template above:
```bash
git -C issues add .
git -C issues commit -m "issue(<backlog>): create 001-slug"
```

### 5. Link Dependencies via Symlinks
Use `ln -sr` (automatic relative path calculation) to link dependencies into companion folders:
- **Add Child Issue**:
  ```bash
  mkdir -p issues/milestone_0/001-parent/children
  ln -sr issues/milestone_0/002-child.md issues/milestone_0/001-parent/children/
  ```
- **Add Blocker (001 is blocked by 003)**:
  ```bash
  mkdir -p issues/milestone_0/001-target/blocked_by
  ln -sr issues/milestone_0/003-blocker.md issues/milestone_0/001-target/blocked_by/
  ```
Commit:
```bash
git -C issues add -A
git -C issues commit -m "issue: link dependencies for 001-target"
```

### 6. Claim and Update Status
```bash
git -C issues commit -am "issue: claim 001-slug"
```

### 7. Append Comments
```bash
git -C issues commit -am "issue: comment on 001-slug"
```

### 8. Moving an Issue Across Backlogs
1. Locate incoming symlinks:
   ```bash
   refs=$(find -L issues -samefile <target_file> ! -path <target_file>)
   ```
2. Move file and companion directory:
   ```bash
   git -C issues mv <old_path>.md <new_path>.md
   [ -d "<old_path>" ] && git -C issues mv <old_path> <new_path>
   ```
3. Re-point referencing symlinks:
   ```bash
   for ref in $refs; do ln -sfr <new_path>.md "$ref"; done
   ```
4. Commit:
   ```bash
   git -C issues add -A
   git -C issues commit -m "issue: move <id>-<slug> to <new_backlog>"
   ```

### 9. Closing an Issue & Removing References
1. Locate and purge incoming symlinks:
   ```bash
   find -L issues -samefile <target_file> ! -path <target_file> -delete
   ```
2. Update issue status to `closed`, check off acceptance criteria, and commit:
   ```bash
   git -C issues add -A
   git -C issues commit -m "issue: close <id>-<slug> and prune references"
   ```

### 10. Syncing Remotes
```bash
git -C issues pull --rebase origin issues-data
git -C issues push origin issues-data
```
