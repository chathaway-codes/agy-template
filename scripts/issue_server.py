#!/usr/bin/env python3
"""
scripts/issue_server.py - Ultra-fast, lightweight read-only web UI for Git issues.

Zero external dependencies. Pure Python standard library.
Features:
- Instant search and filtering (by status, backlog, assignee, text).
- Full Markdown rendering (lists, nested lists, code blocks, bold, italics, links).
- Seamless navigation between linked issues (blocked_by, blocks, children, parents).
- One-click copy buttons tailored for giving IDs, names, paths, and full prompt contexts to LLMs.
- Deep linking via URL hash (#003).
- Keyboard shortcuts (j/k navigation, / search, c copy LLM prompt, p copy path, i copy ID).
"""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import socket
import sys
from typing import Optional
import urllib.parse

from issue import IssueTracker, find_issues_dir


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Git Issue Viewer</title>
<style>
:root {
  --bg-primary: #0d1117;
  --bg-secondary: #161b22;
  --bg-tertiary: #21262d;
  --bg-hover: #30363d;
  --border-color: #30363d;
  --border-muted: #21262d;
  --text-primary: #f0f6fc;
  --text-secondary: #8b949e;
  --text-muted: #6e7681;
  --accent-blue: #58a6ff;
  --accent-green: #3fb950;
  --accent-yellow: #d29922;
  --accent-red: #f85149;
  --accent-purple: #bc8cff;
  --accent-cyan: #39c5cf;
  --code-bg: #1f242c;
  --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Header */
header {
  height: 56px;
  background-color: var(--bg-secondary);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  gap: 16px;
  flex-shrink: 0;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
  font-size: 16px;
}
.logo-badge {
  background: var(--bg-tertiary);
  color: var(--accent-cyan);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 11px;
  font-family: var(--font-mono);
}

.header-search {
  flex: 1;
  max-width: 480px;
  position: relative;
}
.header-search input {
  width: 100%;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  color: var(--text-primary);
  padding: 6px 36px 6px 12px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s ease;
}
.header-search input:focus {
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 2px rgba(88, 166, 255, 0.2);
}
.search-shortcut {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 11px;
  padding: 1px 5px;
  pointer-events: none;
  font-family: var(--font-mono);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}
.stat-pill {
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 6px;
}
.btn-refresh {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  padding: 5px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.btn-refresh:hover {
  background: var(--bg-hover);
}

/* App Body Layout */
.app-container {
  display: flex;
  flex: 1;
  overflow: hidden;
}

/* Left Pane: Issue List */
.sidebar {
  width: 420px;
  border-right: 1px solid var(--border-color);
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-filters {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-row {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  scrollbar-width: none;
}
.filter-row::-webkit-scrollbar { display: none; }

.filter-btn {
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
}
.filter-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}
.filter-btn.active {
  background: var(--bg-tertiary);
  border-color: var(--border-color);
  color: var(--text-primary);
  font-weight: 600;
}
.filter-btn.ready-filter.active {
  border-color: var(--accent-green);
  color: var(--accent-green);
}

.backlog-select {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  outline: none;
  cursor: pointer;
}

.issue-list {
  flex: 1;
  overflow-y: auto;
}

.issue-card {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-muted);
  cursor: pointer;
  transition: background 0.15s ease;
  position: relative;
}
.issue-card:hover {
  background: var(--bg-hover);
}
.issue-card.selected {
  background: rgba(88, 166, 255, 0.1);
  border-left: 3px solid var(--accent-blue);
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.card-badges {
  display: flex;
  align-items: center;
  gap: 6px;
}

.id-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: bold;
  color: var(--accent-blue);
}
.status-pill {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  padding: 1px 6px;
  border-radius: 10px;
  letter-spacing: 0.5px;
}
.status-open { background: rgba(56, 139, 253, 0.15); color: #58a6ff; border: 1px solid rgba(56, 139, 253, 0.3); }
.status-in_progress { background: rgba(210, 153, 34, 0.15); color: #d29922; border: 1px solid rgba(210, 153, 34, 0.3); }
.status-blocked { background: rgba(248, 81, 73, 0.15); color: #f85149; border: 1px solid rgba(248, 81, 73, 0.3); }
.status-closed { background: rgba(110, 118, 129, 0.2); color: #8b949e; border: 1px solid rgba(110, 118, 129, 0.3); }

.ready-pill {
  font-size: 10px;
  font-weight: bold;
  background: rgba(63, 185, 80, 0.15);
  color: var(--accent-green);
  border: 1px solid rgba(63, 185, 80, 0.4);
  padding: 1px 5px;
  border-radius: 10px;
}

.backlog-pill {
  font-size: 10px;
  color: var(--text-muted);
  background: var(--bg-tertiary);
  padding: 1px 5px;
  border-radius: 4px;
}

.card-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 6px;
  line-height: 1.4;
}

.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
}
.card-dep-count {
  display: flex;
  gap: 8px;
}
.dep-counter {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.dep-counter.blocked { color: var(--accent-red); }
.dep-counter.blocks { color: var(--accent-yellow); }

.card-quick-copy {
  opacity: 0;
  transition: opacity 0.15s ease;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
}
.issue-card:hover .card-quick-copy {
  opacity: 1;
}
.card-quick-copy:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

/* Right Pane: Issue Detail Inspector */
.detail-pane {
  flex: 1;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.detail-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-muted);
  gap: 12px;
}

.detail-container {
  padding: 24px 32px;
  max-width: 900px;
}

.detail-header {
  border-bottom: 1px solid var(--border-color);
  padding-bottom: 16px;
  margin-bottom: 20px;
}
.detail-title-line {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}
.detail-id {
  font-family: var(--font-mono);
  font-size: 20px;
  font-weight: 700;
  color: var(--accent-blue);
}
.detail-title {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.detail-badges {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* LLM Copy Box */
.copy-box {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 24px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}
.copy-box-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--accent-cyan);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.copy-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.btn-copy {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-family: var(--font-mono);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s ease;
}
.btn-copy:hover {
  background: var(--bg-hover);
  border-color: var(--accent-blue);
}
.btn-copy.copied {
  background: rgba(63, 185, 80, 0.2);
  border-color: var(--accent-green);
  color: var(--accent-green);
}
.btn-copy-primary {
  background: rgba(88, 166, 255, 0.15);
  border-color: rgba(88, 166, 255, 0.4);
  color: var(--accent-blue);
  font-weight: 600;
}
.btn-copy-primary:hover {
  background: rgba(88, 166, 255, 0.25);
}

/* Dependencies section */
.deps-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.dep-card-group {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 12px;
}
.dep-group-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.dep-group-title.blocked_by { color: var(--accent-red); }
.dep-group-title.blocks { color: var(--accent-yellow); }
.dep-group-title.children { color: var(--accent-purple); }

.dep-links-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.dep-link-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 8px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  text-decoration: none;
  color: var(--text-primary);
  font-size: 12px;
  transition: background 0.15s ease;
  border: 1px solid transparent;
}
.dep-link-item:hover {
  background: var(--bg-hover);
  border-color: var(--border-color);
}
.dep-link-item-left {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dep-empty {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  padding: 4px 0;
}

/* Content view */
.content-section {
  margin-bottom: 24px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border-muted);
  padding-bottom: 4px;
}

.markdown-body {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.6;
}
.markdown-body p {
  margin-bottom: 12px;
}
.markdown-body ul, .markdown-body ol {
  margin-bottom: 12px;
  padding-left: 24px;
}
.markdown-body li {
  margin-bottom: 4px;
}
.markdown-body ul ul, .markdown-body ol ul, .markdown-body ul ol, .markdown-body ol ol {
  margin-top: 4px;
  margin-bottom: 4px;
  padding-left: 20px;
}
.markdown-body strong {
  color: #fff;
  font-weight: 600;
}
.markdown-body em {
  color: var(--accent-cyan);
  font-style: italic;
}
.markdown-body code {
  background: var(--code-bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent-cyan);
  border: 1px solid var(--border-muted);
}
.markdown-body pre {
  background: var(--code-bg);
  border: 1px solid var(--border-color);
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin-bottom: 14px;
}
.markdown-body pre code {
  padding: 0;
  background: none;
  border: none;
  color: var(--text-primary);
}
.markdown-body a {
  color: var(--accent-blue);
  text-decoration: none;
}
.markdown-body a:hover {
  text-decoration: underline;
}
.markdown-body blockquote {
  border-left: 3px solid var(--accent-blue);
  padding-left: 12px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}

.criteria-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.criteria-item {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-radius: 6px;
  border: 1px solid var(--border-muted);
  font-size: 13px;
}
.criteria-item.checked {
  color: var(--text-muted);
  text-decoration: line-through;
}
.criteria-check {
  font-family: var(--font-mono);
  font-weight: bold;
}
.criteria-item.checked .criteria-check {
  color: var(--accent-green);
}

/* Comments */
.comments-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.comment-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  overflow: hidden;
}
.comment-header {
  background: var(--bg-tertiary);
  padding: 8px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  border-bottom: 1px solid var(--border-muted);
}
.comment-author {
  font-weight: 600;
  color: var(--accent-blue);
  display: flex;
  align-items: center;
  gap: 6px;
}
.comment-time {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}
.comment-body {
  padding: 12px;
  font-size: 13px;
  white-space: pre-wrap;
}

/* Raw Markdown Tab */
.tabs-bar {
  display: flex;
  gap: 12px;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 16px;
}
.tab-btn {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  padding: 8px 4px;
  font-size: 13px;
  cursor: pointer;
}
.tab-btn.active {
  border-bottom-color: var(--accent-blue);
  color: var(--text-primary);
  font-weight: 600;
}
.raw-markdown-view {
  background: var(--code-bg);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 16px;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre-wrap;
  color: var(--text-primary);
  line-height: 1.5;
}

/* Toast Notification */
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: var(--accent-green);
  color: #041407;
  padding: 10px 18px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 13px;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.4);
  transform: translateY(100px);
  opacity: 0;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  pointer-events: none;
  z-index: 1000;
}
.toast.show {
  transform: translateY(0);
  opacity: 1;
}

/* Keyboard hint bar */
.key-hints {
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  gap: 12px;
}
.key-hints kbd {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-color);
  border-radius: 3px;
  padding: 1px 4px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
}
</style>
</head>
<body>

