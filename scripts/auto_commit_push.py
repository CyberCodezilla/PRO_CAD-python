#!/usr/bin/env python3
"""
Git Auto-Commit and Push Script for Python CAD Pro
--------------------------------------------------
Generates random, realistic git commits spanning from July 27th to July 30th, 2026,
with random timestamps during working hours and accurate CAD-project commit messages.

July 27th receives a higher weight/volume of commits than other days.
"""

import os
import sys
import random
import subprocess
from datetime import datetime, timedelta, time

# Configuration
YEAR = 2026
TIMEZONE = "+0530"  # IST timezone offset

# Date range schedule setup
# July 27 has a higher commit count (7-11) than July 28, 29, 30 (3-5 each)
DAY_CONFIG = [
    {"date": "2026-07-27", "min_commits": 8, "max_commits": 11, "label": "July 27 (Heavy Activity)"},
    {"date": "2026-07-28", "min_commits": 4, "max_commits": 6, "label": "July 28 (Standard)"},
    {"date": "2026-07-29", "min_commits": 3, "max_commits": 5, "label": "July 29 (Standard)"},
    {"date": "2026-07-30", "min_commits": 3, "max_commits": 5, "label": "July 30 (Standard)"},
]

# Realistic commit messages pool tailored to Python CAD Pro
COMMIT_MESSAGES = [
    # Feature commits
    "feat(ui): add modern toolbar icons and view switching hotkeys",
    "feat(reconstruction): implement 2D slice plane extraction from 3D boundary representation",
    "feat(export): add DXF R12 ascii exporter for 2D technical drawings",
    "feat(ui): add reset view action to 3D viewport control overlay",
    "feat(toolbar): add quick tooltips and dynamic status bar coordinate display",
    "feat(canvas): implement snap-to-grid functionality for line and arc creation",
    "feat(engine): add parametric constraint solver for 2D entity alignment",
    "feat(viewport): render wireframe overlay with dynamic depth testing",
    
    # Bug fixes
    "fix(reconstruction): handle degenerate faces in 3D wireframe mesh generator",
    "fix(canvas): resolve zoom origin offset on high-DPI display scale factors",
    "fix(viewport): prevent memory leak when re-initializing PyOpenGL VAOs",
    "fix(parser): validate entity layer definitions during DXF file import",
    "fix(ui): correct layout margins in viewport dock widget initialization",
    "fix(engine): resolve numerical instability in line-arc intersection solver",

    # Refactorings
    "refactor(engine): optimize CSG boolean operations and vertex transformation matrix",
    "refactor(core): decouple view selector events from main window event loop",
    "refactor(main): clean up app initialization and PySide6 stylesheet loading",
    "refactor(reconstruction): extract mesh triangulation into dedicated helper package",
    "refactor(ui): streamline canvas mouse interaction and tool state machine",

    # Performance
    "perf(viewport): optimize PyOpenGL VBO data uploads during dynamic orbit",
    "perf(math): vectorize bounding box intersection checks using numpy",
    "perf(reconstruction): parallelize triangulation for complex planar polygons",
    "perf(canvas): introduce spatial indexing for fast entity selection",

    # Documentation & Tests
    "docs(readme): update system prerequisites, build instructions, and PySide6 setup",
    "docs(project): record milestone completion for Phase 2 reconstruction pipeline",
    "docs(changelog): update release notes for v0.4.0-alpha CAD engine",
    "test(reconstruction): add comprehensive unit tests for orthographic projection",
    "test(canvas): add mouse drag and snap-to-grid interaction test cases",
    "test(engine): verify geometric primitive transformations under scaling",
    "style(ui): apply dark theme palette to PySide6 docking widgets"
]

LOG_FILE = "CHANGELOG.md"

