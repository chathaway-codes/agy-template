#!/usr/bin/env python3
"""
scripts/issue.py - CLI tool for Git-stored issue management.

Follows the git-stored issue tracking specification:
- Orphan branch 'issues-data' mounted under 'issues/'.
- Companion directories with symlinks for dependencies (blocked_by, children).
- Clean, fast, agent-friendly CLI for scripting and day-to-day issue management.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple


def find_issues_dir() -> Path:
    """Find the issues worktree directory robustly across worktrees and subdirs."""
    # 1. ISSUES_DIR env var
    if "ISSUES_DIR" in os.environ:
        p = Path(os.environ["ISSUES_DIR"]).resolve()
        if p.is_dir():
            return p

    # 2. Local 'issues' in cwd or any ancestor directory up to filesystem root
    curr = Path.cwd().resolve()
    for parent in [curr, *curr.parents]:
        cand = parent / "issues"
        if cand.is_dir() and (cand / ".git").exists():
            return cand
        if cand.is_dir() and any(cand.glob("*/*.md")):
            return cand

    # 3. Discover worktrees via git
    try:
        res = subprocess.run(
            ["git", "worktree", "list"],
            capture_output=True,
            text=True,
            check=True,
        )
        for line in res.stdout.strip().splitlines():
            parts = line.split()
            # Look for line ending in [issues-data]
            if len(parts) >= 3 and parts[-1] == "[issues-data]":
                p = Path(parts[0]).resolve()
                if p.is_dir():
                    return p
            # Or path ending in /issues
            if parts and parts[0].endswith("/issues"):
                p = Path(parts[0]).resolve()
                if p.is_dir():
                    return p
    except Exception:
        pass

    # 4. Fallback to repo root / issues if git top level can be found
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        cand = Path(res.stdout.strip()) / "issues"
        if cand.is_dir():
            return cand
    except Exception:
        pass

    # Default fallback to ./issues
    return Path.cwd() / "issues"


def slugify(text: str) -> str:
    """Convert text into a URL/filesystem friendly slug."""
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def get_current_user() -> str:
    """Determine current author name for git and issue comments."""
    try:
        res = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True,
            text=True,
            check=True,
        )
        name = res.stdout.strip()
        if name:
            return name
    except Exception:
        pass
    return os.environ.get("USER", "agent")


@dataclass
class Issue:
    id: str
    int_id: int
    slug: str
    title: str
    status: str
    assignee: str
    backlog: str
    path: Path
    rel_path: str
    description: str = ""
    acceptance_criteria: List[Dict[str, any]] = field(default_factory=list)
    comments: List[Dict[str, str]] = field(default_factory=list)
    raw_content: str = ""
    blocked_by: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    parents: List[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """Issue is open and has no active blockers."""
        if self.status != "open":
            return False
        # Blockers are active if any blocker is not closed
        # Note: caller will populate is_ready after resolving blocker statuses
        return len(self.blocked_by) == 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "int_id": self.int_id,
            "slug": self.slug,
            "title": self.title,
            "status": self.status,
            "assignee": self.assignee,
            "backlog": self.backlog,
            "path": str(self.path),
            "rel_path": self.rel_path,
            "description": self.description,
            "acceptance_criteria": self.acceptance_criteria,
            "comments": self.comments,
            "raw_content": self.raw_content,
            "blocked_by": self.blocked_by,
            "blocks": self.blocks,
            "children": self.children,
            "parents": self.parents,
            "is_ready": self.is_ready,
        }


class IssueTracker:
    def __init__(self, issues_dir: Optional[Path] = None):
        self.issues_dir = issues_dir or find_issues_dir()

    def run_git(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the issues repository."""
        cmd = ["git", "-C", str(self.issues_dir)] + args
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def load_all(self) -> Dict[str, Issue]:
        """Load and parse all issues, building the full dependency graph."""
        issues: Dict[str, Issue] = {}
        if not self.issues_dir.is_dir():
            return issues

        # 1. Parse markdown files
        for p in self.issues_dir.glob("*/*.md"):
            if not p.is_file() or p.name.startswith("."):
                continue
            issue = self._parse_file(p)
            if issue:
                issues[issue.id] = issue

        # 2. Build dependency relationships from companion directories
        # Map path/stem to issue ID
        stem_to_id: Dict[str, str] = {iss.slug: iss.id for iss in issues.values()}
        path_to_id: Dict[Path, str] = {iss.path.resolve(): iss.id for iss in issues.values()}

        for p in self.issues_dir.glob("*/*"):
            if not p.is_dir() or p.name.startswith("."):
                continue
            # p is companion dir, e.g. issues/milestone_0/003-slug
            slug = p.name
            parent_id = stem_to_id.get(slug)
            if not parent_id:
                # Try finding by ID prefix
                m = re.match(r"^(\d+)", slug)
                if m:
                    norm_id = f"{int(m.group(1)):03d}"
                    parent_id = norm_id if norm_id in issues else None

            # blocked_by
            blocked_by_dir = p / "blocked_by"
            if blocked_by_dir.is_dir():
                for link in blocked_by_dir.iterdir():
                    target_id = self._resolve_target_id(link, stem_to_id, path_to_id)
                    if parent_id and target_id and parent_id in issues:
                        if target_id not in issues[parent_id].blocked_by:
                            issues[parent_id].blocked_by.append(target_id)
                        if target_id in issues and parent_id not in issues[target_id].blocks:
                            issues[target_id].blocks.append(parent_id)

            # children
            children_dir = p / "children"
            if children_dir.is_dir():
                for link in children_dir.iterdir():
                    target_id = self._resolve_target_id(link, stem_to_id, path_to_id)
                    if parent_id and target_id and parent_id in issues:
                        if target_id not in issues[parent_id].children:
                            issues[parent_id].children.append(target_id)
                        if target_id in issues and parent_id not in issues[target_id].parents:
                            issues[target_id].parents.append(parent_id)

        # 3. Sort dependency lists
        for iss in issues.values():
            iss.blocked_by.sort()
            iss.blocks.sort()
            iss.children.sort()
            iss.parents.sort()

        # Return canonically sorted by integer ID
        return dict(sorted(issues.items(), key=lambda item: item[1].int_id))

    def _resolve_target_id(
        self,
        link: Path,
        stem_to_id: Dict[str, str],
        path_to_id: Dict[Path, str],
    ) -> Optional[str]:
        """Resolve a symlink or filename to an issue ID."""
        try:
            resolved = link.resolve()
            if resolved in path_to_id:
                return path_to_id[resolved]
        except Exception:
            pass

        stem = link.name
        if stem.endswith(".md"):
            stem = stem[:-3]
        if stem in stem_to_id:
            return stem_to_id[stem]

        m = re.match(r"^(\d+)", stem)
        if m:
            return f"{int(m.group(1)):03d}"
        return None

    def _parse_file(self, file_path: Path) -> Optional[Issue]:
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Backlog is the parent folder name
        backlog = file_path.parent.name
        slug = file_path.stem

        # Match ID from filename or title
        m_filename = re.match(r"^(\d+)-(.*)$", slug)
        file_id = m_filename.group(1) if m_filename else None

        # Parse Level 1 header
        m_title = re.search(r"^#\s+(?:(\d+):\s*)?(.*)$", content, re.MULTILINE)
        if m_title:
            title_id = m_title.group(1)
            title = m_title.group(2).strip()
        else:
            title_id = None
            title = slug

        raw_id = file_id or title_id or "000"
        try:
            int_id = int(raw_id)
            issue_id = f"{int_id:03d}"
        except ValueError:
            int_id = 0
            issue_id = raw_id

        # Status
        m_status = re.search(r"^##\s+Status\s*\n\s*([a-zA-Z0-9_-]+)", content, re.MULTILINE)
        status = m_status.group(1).strip().lower() if m_status else "open"

        # Assignee
        m_assignee = re.search(r"^##\s+Assignee\s*\n\s*([^\n#]+)", content, re.MULTILINE)
        assignee = m_assignee.group(1).strip() if m_assignee else "unassigned"

        # Description
        m_desc = re.search(r"##\s+Description\s*\n(.*?)(?=\n##\s+|\Z)", content, re.DOTALL)
        description = m_desc.group(1).strip() if m_desc else ""

        # Acceptance Criteria
        criteria = []
        m_crit = re.search(r"##\s+Acceptance Criteria\s*\n(.*?)(?=\n##\s+|\Z)", content, re.DOTALL)
        if m_crit:
            for line in m_crit.group(1).splitlines():
                crit_match = re.match(r"^\s*-\s*\[([ xX])\]\s*(.*)$", line)
                if crit_match:
                    criteria.append({
                        "checked": crit_match.group(1).lower() == "x",
                        "text": crit_match.group(2).strip(),
                    })

        # Comments
        comments = []
        m_comm = re.search(r"##\s+Comments\s*\n(.*?)(?=\n##\s+|\Z)", content, re.DOTALL)
        if m_comm:
            raw_comments = m_comm.group(1).strip()
            comment_blocks = re.split(r"(?m)^###\s+", raw_comments)
            for block in comment_blocks:
                block = block.strip()
                if not block:
                    continue
                header_line, *body_lines = block.splitlines()
                header_parts = header_line.split(None, 1)
                ts = header_parts[0] if len(header_parts) >= 1 else ""
                author = header_parts[1] if len(header_parts) >= 2 else ""
                body = "\n".join(body_lines).strip()
                comments.append({"timestamp": ts, "author": author, "body": body})

        # Calculate relative path from issues_dir or cwd
        try:
            rel_path = f"issues/{backlog}/{file_path.name}"
        except Exception:
            rel_path = str(file_path)

        return Issue(
            id=issue_id,
            int_id=int_id,
            slug=slug,
            title=title,
            status=status,
            assignee=assignee,
            backlog=backlog,
            path=file_path,
            rel_path=rel_path,
            description=description,
            acceptance_criteria=criteria,
            comments=comments,
            raw_content=content,
        )

    def find_issue(self, query: str) -> Issue:
        """Find an issue by ID (e.g. '003', '3', '#003'), slug, or path."""
        issues = self.load_all()
        q = query.strip().lstrip("#")

        # Try exact ID
        if q in issues:
            return issues[q]
        if q.isdigit():
            norm_id = f"{int(q):03d}"
            if norm_id in issues:
                return issues[norm_id]

        # Try slug / stem
        stem = Path(q).stem
        for iss in issues.values():
            if iss.slug == stem or iss.slug == q:
                return iss

        # Try title or partial slug match
        lower_q = q.lower()
        matches = [
            iss for iss in issues.values()
            if lower_q in iss.slug.lower() or lower_q in iss.title.lower()
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            exact = [m for m in matches if m.slug == lower_q or m.id == lower_q]
            if len(exact) == 1:
                return exact[0]
            raise ValueError(f"Ambiguous query '{query}': matches {[m.id for m in matches]}")

        raise KeyError(f"Issue not found: '{query}'")

    def next_id(self) -> str:
        """Return the next available 3-digit zero-padded ID."""
        issues = self.load_all()
        if not issues:
            return "001"
        max_id = max(iss.int_id for iss in issues.values())
        return f"{max_id + 1:03d}"

    def create(
        self,
        backlog: str,
        title: str,
        assignee: str = "unassigned",
        description: str = "",
        acceptance_criteria: Optional[List[str]] = None,
        commit: bool = True,
    ) -> Issue:
        """Create a new issue file and commit to git."""
        new_id = self.next_id()
        base_slug = slugify(title)
        slug = f"{new_id}-{base_slug}"
        backlog_dir = self.issues_dir / backlog
        backlog_dir.mkdir(parents=True, exist_ok=True)

        issue_file = backlog_dir / f"{slug}.md"
        if issue_file.exists():
            raise FileExistsError(f"Issue file already exists: {issue_file}")

        criteria_lines = []
        if acceptance_criteria:
            for item in acceptance_criteria:
                criteria_lines.append(f"- [ ] {item}")
        else:
            criteria_lines.append("- [ ] Implementation complete and verified")

        desc_content = description.strip() if description else "Description to be provided."
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        author = get_current_user()

        content = f"""# {new_id}: {title}

## Status
open

## Assignee
{assignee}

## Description
{desc_content}

## Acceptance Criteria
{chr(10).join(criteria_lines)}

## Comments
### {now_ts} {author}
Issue created in {backlog}.
"""
        issue_file.write_text(content, encoding="utf-8")

        if commit:
            self.run_git(["add", str(issue_file)])
            self.run_git(["commit", "-m", f"issue({backlog}): create {slug}"])

        return self.find_issue(new_id)

    def set_status(self, query: str, status: str, commit: bool = True) -> Issue:
        """Update the status of an issue."""
        valid_statuses = ("open", "in_progress", "blocked", "closed")
        status = status.lower()
        if status not in valid_statuses:
            raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")

        issue = self.find_issue(query)
        content = issue.path.read_text(encoding="utf-8")

        # Replace ## Status section
        new_content = re.sub(
            r"(##\s+Status\s*\n\s*)([a-zA-Z0-9_-]+)",
            rf"\g<1>{status}",
            content,
            count=1,
        )
        issue.path.write_text(new_content, encoding="utf-8")

        if commit:
            self.run_git(["add", str(issue.path)])
            self.run_git(["commit", "-m", f"issue: set status {status} on {issue.slug}"])

        return self.find_issue(issue.id)

    def set_assignee(self, query: str, assignee: str, commit: bool = True) -> Issue:
        """Update the assignee of an issue."""
        issue = self.find_issue(query)
        content = issue.path.read_text(encoding="utf-8")

        new_content = re.sub(
            r"(##\s+Assignee\s*\n\s*)([^\n#]+)",
            rf"\g<1>{assignee}",
            content,
            count=1,
        )
        issue.path.write_text(new_content, encoding="utf-8")

        if commit:
            self.run_git(["add", str(issue.path)])
            self.run_git(["commit", "-m", f"issue: assign {issue.slug} to {assignee}"])

        return self.find_issue(issue.id)

    def claim(self, query: str, assignee: Optional[str] = None, commit: bool = True) -> Issue:
        """Claim an issue: set assignee and status to in_progress."""
        user = assignee or get_current_user()
        issue = self.find_issue(query)
        content = issue.path.read_text(encoding="utf-8")

        # Update status to in_progress
        content = re.sub(
            r"(##\s+Status\s*\n\s*)([a-zA-Z0-9_-]+)",
            r"\g<1>in_progress",
            content,
            count=1,
        )
        # Update assignee
        content = re.sub(
            r"(##\s+Assignee\s*\n\s*)([^\n#]+)",
            rf"\g<1>{user}",
            content,
            count=1,
        )
        issue.path.write_text(content, encoding="utf-8")

        if commit:
            self.run_git(["add", str(issue.path)])
            self.run_git(["commit", "-m", f"issue: claim {issue.slug}"])

        return self.find_issue(issue.id)

    def add_comment(
        self,
        query: str,
        comment_text: str,
        author: Optional[str] = None,
        commit: bool = True,
    ) -> Issue:
        """Append an ISO-timestamped comment to an issue."""
        issue = self.find_issue(query)
        content = issue.path.read_text(encoding="utf-8")
        now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        user = author or get_current_user()

        new_entry = f"### {now_ts} {user}\n{comment_text.strip()}\n"

        if "## Comments" in content:
            new_content = content.rstrip() + f"\n\n{new_entry}"
        else:
            new_content = content.rstrip() + f"\n\n## Comments\n{new_entry}"

        issue.path.write_text(new_content, encoding="utf-8")

        if commit:
            self.run_git(["add", str(issue.path)])
            self.run_git(["commit", "-m", f"issue: comment on {issue.slug}"])

        return self.find_issue(issue.id)

    def add_blocker(self, target_query: str, blocker_query: str, commit: bool = True) -> None:
        """Mark target_issue as blocked by blocker_issue via symlink in companion dir."""
        target = self.find_issue(target_query)
        blocker = self.find_issue(blocker_query)

        companion_dir = target.path.parent / target.slug / "blocked_by"
        companion_dir.mkdir(parents=True, exist_ok=True)

        symlink_path = companion_dir / blocker.path.name
        if symlink_path.exists() or symlink_path.is_symlink():
            return  # Already blocked

        rel_target = os.path.relpath(blocker.path, companion_dir)
        symlink_path.symlink_to(rel_target)

        if commit:
            self.run_git(["add", "-A"])
            self.run_git(["commit", "-m", f"issue: mark {target.slug} blocked by {blocker.slug}"])

    def remove_blocker(self, target_query: str, blocker_query: str, commit: bool = True) -> None:
        """Remove blocker dependency from target issue."""
        target = self.find_issue(target_query)
        blocker = self.find_issue(blocker_query)

        companion_dir = target.path.parent / target.slug / "blocked_by"
        symlink_path = companion_dir / blocker.path.name
        if symlink_path.is_symlink() or symlink_path.exists():
            symlink_path.unlink()

        self._prune_empty_dirs(target.path.parent / target.slug)

        if commit:
            self.run_git(["add", "-A"])
            self.run_git(["commit", "-m", f"issue: unblock {target.slug} from {blocker.slug}"])

    def add_child(self, parent_query: str, child_query: str, commit: bool = True) -> None:
        """Link a child issue under a parent issue via symlink in companion dir."""
        parent = self.find_issue(parent_query)
        child = self.find_issue(child_query)

        companion_dir = parent.path.parent / parent.slug / "children"
        companion_dir.mkdir(parents=True, exist_ok=True)

        symlink_path = companion_dir / child.path.name
        if symlink_path.exists() or symlink_path.is_symlink():
            return

        rel_target = os.path.relpath(child.path, companion_dir)
        symlink_path.symlink_to(rel_target)

        if commit:
            self.run_git(["add", "-A"])
            self.run_git(["commit", "-m", f"issue: link child {child.slug} to parent {parent.slug}"])

    def remove_child(self, parent_query: str, child_query: str, commit: bool = True) -> None:
        """Remove child link from parent issue."""
        parent = self.find_issue(parent_query)
        child = self.find_issue(child_query)

        companion_dir = parent.path.parent / parent.slug / "children"
        symlink_path = companion_dir / child.path.name
        if symlink_path.is_symlink() or symlink_path.exists():
            symlink_path.unlink()

        self._prune_empty_dirs(parent.path.parent / parent.slug)

        if commit:
            self.run_git(["add", "-A"])
            self.run_git(["commit", "-m", f"issue: unlink child {child.slug} from parent {parent.slug}"])

    def move(self, query: str, target_backlog: str, commit: bool = True) -> Issue:
        """Move issue and its companion directory to a new backlog, updating all symlinks."""
        issue = self.find_issue(query)
        target_dir = self.issues_dir / target_backlog
        target_dir.mkdir(parents=True, exist_ok=True)

        new_issue_path = target_dir / issue.path.name
        if new_issue_path.exists() and new_issue_path != issue.path:
            raise FileExistsError(f"Target issue path already exists: {new_issue_path}")

        # 1. Locate all incoming symlinks pointing to this issue
        incoming_refs = self._find_incoming_symlinks(issue.path)

        # 2. Move file using git mv
        self.run_git(["mv", str(issue.path), str(new_issue_path)])

        # 3. Move companion directory if present
        companion_dir = issue.path.parent / issue.slug
        new_companion_dir = target_dir / issue.slug
        if companion_dir.is_dir():
            self.run_git(["mv", str(companion_dir), str(new_companion_dir)])

            # Re-point outgoing symlinks inside new companion directory
            for sub in ("blocked_by", "children"):
                sub_dir = new_companion_dir / sub
                if sub_dir.is_dir():
                    for link in list(sub_dir.iterdir()):
                        if link.is_symlink():
                            target = link.resolve()
                            link.unlink()
                            link.symlink_to(os.path.relpath(target, sub_dir))

        # 4. Re-point incoming symlinks to the new location
        for ref in incoming_refs:
            if ref.is_symlink() or ref.exists():
                ref.unlink()
                ref.symlink_to(os.path.relpath(new_issue_path, ref.parent))

        if commit:
            self.run_git(["add", "-A"])
            self.run_git(["commit", "-m", f"issue: move {issue.slug} to {target_backlog}"])

        return self.find_issue(issue.id)

    def close(self, query: str, comment: Optional[str] = None, commit: bool = True) -> Issue:
        """Close an issue: prune all incoming symlinks, update status, check criteria."""
        issue = self.find_issue(query)

        # 1. Locate and remove all incoming symlinks across the entire issues tree
        incoming_refs = self._find_incoming_symlinks(issue.path)
        for ref in incoming_refs:
            if ref.is_symlink() or ref.exists():
                parent_dir = ref.parent
                ref.unlink()
                self._prune_empty_dirs(parent_dir.parent)

        # 2. Update status to closed and check off criteria
        content = issue.path.read_text(encoding="utf-8")
        content = re.sub(
            r"(##\s+Status\s*\n\s*)([a-zA-Z0-9_-]+)",
            r"\g<1>closed",
            content,
            count=1,
        )
        # Check off acceptance criteria: - [ ] -> - [x]
        content = re.sub(r"(?m)^(\s*-\s*\[)[ ](\]\s*.*)$", r"\g<1>x\g<2>", content)

        # 3. Add closing comment if provided
        if comment:
            now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            user = get_current_user()
            entry = f"### {now_ts} {user}\n{comment.strip()}\n"
            if "## Comments" in content:
                content = content.rstrip() + f"\n\n{entry}"
            else:
                content = content.rstrip() + f"\n\n## Comments\n{entry}"

        issue.path.write_text(content, encoding="utf-8")

        if commit:
            self.run_git(["add", "-A"])
            self.run_git(["commit", "-m", f"issue: close {issue.slug} and prune references"])

        return self.find_issue(issue.id)

    def _find_incoming_symlinks(self, target_path: Path) -> List[Path]:
        """Find all symlinks in the issues repository pointing to target_path."""
        refs: List[Path] = []
        target_resolved = target_path.resolve()
        for root, dirs, files in os.walk(self.issues_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            for name in files:
                p = Path(root) / name
                if p.is_symlink():
                    try:
                        if p.resolve() == target_resolved and p != target_path:
                            refs.append(p)
                    except Exception:
                        pass
        return refs

    def _prune_empty_dirs(self, dir_path: Path) -> None:
        """Remove empty companion subdirectories (blocked_by, children) and companion root."""
        try:
            for sub in ("blocked_by", "children"):
                sub_dir = dir_path / sub
                if sub_dir.is_dir() and not any(sub_dir.iterdir()):
                    sub_dir.rmdir()
            if dir_path.is_dir() and not any(dir_path.iterdir()):
                dir_path.rmdir()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

def cmd_list(tracker: IssueTracker, args: argparse.Namespace) -> int:
    issues = tracker.load_all()
    filtered = list(issues.values())

    if args.status:
        filtered = [i for i in filtered if i.status == args.status.lower()]
    if args.backlog:
        filtered = [i for i in filtered if i.backlog == args.backlog]
    if args.assignee:
        filtered = [i for i in filtered if i.assignee == args.assignee]

    filtered.sort(key=lambda x: x.int_id)

    if args.json:
        print(json.dumps([i.to_dict() for i in filtered], indent=2))
        return 0

    if args.ids_only:
        for i in filtered:
            print(i.id)
        return 0

    if not filtered:
        print("No issues found.")
        return 0

    # Header
    print(f"{'ID':<5} {'STATUS':<12} {'ASSIGNEE':<14} {'BLOCKERS':<9} {'BACKLOG':<14} {'TITLE'}")
    print("-" * 80)
    for i in filtered:
        blockers_str = str(len(i.blocked_by)) if i.blocked_by else "-"
        print(f"#{i.id:<4} {i.status:<12} {i.assignee[:13]:<14} {blockers_str:<9} {i.backlog[:13]:<14} {i.title}")

    return 0


def cmd_ready(tracker: IssueTracker, args: argparse.Namespace) -> int:
    issues = tracker.load_all()
    # Ready: status == 'open' and (no blockers or all blocker issues are closed)
    ready_issues: List[Issue] = []
    for iss in issues.values():
        if iss.status != "open":
            continue
        unresolved_blockers = [
            b_id for b_id in iss.blocked_by
            if b_id in issues and issues[b_id].status != "closed"
        ]
        if not unresolved_blockers:
            ready_issues.append(iss)

    ready_issues.sort(key=lambda x: x.int_id)

    if args.json:
        print(json.dumps([i.to_dict() for i in ready_issues], indent=2))
        return 0

    if args.ids_only:
        for i in ready_issues:
            print(i.id)
        return 0

    if not ready_issues:
        print("No issues currently ready for pickup.")
        return 0

    print(f"{'ID':<5} {'ASSIGNEE':<14} {'BACKLOG':<14} {'TITLE'}")
    print("-" * 65)
    for i in ready_issues:
        print(f"#{i.id:<4} {i.assignee[:13]:<14} {i.backlog[:13]:<14} {i.title}")

    return 0


def cmd_show(tracker: IssueTracker, args: argparse.Namespace) -> int:
    try:
        issue = tracker.find_issue(args.id)
    except KeyError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(issue.to_dict(), indent=2))
        return 0

    if args.raw:
        print(issue.raw_content)
        return 0

    print(f"Issue #{issue.id}: {issue.title}")
    print(f"Path:     {issue.rel_path}")
    print(f"Backlog:  {issue.backlog}")
    print(f"Status:   {issue.status}")
    print(f"Assignee: {issue.assignee}")

    # Relations
    all_issues = tracker.load_all()
    if issue.blocked_by:
        blockers_info = [
            f"#{bid} ({all_issues[bid].status if bid in all_issues else 'unknown'})"
            for bid in issue.blocked_by
        ]
        print(f"Blocked by: {', '.join(blockers_info)}")
    else:
        print("Blocked by: none")

    if issue.blocks:
        blocks_info = [
            f"#{bid} ({all_issues[bid].status if bid in all_issues else 'unknown'})"
            for bid in issue.blocks
        ]
        print(f"Blocks:     {', '.join(blocks_info)}")

    if issue.children:
        print(f"Children:   {', '.join(['#' + c for c in issue.children])}")
    if issue.parents:
        print(f"Parent:     {', '.join(['#' + p for p in issue.parents])}")

    print("\n--- Description ---")
    print(issue.description or "(no description)")

    if issue.acceptance_criteria:
        print("\n--- Acceptance Criteria ---")
        for crit in issue.acceptance_criteria:
            box = "[x]" if crit["checked"] else "[ ]"
            print(f"{box} {crit['text']}")

    if issue.comments:
        print("\n--- Comments ---")
        for comm in issue.comments:
            print(f"[{comm['timestamp']}] {comm['author']}:")
            for line in comm["body"].splitlines():
                print(f"  {line}")

    return 0


def cmd_next_id(tracker: IssueTracker, args: argparse.Namespace) -> int:
    print(tracker.next_id())
    return 0


def cmd_create(tracker: IssueTracker, args: argparse.Namespace) -> int:
    criteria = args.criteria if args.criteria else None
    issue = tracker.create(
        backlog=args.backlog,
        title=args.title,
        assignee=args.assignee or "unassigned",
        description=args.description or "",
        acceptance_criteria=criteria,
        commit=not args.no_commit,
    )
    print(f"Created #{issue.id}: {issue.title} ({issue.rel_path})")
    return 0


def cmd_claim(tracker: IssueTracker, args: argparse.Namespace) -> int:
    issue = tracker.claim(args.id, assignee=args.assignee, commit=not args.no_commit)
    print(f"Claimed #{issue.id} by {issue.assignee} (status: {issue.status})")
    return 0


def cmd_status(tracker: IssueTracker, args: argparse.Namespace) -> int:
    issue = tracker.set_status(args.id, args.status, commit=not args.no_commit)
    print(f"Updated #{issue.id} status to '{issue.status}'")
    return 0


def cmd_assign(tracker: IssueTracker, args: argparse.Namespace) -> int:
    issue = tracker.set_assignee(args.id, args.assignee, commit=not args.no_commit)
    print(f"Assigned #{issue.id} to {issue.assignee}")
    return 0


def cmd_comment(tracker: IssueTracker, args: argparse.Namespace) -> int:
    issue = tracker.add_comment(
        args.id,
        args.message,
        author=args.author,
        commit=not args.no_commit,
    )
    print(f"Appended comment to #{issue.id}")
    return 0


def cmd_block(tracker: IssueTracker, args: argparse.Namespace) -> int:
    tracker.add_blocker(args.target, args.blocker, commit=not args.no_commit)
    print(f"Marked #{args.target} blocked by #{args.blocker}")
    return 0


def cmd_unblock(tracker: IssueTracker, args: argparse.Namespace) -> int:
    tracker.remove_blocker(args.target, args.blocker, commit=not args.no_commit)
    print(f"Removed blocker #{args.blocker} from #{args.target}")
    return 0


def cmd_link(tracker: IssueTracker, args: argparse.Namespace) -> int:
    tracker.add_child(args.parent, args.child, commit=not args.no_commit)
    print(f"Linked child #{args.child} to parent #{args.parent}")
    return 0


def cmd_unlink(tracker: IssueTracker, args: argparse.Namespace) -> int:
    tracker.remove_child(args.parent, args.child, commit=not args.no_commit)
    print(f"Unlinked child #{args.child} from parent #{args.parent}")
    return 0


def cmd_move(tracker: IssueTracker, args: argparse.Namespace) -> int:
    issue = tracker.move(args.id, args.backlog, commit=not args.no_commit)
    print(f"Moved #{issue.id} to {issue.backlog} ({issue.rel_path})")
    return 0


def cmd_close(tracker: IssueTracker, args: argparse.Namespace) -> int:
    issue = tracker.close(args.id, comment=args.comment, commit=not args.no_commit)
    print(f"Closed #{issue.id} and pruned incoming references")
    return 0


def cmd_serve(tracker: IssueTracker, args: argparse.Namespace) -> int:
    import importlib.util
    server_path = Path(__file__).parent / "issue_server.py"
    if not server_path.exists():
        print(f"Error: {server_path} not found", file=sys.stderr)
        return 1

    spec = importlib.util.spec_from_file_location("issue_server", server_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.run_server(port=args.port, host=args.host, open_browser=args.open)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="issue",
        description="Git-stored issue tracking CLI for agents and developers.",
    )
    parser.add_argument("--issues-dir", type=Path, help="Override issues directory")
    subparsers = parser.add_subparsers(dest="command")

    # list
    p_list = subparsers.add_parser("list", aliases=["ls"], help="List issues")
    p_list.add_argument("--status", choices=["open", "in_progress", "blocked", "closed"], help="Filter by status")
    p_list.add_argument("--backlog", help="Filter by backlog directory")
    p_list.add_argument("--assignee", help="Filter by assignee")
    p_list.add_argument("--json", action="store_true", help="Output JSON")
    p_list.add_argument("--ids-only", action="store_true", help="Print only issue IDs")

    # ready
    p_ready = subparsers.add_parser("ready", help="List open issues ready for pickup (no blockers)")
    p_ready.add_argument("--json", action="store_true", help="Output JSON")
    p_ready.add_argument("--ids-only", action="store_true", help="Print only issue IDs")

    # show
    p_show = subparsers.add_parser("show", aliases=["view", "get"], help="Show issue details")
    p_show.add_argument("id", help="Issue ID, slug, or path")
    p_show.add_argument("--json", action="store_true", help="Output JSON")
    p_show.add_argument("--raw", action="store_true", help="Output raw markdown")

    # next-id
    subparsers.add_parser("next-id", help="Print next available issue ID")

    # create
    p_create = subparsers.add_parser("create", aliases=["new"], help="Create a new issue")
    p_create.add_argument("backlog", help="Backlog folder (e.g. milestone_0, bugs, backlog)")
    p_create.add_argument("title", help="Issue title")
    p_create.add_argument("--assignee", default="unassigned", help="Assignee")
    p_create.add_argument("--description", "-d", help="Issue description")
    p_create.add_argument("--criteria", "-c", action="append", help="Acceptance criteria item (repeatable)")
    p_create.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # claim
    p_claim = subparsers.add_parser("claim", help="Claim an issue (set in_progress and assignee)")
    p_claim.add_argument("id", help="Issue ID or slug")
    p_claim.add_argument("assignee", nargs="?", help="Assignee name (defaults to git user)")
    p_claim.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # status
    p_status = subparsers.add_parser("status", help="Change issue status")
    p_status.add_argument("id", help="Issue ID or slug")
    p_status.add_argument("status", choices=["open", "in_progress", "blocked", "closed"], help="New status")
    p_status.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # assign
    p_assign = subparsers.add_parser("assign", help="Change issue assignee")
    p_assign.add_argument("id", help="Issue ID or slug")
    p_assign.add_argument("assignee", help="New assignee")
    p_assign.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # comment
    p_comment = subparsers.add_parser("comment", help="Append a comment to an issue")
    p_comment.add_argument("id", help="Issue ID or slug")
    p_comment.add_argument("message", help="Comment text")
    p_comment.add_argument("--author", help="Comment author name")
    p_comment.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # block
    p_block = subparsers.add_parser("block", help="Mark target issue blocked by blocker issue")
    p_block.add_argument("target", help="Target issue ID (the one waiting)")
    p_block.add_argument("blocker", help="Blocker issue ID (the prerequisite)")
    p_block.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # unblock
    p_unblock = subparsers.add_parser("unblock", help="Remove blocker from target issue")
    p_unblock.add_argument("target", help="Target issue ID")
    p_unblock.add_argument("blocker", help="Blocker issue ID to remove")
    p_unblock.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # link
    p_link = subparsers.add_parser("link", help="Link child issue to parent issue")
    p_link.add_argument("parent", help="Parent issue ID")
    p_link.add_argument("child", help="Child issue ID")
    p_link.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # unlink
    p_unlink = subparsers.add_parser("unlink", help="Unlink child issue from parent issue")
    p_unlink.add_argument("parent", help="Parent issue ID")
    p_unlink.add_argument("child", help="Child issue ID to unlink")
    p_unlink.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # move
    p_move = subparsers.add_parser("move", aliases=["mv"], help="Move issue to another backlog")
    p_move.add_argument("id", help="Issue ID or slug")
    p_move.add_argument("backlog", help="Target backlog directory (e.g. milestone_1)")
    p_move.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # close
    p_close = subparsers.add_parser("close", help="Close issue and prune incoming references")
    p_close.add_argument("id", help="Issue ID or slug")
    p_close.add_argument("comment", nargs="?", help="Optional closing comment")
    p_close.add_argument("--no-commit", action="store_true", help="Do not commit to git")

    # serve
    p_serve = subparsers.add_parser("serve", aliases=["ui"], help="Start read-only web UI server")
    p_serve.add_argument("--port", "-p", type=int, default=8080, help="HTTP port (default: 8080)")
    p_serve.add_argument("--host", default="127.0.0.1", help="HTTP bind host (default: 127.0.0.1)")
    p_serve.add_argument("--open", action="store_true", help="Open browser automatically")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    tracker = IssueTracker(args.issues_dir)

    handlers = {
        "list": cmd_list,
        "ls": cmd_list,
        "ready": cmd_ready,
        "show": cmd_show,
        "view": cmd_show,
        "get": cmd_show,
        "next-id": cmd_next_id,
        "create": cmd_create,
        "new": cmd_create,
        "claim": cmd_claim,
        "status": cmd_status,
        "assign": cmd_assign,
        "comment": cmd_comment,
        "block": cmd_block,
        "unblock": cmd_unblock,
        "link": cmd_link,
        "unlink": cmd_unlink,
        "move": cmd_move,
        "mv": cmd_move,
        "close": cmd_close,
        "serve": cmd_serve,
        "ui": cmd_serve,
    }

    handler = handlers.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    return handler(tracker, args)


if __name__ == "__main__":
    sys.exit(main())