<header>
  <div class="logo-area">
    <span>Issues</span>
    <span class="logo-badge">issues-data</span>
  </div>

  <div class="header-search">
    <input type="text" id="searchInput" placeholder="Filter issues (title, ID, backlog, assignee)..." autocomplete="off">
    <span class="search-shortcut">/</span>
  </div>

  <div class="header-actions">
    <div class="key-hints">
      <span><kbd>j</kbd>/<kbd>k</kbd> navigate</span>
      <span><kbd>c</kbd> copy LLM</span>
      <span><kbd>p</kbd> copy path</span>
    </div>
    <div class="stat-pill" id="statSummary">Loading...</div>
    <button class="btn-refresh" id="refreshBtn" title="Reload issues from disk">↻ Reload</button>
  </div>
</header>

<div class="app-container">
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-filters">
      <div class="filter-row">
        <button class="filter-btn active" data-status="all">All</button>
        <button class="filter-btn ready-filter" data-status="ready">⚡ Ready</button>
        <button class="filter-btn" data-status="open">Open</button>
        <button class="filter-btn" data-status="in_progress">In Progress</button>
        <button class="filter-btn" data-status="blocked">Blocked</button>
        <button class="filter-btn" data-status="closed">Closed</button>
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <select class="backlog-select" id="backlogSelect">
          <option value="all">All Backlogs</option>
        </select>
        <span style="font-size: 11px; color: var(--text-muted);" id="visibleCount">0 issues</span>
      </div>
    </div>

    <div class="issue-list" id="issueList"></div>
  </aside>

  <!-- Detail Inspector -->
  <main class="detail-pane" id="detailPane">
    <div class="detail-placeholder" id="placeholder">
      <p style="font-size: 16px;">Select an issue to inspect details</p>
      <p style="font-size: 12px;">Use <kbd>j</kbd> and <kbd>k</kbd> to cycle through issues</p>
    </div>
    <div class="detail-container" id="detailContent" style="display: none;"></div>
  </main>
