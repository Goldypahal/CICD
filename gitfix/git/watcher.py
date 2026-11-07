import stat
import time
from typing import Callable

from .repo_manager import GitRepoManager

HOOK_MARKER = "# GitFix auto post-commit hook"
HOOK_SCRIPT = f"""#!/bin/sh
{HOOK_MARKER}
# Skip commits made by GitFix itself, and never block the user's commit.
[ -n "$GITFIX_RUNNING" ] && exit 0
gitfix fix || true
"""


class GitWatcher:
    def __init__(self, repo_manager: GitRepoManager):
        self.repo_manager = repo_manager

    def install_post_commit_hook(self) -> bool:
        """Install the hook. Never overwrites a post-commit hook that GitFix did not write."""
        hooks_dir = self.repo_manager.repo_dir / ".git" / "hooks"
        if not hooks_dir.exists():
            return False
        hook_path = hooks_dir / "post-commit"
        try:
            if hook_path.exists() and HOOK_MARKER not in hook_path.read_text(encoding="utf-8", errors="replace"):
                print(f"[GitWatcher] Existing post-commit hook at {hook_path} left untouched.")
                return False
            hook_path.write_text(HOOK_SCRIPT, encoding="utf-8")
            hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            return True
        except Exception as e:
            print(f"[GitWatcher] Failed to install post-commit hook: {e}")
            return False

    def watch(self, callback: Callable[[str], None], poll_interval: float = 2.0):
        last_commit = self.repo_manager.get_current_commit()
        print(f"[GitWatcher] Started monitoring repository at commit: {last_commit[:7]}")

        try:
            while True:
                time.sleep(poll_interval)
                curr_commit = self.repo_manager.get_current_commit()
                if curr_commit and curr_commit != last_commit:
                    print(f"\n[GitWatcher] Detected new commit: {curr_commit[:7]}")
                    callback(curr_commit)
                    # The callback may itself commit a fix; don't treat that as a new trigger.
                    last_commit = self.repo_manager.get_current_commit()
        except KeyboardInterrupt:
            print("\n[GitWatcher] Stopped watching.")
