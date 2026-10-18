#!/usr/bin/env python3
"""
tests/test_issue_tooling.py - Unit and integration tests for git issue CLI and web UI.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

# Ensure scripts dir is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from issue import IssueTracker, slugify


class TestIssueTooling(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)
        self.issues_dir = self.repo_dir / "issues"
        self.issues_dir.mkdir(parents=True)

        # Initialize git repo in issues_dir
        subprocess.run(["git", "init", "-b", "issues-data"], cwd=self.issues_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.issues_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=self.issues_dir, check=True, capture_output=True)

        self.tracker = IssueTracker(self.issues_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_slugify(self):
        self.assertEqual(slugify("Implement Jump Buffering!"), "implement-jump-buffering")
        self.assertEqual(slugify("  Combat: Creeps & Bugs  "), "combat-creeps-bugs")

    def test_create_and_load(self):
        iss = self.tracker.create("milestone_0", "First Task", description="Initial description")
        self.assertEqual(iss.id, "001")
        self.assertEqual(iss.status, "open")
        self.assertEqual(iss.assignee, "unassigned")
        self.assertEqual(iss.backlog, "milestone_0")
        self.assertTrue(iss.path.exists())

        # Verify next_id increments
        self.assertEqual(self.tracker.next_id(), "002")

        # Load all
        all_issues = self.tracker.load_all()
        self.assertIn("001", all_issues)
        self.assertEqual(all_issues["001"].title, "First Task")

    def test_claim_and_status(self):
        self.tracker.create("milestone_0", "Task A")
        self.tracker.claim("001", assignee="agent-1")
        iss = self.tracker.find_issue("001")
        self.assertEqual(iss.status, "in_progress")
        self.assertEqual(iss.assignee, "agent-1")

        self.tracker.set_status("001", "blocked")
        iss = self.tracker.find_issue("001")
        self.assertEqual(iss.status, "blocked")

    def test_comment(self):
        self.tracker.create("milestone_0", "Task A")
        self.tracker.add_comment("001", "Investigation completed.", author="debugger")
        iss = self.tracker.find_issue("001")
        self.assertEqual(len(iss.comments), 2)  # Initial create comment + new comment
        self.assertEqual(iss.comments[-1]["author"], "debugger")
        self.assertEqual(iss.comments[-1]["body"], "Investigation completed.")

    def test_dependencies_and_ready(self):
        iss1 = self.tracker.create("milestone_0", "Prerequisite")
        iss2 = self.tracker.create("milestone_0", "Dependent Feature")

        # Initially both are ready
        issues = self.tracker.load_all()
        ready = sorted([i.id for i in issues.values() if i.is_ready])
        self.assertEqual(ready, ["001", "002"])

        # Block 002 by 001
        self.tracker.add_blocker("002", "001")
        issues = self.tracker.load_all()
        self.assertEqual(issues["002"].blocked_by, ["001"])
        self.assertEqual(issues["001"].blocks, ["002"])

        # Now 002 is not ready
        self.assertFalse(issues["002"].is_ready)

        # Unblock 002
        self.tracker.remove_blocker("002", "001")
        issues = self.tracker.load_all()
        self.assertEqual(issues["002"].blocked_by, [])
        self.assertEqual(issues["001"].blocks, [])

    def test_parent_child_links(self):
        self.tracker.create("milestone_0", "Epic Task")
        self.tracker.create("milestone_0", "Subtask 1")

        self.tracker.add_child("001", "002")
        issues = self.tracker.load_all()
        self.assertEqual(issues["001"].children, ["002"])
        self.assertEqual(issues["002"].parents, ["001"])

        self.tracker.remove_child("001", "002")
        issues = self.tracker.load_all()
        self.assertEqual(issues["001"].children, [])
        self.assertEqual(issues["002"].parents, [])

    def test_move_backlog(self):
        self.tracker.create("milestone_0", "Task A")
        self.tracker.create("milestone_0", "Task B")
        self.tracker.add_blocker("002", "001")

        # Move 001 to milestone_1
        self.tracker.move("001", "milestone_1")
        iss1 = self.tracker.find_issue("001")
        self.assertEqual(iss1.backlog, "milestone_1")

        # Check that symlink in 002/blocked_by still points to 001 and resolves correctly
        issues = self.tracker.load_all()
        self.assertEqual(issues["002"].blocked_by, ["001"])
        self.assertEqual(issues["001"].blocks, ["002"])

    def test_close_and_prune_references(self):
        self.tracker.create("milestone_0", "Task A")
        self.tracker.create("milestone_0", "Task B")
        self.tracker.add_blocker("002", "001")

        # Close 001
        self.tracker.close("001", comment="Done and verified.")
        iss1 = self.tracker.find_issue("001")
        self.assertEqual(iss1.status, "closed")

        # Verify symlink in 002/blocked_by was pruned
        issues = self.tracker.load_all()
        self.assertEqual(issues["002"].blocked_by, [])


if __name__ == "__main__":
    unittest.main()