</div>

<div class="toast" id="toast">Copied to clipboard!</div>

<script>
let issuesData = [];
let selectedId = null;
let currentFilter = 'all';
let currentBacklog = 'all';
let currentTab = 'rendered';

async function fetchIssues() {
  try {
    const res = await fetch('/api/issues');
    issuesData = await res.json();
    populateBacklogs();
    updateStats();
    renderList();

    // Select based on URL hash or default
    const hash = window.location.hash.replace(/^#/, '');
    if (hash) {
      selectIssue(hash, false);
    } else if (issuesData.length > 0 && !selectedId) {
      selectIssue(issuesData[0].id, false);
    }
  } catch (err) {
    console.error('Failed to load issues:', err);
  }
}

function updateStats() {
  const total = issuesData.length;
  const ready = issuesData.filter(i => isIssueReady(i)).length;
  const closed = issuesData.filter(i => i.status === 'closed').length;
  document.getElementById('statSummary').innerHTML = 
    `<span>${total} issues</span> · <span style="color:var(--accent-green);">${ready} ready</span> · <span>${closed} closed</span>`;
}

function populateBacklogs() {
  const select = document.getElementById('backlogSelect');
  const backlogs = Array.from(new Set(issuesData.map(i => i.backlog))).sort();
  const currentVal = select.value;
  select.innerHTML = '<option value="all">All Backlogs</option>';
  backlogs.forEach(b => {
    const opt = document.createElement('option');
    opt.value = b;
    opt.textContent = b;
    select.appendChild(opt);
  });
  if (backlogs.includes(currentVal)) {
    select.value = currentVal;
  }
}

function isIssueReady(issue) {
  if (issue.status !== 'open') return false;
  if (!issue.blocked_by || issue.blocked_by.length === 0) return true;
  const issueMap = new Map(issuesData.map(i => [i.id, i]));
  return issue.blocked_by.every(bid => {
    const blocker = issueMap.get(bid);
    return blocker && blocker.status === 'closed';
  });
}

function getFilteredIssues() {
  const query = document.getElementById('searchInput').value.trim().toLowerCase();
  return issuesData.filter(issue => {
    if (currentFilter === 'ready') {
      if (!isIssueReady(issue)) return false;
    } else if (currentFilter !== 'all') {
      if (issue.status !== currentFilter) return false;
    }

    if (currentBacklog !== 'all' && issue.backlog !== currentBacklog) {
      return false;
    }

    if (query) {
      const matchId = issue.id.toLowerCase().includes(query);
      const matchTitle = issue.title.toLowerCase().includes(query);
      const matchBacklog = issue.backlog.toLowerCase().includes(query);
      const matchAssignee = issue.assignee.toLowerCase().includes(query);
      const matchDesc = (issue.description || '').toLowerCase().includes(query);
      return matchId || matchTitle || matchBacklog || matchAssignee || matchDesc;
    }

    return true;
  });
}

function renderList() {
  const container = document.getElementById('issueList');
  const filtered = getFilteredIssues();
  document.getElementById('visibleCount').textContent = `${filtered.length} issues`;

  container.innerHTML = '';
  filtered.forEach(issue => {
    const card = document.createElement('div');
    card.className = `issue-card ${issue.id === selectedId ? 'selected' : ''}`;
    card.id = `card-${issue.id}`;
    card.onclick = () => selectIssue(issue.id, true);

    const readyBadge = isIssueReady(issue) ? `<span class="ready-pill">READY</span>` : '';
    const blockerCount = (issue.blocked_by && issue.blocked_by.length) || 0;
    const blocksCount = (issue.blocks && issue.blocks.length) || 0;

    let depHtml = '';
    if (blockerCount > 0) {
      depHtml += `<span class="dep-counter blocked" title="Blocked by ${blockerCount} issue(s)">⛔ ${blockerCount}</span>`;
    }
    if (blocksCount > 0) {
      depHtml += `<span class="dep-counter blocks" title="Blocks ${blocksCount} issue(s)">↳ ${blocksCount}</span>`;
    }

    card.innerHTML = `
      <div class="card-top">
        <div class="card-badges">
          <span class="id-badge">#${issue.id}</span>
          <span class="status-pill status-${issue.status}">${issue.status}</span>
          ${readyBadge}
          <span class="backlog-pill">${issue.backlog}</span>
        </div>
        <button class="card-quick-copy" title="Copy #ID: Title" onclick="event.stopPropagation(); copyCardTitle('${issue.id}')">📋</button>
      </div>
      <div class="card-title">${escapeHtml(issue.title)}</div>
      <div class="card-meta">
        <span>👤 ${escapeHtml(issue.assignee)}</span>
        <div class="card-dep-count">${depHtml}</div>
      </div>
    `;
    container.appendChild(card);
  });
}

function selectIssue(id, updateHash = true) {
  const issue = issuesData.find(i => i.id === id || i.slug === id);
  if (!issue) return;

  selectedId = issue.id;
  if (updateHash) {
    window.location.hash = issue.id;
  }

  document.querySelectorAll('.issue-card').forEach(c => c.classList.remove('selected'));
  const activeCard = document.getElementById(`card-${issue.id}`);
  if (activeCard) {
    activeCard.classList.add('selected');
    activeCard.scrollIntoView({ block: 'nearest' });
  }

  renderDetail(issue);
}

function getSelectedIssue() {
  return issuesData.find(i => i.id === selectedId);
}

function buildLLMPrompt(issue) {
  const issueMap = new Map(issuesData.map(i => [i.id, i]));

  const blockersList = (issue.blocked_by || []).map(bid => {
    const b = issueMap.get(bid);
    return `#${bid} (${b ? b.status : 'unknown'})`;
  }).join(', ') || 'none';

  const blocksList = (issue.blocks || []).map(bid => {
    const b = issueMap.get(bid);
    return `#${bid} (${b ? b.status : 'unknown'})`;
  }).join(', ') || 'none';

  const criteriaText = (issue.acceptance_criteria || []).map(c => 
    `- [${c.checked ? 'x' : ' '}] ${c.text}`
  ).join('\n');

  return `### Issue #${issue.id}: ${issue.title}
- **Path**: \`${issue.rel_path}\`
- **Backlog**: \`${issue.backlog}\`
- **Status**: \`${issue.status}\`
- **Assignee**: \`${issue.assignee}\`
- **Blocked by**: ${blockersList}
- **Blocks**: ${blocksList}

#### Description
${issue.description || '(no description)'}

#### Acceptance Criteria
${criteriaText || '- [ ] Implementation complete and verified'}
`;
}

function copyLLMPrompt(btn) {
  const issue = getSelectedIssue();
  if (!issue) return;
  copyAndNotify(btn, buildLLMPrompt(issue), 'Copied Full LLM Context!');
}

function copyIssueId(btn) {
  const issue = getSelectedIssue();
  if (!issue) return;
  copyAndNotify(btn, issue.id, `Copied ID #${issue.id}!`);
}

function copyIssueName(btn) {
  const issue = getSelectedIssue();
  if (!issue) return;
  copyAndNotify(btn, `#${issue.id}: ${issue.title}`, 'Copied Title!');
}

function copyIssuePath(btn) {
  const issue = getSelectedIssue();
  if (!issue) return;
  copyAndNotify(btn, issue.rel_path, 'Copied Relative Path!');
}

function copyAbsolutePath(btn) {
  const issue = getSelectedIssue();
  if (!issue) return;
  copyAndNotify(btn, issue.path, 'Copied Absolute Path!');
}

function copyCardTitle(id) {
  const issue = issuesData.find(i => i.id === id);
  if (issue) {
    copyText(`#${issue.id}: ${issue.title}`);
    showToast(`Copied #${issue.id}: ${issue.title}`);
  }
}

function copyRawMarkdown(btn) {
  const issue = getSelectedIssue();
  if (!issue) return;
  copyAndNotify(btn, issue.raw_content || '', 'Copied Raw Markdown!');
}

function renderDetail(issue) {
  document.getElementById('placeholder').style.display = 'none';
  const detail = document.getElementById('detailContent');
  detail.style.display = 'block';

  const ready = isIssueReady(issue);
  const issueMap = new Map(issuesData.map(i => [i.id, i]));

  function renderDepLinks(ids, type) {
    if (!ids || ids.length === 0) {
      return '<div class="dep-empty">None</div>';
    }
    return ids.map(id => {
      const dep = issueMap.get(id);
      const title = dep ? dep.title : id;
      const status = dep ? dep.status : 'unknown';
      return `
        <a href="#${id}" class="dep-link-item" onclick="selectIssue('${id}'); return false;">
          <div class="dep-link-item-left">
            <span class="id-badge">#${id}</span>
            <span title="${escapeHtml(title)}">${escapeHtml(title)}</span>
          </div>
          <span class="status-pill status-${status}">${status}</span>
        </a>
      `;
    }).join('');
  }

  const criteriaHtml = (issue.acceptance_criteria || []).map(c => `
    <div class="criteria-item ${c.checked ? 'checked' : ''}">
      <span class="criteria-check">${c.checked ? '☑' : '☐'}</span>
      <span>${escapeHtml(c.text)}</span>
    </div>
  `).join('') || '<div style="color:var(--text-muted);font-style:italic;">No criteria specified</div>';

  const commentsHtml = (issue.comments || []).map(c => `
    <div class="comment-card">
      <div class="comment-header">
        <span class="comment-author">👤 ${escapeHtml(c.author || 'unknown')}</span>
        <span class="comment-time">${escapeHtml(c.timestamp)}</span>
      </div>
      <div class="comment-body">${escapeHtml(c.body)}</div>
    </div>
  `).join('') || '<div style="color:var(--text-muted);font-style:italic;">No comments yet</div>';

  const descHtml = renderMarkdown(issue.description || '*(No description provided)*');

  detail.innerHTML = `
    <div class="detail-header">
      <div class="detail-title-line">
        <span class="detail-id">#${issue.id}</span>
        <h1 class="detail-title">${escapeHtml(issue.title)}</h1>
      </div>
      <div class="detail-badges">
        <span class="status-pill status-${issue.status}">${issue.status}</span>
        ${ready ? '<span class="ready-pill">READY FOR PICKUP</span>' : ''}
        <span class="backlog-pill">📁 ${escapeHtml(issue.backlog)}</span>
        <span style="font-size:12px;color:var(--text-secondary);">👤 ${escapeHtml(issue.assignee)}</span>
        <span style="font-size:12px;color:var(--text-muted);font-family:var(--font-mono);">${escapeHtml(issue.rel_path)}</span>
      </div>
    </div>

    <!-- LLM Quick-Copy Action Box -->
    <div class="copy-box">
      <div class="copy-box-title">
        <span>🤖 Copy to LLM / Agent Prompt</span>
        <span style="font-size:10px;color:var(--text-muted);text-transform:none;">Click any button to copy</span>
      </div>
      <div class="copy-buttons">
        <button class="btn-copy btn-copy-primary" onclick="copyLLMPrompt(this)">
          🤖 Copy for LLM Prompt
        </button>
        <button class="btn-copy" onclick="copyIssueId(this)">
          #${issue.id}
        </button>
        <button class="btn-copy" onclick="copyIssueName(this)">
          📋 Name
        </button>
        <button class="btn-copy" onclick="copyIssuePath(this)">
          📄 Path (${issue.rel_path})
        </button>
        <button class="btn-copy" onclick="copyAbsolutePath(this)">
          📂 Absolute Path
        </button>
      </div>
    </div>

    <!-- Dependencies & Graph Relations -->
    <div class="deps-section">
      <div class="dep-card-group">
        <div class="dep-group-title blocked_by">⛔ Blocked By (${issue.blocked_by ? issue.blocked_by.length : 0})</div>
        <div class="dep-links-list">${renderDepLinks(issue.blocked_by, 'blocked_by')}</div>
      </div>
      <div class="dep-card-group">
        <div class="dep-group-title blocks">↳ Blocks (${issue.blocks ? issue.blocks.length : 0})</div>
        <div class="dep-links-list">${renderDepLinks(issue.blocks, 'blocks')}</div>
      </div>
      <div class="dep-card-group">
        <div class="dep-group-title children">↳ Children / Subtasks (${issue.children ? issue.children.length : 0})</div>
        <div class="dep-links-list">${renderDepLinks(issue.children, 'children')}</div>
      </div>
      <div class="dep-card-group">
        <div class="dep-group-title">↰ Parent Issue</div>
        <div class="dep-links-list">${renderDepLinks(issue.parents, 'parent')}</div>
      </div>
    </div>

    <!-- View Tabs: Rendered vs Raw Markdown -->
    <div class="tabs-bar">
      <button class="tab-btn ${currentTab === 'rendered' ? 'active' : ''}" onclick="switchTab('rendered')">Rendered View</button>
      <button class="tab-btn ${currentTab === 'raw' ? 'active' : ''}" onclick="switchTab('raw')">Raw Markdown</button>
    </div>

    <!-- Tab 1: Rendered View -->
    <div id="tab-rendered" style="display: ${currentTab === 'rendered' ? 'block' : 'none'};">
      <div class="content-section">
        <div class="section-title">Description</div>
        <div class="markdown-body">${descHtml}</div>
      </div>

      <div class="content-section">
        <div class="section-title">Acceptance Criteria</div>
        <div class="criteria-list">${criteriaHtml}</div>
      </div>

      <div class="content-section">
        <div class="section-title">Comments (${(issue.comments || []).length})</div>
        <div class="comments-list">${commentsHtml}</div>
      </div>
    </div>

    <!-- Tab 2: Raw Markdown -->
    <div id="tab-raw" style="display: ${currentTab === 'raw' ? 'block' : 'none'};">
      <div style="margin-bottom: 10px; display: flex; justify-content: flex-end;">
        <button class="btn-copy" onclick="copyRawMarkdown(this)">
          📋 Copy Raw Markdown
        </button>
      </div>
      <pre class="raw-markdown-view"><code id="rawCodeBlock">${escapeHtml(issue.raw_content || '')}</code></pre>
    </div>
  `;

  if (!issue.raw_content) {
    fetch(`/api/raw/${issue.id}`)
      .then(res => res.text())
      .then(text => {
        issue.raw_content = text;
        const el = document.getElementById('rawCodeBlock');
        if (el) el.textContent = text;
      })
      .catch(console.error);
  }
}

function switchTab(tab) {
  currentTab = tab;
  const tabRendered = document.getElementById('tab-rendered');
  const tabRaw = document.getElementById('tab-raw');
  const btns = document.querySelectorAll('.tab-btn');
  if (tabRendered && tabRaw) {
    tabRendered.style.display = tab === 'rendered' ? 'block' : 'none';
    tabRaw.style.display = tab === 'raw' ? 'block' : 'none';
    btns.forEach(b => {
      if (tab === 'rendered') {
        b.classList.toggle('active', b.textContent.includes('Rendered'));
      } else {
        b.classList.toggle('active', b.textContent.includes('Raw'));
      }
    });
  }
}

function renderMarkdown(md) {
  if (!md) return '';
  md = md.replace(/\r\n/g, '\n');

  // 1. Extract fenced code blocks
  const codeBlocks = [];
  md = md.replace(/```([a-zA-Z0-9_+-]*)\n([\s\S]*?)\n```/g, (match, lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre><code class="language-${escapeHtml(lang)}">${escapeHtml(code)}</code></pre>`);
    return `<!--CODEBLOCK_${idx}-->`;
  });

  // 2. Extract inline code
  const inlineCodes = [];
  md = md.replace(/`([^`\n]+)`/g, (match, code) => {
    const idx = inlineCodes.length;
    inlineCodes.push(`<code>${escapeHtml(code)}</code>`);
    return `<!--INLINECODE_${idx}-->`;
  });

  // 3. Escape HTML
  md = escapeHtml(md);

  // 4. Block formatting (Headers, blockquotes)
  md = md.replace(/^#### (.*$)/gim, '<h4>$1</h4>');
  md = md.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  md = md.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  md = md.replace(/^# (.*$)/gim, '<h1>$1</h1>');
  md = md.replace(/^\> (.*$)/gim, '<blockquote>$1</blockquote>');

  // 5. Inline formatting (bold, italic, links)
  md = md.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
  md = md.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  md = md.replace(/__([^_]+)__/g, '<strong>$1</strong>');
  md = md.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  md = md.replace(/_([^_]+)_/g, '<em>$1</em>');
  md = md.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  // 6. Process line-by-line for lists (handles loose lists without prior blank line & nested lists)
  const lines = md.split('\n');
  const result = [];
  const listStack = []; // array of { indent: number, tag: 'ul' | 'ol' }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const listMatch = line.match(/^(\s*)([-*+]|\d+\.)\s+(.*)$/);

    if (listMatch) {
      const indent = listMatch[1].length;
      const isOrdered = /^\d+\./.test(listMatch[2]);
      const tag = isOrdered ? 'ol' : 'ul';
      const content = listMatch[3];

      if (listStack.length === 0) {
        listStack.push({ indent, tag });
        result.push(`<${tag}>`);
      } else if (indent > listStack[listStack.length - 1].indent) {
        listStack.push({ indent, tag });
        result.push(`<${tag}>`);
      } else {
        while (listStack.length > 0 && indent < listStack[listStack.length - 1].indent) {
          const top = listStack.pop();
          result.push(`</${top.tag}>`);
        }
      }
      result.push(`<li>${content}</li>`);
    } else {
      while (listStack.length > 0) {
        const top = listStack.pop();
        result.push(`</${top.tag}>`);
      }
      const trimmed = line.trim();
      if (!trimmed) {
        // empty line
      } else if (trimmed.startsWith('<h') || trimmed.startsWith('<blockquote') || trimmed.startsWith('<!--CODEBLOCK')) {
        result.push(trimmed);
      } else {
        result.push(`<p>${trimmed}</p>`);
      }
    }
  }

  while (listStack.length > 0) {
    const top = listStack.pop();
    result.push(`</${top.tag}>`);
  }

  let html = result.join('\n');

  // 7. Restore code blocks and inline code
  html = html.replace(/<!--CODEBLOCK_(\d+)-->/g, (_, idx) => codeBlocks[idx]);
  html = html.replace(/<!--INLINECODE_(\d+)-->/g, (_, idx) => inlineCodes[idx]);

  return html;
}

function copyAndNotify(button, text, toastMsg = 'Copied to clipboard!') {
  copyText(text);
  showToast(toastMsg);
  if (button) {
    const origText = button.innerHTML;
    button.classList.add('copied');
    button.innerHTML = '✓ Copied!';
    setTimeout(() => {
      button.classList.remove('copied');
      button.innerHTML = origText;
    }, 1800);
  }
}

function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).catch(() => fallbackCopyText(text));
  } else {
    fallbackCopyText(text);
  }
}

function fallbackCopyText(text) {
  const el = document.createElement('textarea');
  el.value = text;
  el.setAttribute('readonly', '');
  el.style.position = 'fixed';
  el.style.left = '-9999px';
  el.style.top = '0';
  document.body.appendChild(el);
  el.focus();
  el.select();
  try {
    document.execCommand('copy');
  } catch (err) {
    console.error('Fallback copy failed', err);
  }
  document.body.removeChild(el);
}

function showToast(msg) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2000);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Event Listeners
document.getElementById('searchInput').addEventListener('input', () => {
  renderList();
});

document.getElementById('backlogSelect').addEventListener('change', (e) => {
  currentBacklog = e.target.value;
  renderList();
});

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', (e) => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.status;
    renderList();
  });
});

