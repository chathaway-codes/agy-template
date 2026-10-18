---
name: qa
description: >-
  Runs automated tests and verification checks using the project Makefile.
  Use this skill whenever verifying code changes, checking for regressions,
  or running test suites.
---

# Quality Assurance & Testing

Deterministic verification via `make`. Fast feedback, zero guesswork.

## Core Commands

Always execute targets from the repository root:

| Target | Purpose | Speed |
| :--- | :--- | :--- |
| `make test` | Full test suite | Fast |
| `make test-issues` | Verify issue tracker tooling and dependency graph | Sub-second (~0.15s) |
| `make clean` | Purge build artifacts, caches, and temporary files | Instant |

## Hacker QA Discipline

1. **Impatience (Tight Feedback Loops)**:
   - Run tests frequently. Feedback should take seconds, not minutes. Keep tests fast and run them early.
2. **Hubris (Non-Negotiable Quality)**:
   - Before completing any task, run `make test`. All assertions must pass (exit status `0`).
   - If tests fail, do not mock or suppress them. Fix the underlying logic.
3. **No Assumptions (Grounding)**:
   - If a test fails, inspect the exact failure message, line number, and stack trace.
   - Verify file paths, data structures, and types directly with inspection tools before making changes.
