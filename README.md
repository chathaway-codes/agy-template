# Agent-Ready Git Workspace Template

A minimalist, high-discipline workspace template designed for autonomous coding agents (Antigravity / `agy`) and human developers following the Unix philosophy and hacker ethos.

## Core Features

- **Agent Directives (`AGENTS.md`)**: Rules of engagement enforcing simplicity, Unix philosophy, the Three Virtues (Laziness, Impatience, Hubris), YAGNI, and strict verification gates.
- **Git-Stored Worktree Issue Tracker (`issues/`, `scripts/issue`)**: Zero-dependency, local-first issue tracker stored on an isolated orphan branch (`issues-data`) mounted via `git worktree`.
  - Fast CLI (`./scripts/issue`) with symlink-based dependency graph tracking (`blocked_by/`, `children/`).
  - Single-file zero-dependency web viewer (`./scripts/issue serve` or `make issues-ui`) with LLM prompt copy buttons and live search.
- **Agent Skills (`.agents/skills/`)**:
  - `issues`: Runbook and graph specification for managing tasks, dependencies, and bug tracking.
  - `qa`: Verification discipline ensuring zero-defect deliverables via `make test`.
- **Anti-Oscillation Ledger (`DEAD_ENDS.md`)**: Append-only log of failed approaches to prevent agents from repeating mistakes across runs.
- **Reproducible Container Environment (`Dockerfile`)**: Pre-configured Arch Linux developer environment with non-root UID 1000 user, Antigravity CLI (`agy`), and headless development tooling.
- **Self-Documenting Makefile (`Makefile`)**: Unified entrypoint for testing, issue tracking, container execution, and isolated YOLO remote-control daemon mode.

## Quick Start

### 1. Initialize Issue Tracker
On a fresh clone, run the bootstrap script to create the orphan `issues-data` branch and mount the `issues/` worktree:
```bash
./scripts/setup_issues.sh
```

### 2. Run Verification
```bash
make test
```

### 3. Manage Issues
```bash
# List all ready issues (open and unblocked)
make issues-ready

# Create a new issue
./scripts/issue create milestone_0 "Implement feature X"

# Launch read-only Web UI
make issues-ui
```

### 4. Containerized Development & YOLO Daemon
```bash
# Build dev container
make docker-build

# Run test suite in container
make docker-test

# Spawn isolated Antigravity daemon in YOLO mode
make docker-yolo
```