document.getElementById('refreshBtn').addEventListener('click', () => {
  fetchIssues();
  showToast('Reloaded issues!');
});

// Keyboard Navigation
window.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
    if (e.key === 'Escape') {
      e.target.blur();
    }
    return;
  }

  if (e.key === '/') {
    e.preventDefault();
    document.getElementById('searchInput').focus();
    return;
  }

  const filtered = getFilteredIssues();
  if (filtered.length === 0) return;

  const currentIndex = filtered.findIndex(i => i.id === selectedId);

  if (e.key === 'j' || e.key === 'ArrowDown') {
    e.preventDefault();
    const nextIdx = (currentIndex + 1) < filtered.length ? (currentIndex + 1) : 0;
    selectIssue(filtered[nextIdx].id);
  } else if (e.key === 'k' || e.key === 'ArrowUp') {
    e.preventDefault();
    const prevIdx = (currentIndex - 1) >= 0 ? (currentIndex - 1) : filtered.length - 1;
    selectIssue(filtered[prevIdx].id);
  } else if (e.key === 'c') {
    const btn = document.querySelector('.btn-copy-primary');
    if (btn) copyLLMPrompt(btn);
  } else if (e.key === 'p') {
    const issue = getSelectedIssue();
    if (issue) {
      copyText(issue.rel_path);
      showToast(`Copied path: ${issue.rel_path}`);
    }
  } else if (e.key === 'i') {
    const issue = getSelectedIssue();
    if (issue) {
      copyText(issue.id);
      showToast(`Copied ID #${issue.id}`);
    }
  }
});

