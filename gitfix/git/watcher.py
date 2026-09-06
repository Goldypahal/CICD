import time
from pathlib import Path
from typing import Callable, Optional
from .repo_manager import GitRepoManager

HOOK_SCRIPT = """#!/bin/sh
# GitFix auto post-commit hook
gitfix fix --auto-commit
"""

class GitWatcher:
    def __init__(self, repo_manager: GitRepoManager):
        self.repo_manager = repo_manager

    def install_post_commit_hook(self) -> bool:
        hooks_dir = self.repo_manager.repo_dir / ".git" / "hooks"
        if not hooks_dir.exists():
            return False
        hook_path = hooks_dir / "post-commit"
        try:
            hook_path.write_text(HOOK_SCRIPT, encoding="utf-8")
            # Set executable permissions on unix/linux/mac
            import stat
            hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)
            return True
        except Exception:
            return True  # Best effort

    def watch(self, callback: Callable[[str], None], poll_interval: float = 2.0):
        last_commit = self.repo_manager.get_current_commit()
        print(f"[GitWatcher] Started monitoring repository at commit: {last_commit[:7]}")
        
        try:
            while True:
                time.sleep(poll_interval)
                curr_commit = self.repo_manager.get_current_commit()
                if curr_commit and curr_commit != last_commit:
                    print(f"\n[GitWatcher] Detected new commit: {curr_commit[:7]}")
                    last_commit = curr_commit
                    callback(curr_commit)
        except KeyboardInterrupt:
            print("\n[GitWatcher] Stopped watching.")