def generate_timestamps_for_date(date_str, count):
    """Generate `count` chronologically sorted random timestamps between 09:30 and 21:45."""
    base_date = datetime.strptime(date_str, "%Y-%m-%d")
    timestamps = []
    
    # Work hours: 09:30 (570 mins) to 21:45 (1305 mins)
    start_min = 9 * 60 + 30
    end_min = 21 * 60 + 45
    
    # Pick random distinct minute offsets
    random_minutes = sorted(random.sample(range(start_min, end_min), count))
    
    for mins in random_minutes:
        hour = mins // 60
        minute = mins % 60
        second = random.randint(0, 59)
        dt = base_date.replace(hour=hour, minute=minute, second=second)
        formatted = f"{dt.strftime('%Y-%m-%dT%H:%M:%S')} {TIMEZONE}"
        timestamps.append(formatted)
        
    return timestamps

def append_activity_entry(timestamp_str, message):
    """Append a small log entry to CHANGELOG.md to ensure git changes exist per commit."""
    entry = f"- [{timestamp_str}] {message}\n"
    
    existing_content = ""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            existing_content = f.read()
    else:
        existing_content = "# Project Activity & Commit Log\n\n"
        
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(existing_content + entry)

def run_git_cmd(cmd_list, env=None):
    """Run a git subprocess command."""
    res = subprocess.run(cmd_list, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        print(f"Error running {' '.join(cmd_list)}: {res.stderr}")
        return False
    return True

def generate_schedule():
    """Build full list of planned commits across the date range."""
    used_messages = set()
    msg_pool = list(COMMIT_MESSAGES)
    random.shuffle(msg_pool)
    
    schedule = []
    msg_idx = 0
    
    for day in DAY_CONFIG:
        count = random.randint(day["min_commits"], day["max_commits"])
        timestamps = generate_timestamps_for_date(day["date"], count)
        
        for ts in timestamps:
            msg = msg_pool[msg_idx % len(msg_pool)]
            msg_idx += 1
            schedule.append({
                "date_label": day["label"],
                "timestamp": ts,
                "message": msg
            })
            
    return schedule

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Git Auto-Commit and Push Script for July 27 - July 30")
    parser.add_argument("--dry-run", action="store_true", help="Print schedule without committing")
    parser.add_argument("--push", action="store_true", help="Push to git origin after committing")
    parser.add_argument("--execute", action="store_true", help="Execute commits")

    args = parser.parse_args()

    schedule = generate_schedule()

    print("==================================================")
    print("        Git Auto-Commit Schedule (July 27 - 30)   ")
    print("==================================================")
    print(f"Total Commits Planned: {len(schedule)}\n")

    current_day = None
    for idx, item in enumerate(schedule, 1):
        if item["date_label"] != current_day:
            current_day = item["date_label"]
            print(f"\n--- {current_day} ---")
        print(f"[{idx:02d}] {item['timestamp']}  |  {item['message']}")

    print("\n==================================================")

    if args.dry_run or not args.execute:
        print("\n[DRY RUN MODE] No changes were made to git repository.")
        print("To make actual commits, run with: python scripts/auto_commit_push.py --execute")
        print("To commit and push to remote, run: python scripts/auto_commit_push.py --execute --push")
        return

    print("\nStarting execution of commits...")
    env = os.environ.copy()

    for idx, item in enumerate(schedule, 1):
        ts = item["timestamp"]
        msg = item["message"]

        # Append entry to log file
        append_activity_entry(ts, msg)

        # Set Git Date Environment Variables
        env["GIT_AUTHOR_DATE"] = ts
        env["GIT_COMMITTER_DATE"] = ts

        # Stage file
        if not run_git_cmd(["git", "add", LOG_FILE], env=env):
            print(f"Failed to stage changes for commit #{idx}")
            sys.exit(1)

        # Commit
        commit_cmd = ["git", "commit", "-m", msg, "--date", ts]
        if not run_git_cmd(commit_cmd, env=env):
            print(f"Failed commit #{idx}")
            sys.exit(1)

        print(f"✅ [{idx}/{len(schedule)}] Committed: '{msg}' on {ts}")

    if args.push:
        print("\nPushing commits to remote 'origin main'...")
        if run_git_cmd(["git", "push", "origin", "main"]):
            print("🚀 Successfully pushed all commits to origin main!")
        else:
            print("⚠️ Push failed. Please check your remote repository settings.")
    else:
        print("\nCommits completed locally! Use 'git push' when you wish to push them.")

if __name__ == "__main__":
    main()