window.addEventListener('hashchange', () => {
  const hash = window.location.hash.replace(/^#/, '');
  if (hash && hash !== selectedId) {
    selectIssue(hash, false);
  }
});

// Initial boot
fetchIssues();
</script>
</body>
</html>
"""


class IssueRequestHandler(BaseHTTPRequestHandler):
    tracker: IssueTracker

    def log_message(self, format, *args):
        # Quiet server logging unless error
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write(f"[HTTP {args[1]}] {args[0]}\n")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
            return

        if path == "/api/issues":
            issues = self.tracker.load_all()
            data = [iss.to_dict() for iss in sorted(issues.values(), key=lambda x: x.int_id)]
            payload = json.dumps(data).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(payload)
            return

        if path.startswith("/api/issues/"):
            issue_id = path.split("/api/issues/", 1)[1]
            try:
                issue = self.tracker.find_issue(issue_id)
                payload = json.dumps(issue.to_dict()).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(payload)
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND, f"Issue {issue_id} not found")
            return

        if path.startswith("/api/raw/"):
            issue_id = path.split("/api/raw/", 1)[1]
            try:
                issue = self.tracker.find_issue(issue_id)
                payload = issue.raw_content.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.end_headers()
                self.wfile.write(payload)
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND, f"Issue {issue_id} not found")
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


def find_available_port(start_port: int = 8080, host: str = "127.0.0.1") -> int:
    port = start_port
    while port < start_port + 50:
        if not is_port_in_use(port, host):
            return port
        port += 1
    return start_port


def run_server(port: int = 8080, host: str = "127.0.0.1", open_browser: bool = False) -> int:
    issues_dir = find_issues_dir()
    if not issues_dir.is_dir():
        print(f"Error: issues directory not found at {issues_dir}", file=sys.stderr)
        return 1

    actual_port = find_available_port(port, host)
    handler = IssueRequestHandler
    handler.tracker = IssueTracker(issues_dir)

    server = HTTPServer((host, actual_port), handler)
    url = f"http://{host}:{actual_port}"
    print(f"Git Issue Viewer running at: {url}")
    print(f"Mounted issues worktree:     {issues_dir}")
    print("Press Ctrl+C to stop.")

    if open_browser:
        import webbrowser
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Git Issue Viewer Web UI")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--open", action="store_true", help="Open browser automatically")
    args = parser.parse_args()
    return run_server(port=args.port, host=args.host, open_browser=args.open)


if __name__ == "__main__":
    sys.exit(main())
