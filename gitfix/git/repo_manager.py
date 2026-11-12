import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class GitRepoManager:
    def __init__(self, repo_dir: Optional[Path] = None):
        self.repo_dir = Path(repo_dir or Path.cwd()).resolve()

    def _run_git(self, args: List[str], env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
        res = subprocess.run(
            ["git"] + args,
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, **env} if env else None,
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()

    # ------------------------------------------------------------------ state
    def is_git_repo(self) -> bool:
        code, stdout, _ = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return code == 0 and stdout == "true"

    def get_current_commit(self) -> str:
        code, stdout, _ = self._run_git(["rev-parse", "HEAD"])
        return stdout if code == 0 else ""

    def get_current_branch(self) -> str:
        """Current branch name, or "" when HEAD is detached (as in most CI checkouts)."""
        code, stdout, _ = self._run_git(["symbolic-ref", "--quiet", "--short", "HEAD"])
        return stdout if code == 0 else ""

    def get_current_ref(self) -> str:
        """Something `git checkout` can return to: the branch name, or the commit SHA if detached."""
        return self.get_current_branch() or self.get_current_commit()

    def resolve_ref(self, ref: str) -> str:
        code, stdout, _ = self._run_git(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
        return stdout if code == 0 else ""

    def branch_exists(self, name: str) -> bool:
        code, _, _ = self._run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{name}"])
        return code == 0

    def has_tracked_changes(self) -> bool:
        """True if tracked files have staged or unstaged modifications."""
        code, stdout, _ = self._run_git(["status", "--porcelain", "--untracked-files=no"])
        return code != 0 or bool(stdout.strip())

    def is_working_tree_clean(self) -> bool:
        """Check if working tree has any uncommitted changes or untracked files."""
        code, stdout, _ = self._run_git(["status", "--porcelain"])
        return code == 0 and len(stdout.strip()) == 0

    # ------------------------------------------------------------------ diffs
    def get_commit_diff(self, commit_ref: str = "HEAD~1..HEAD") -> str:
        code, stdout, _ = self._run_git(["diff", commit_ref])
        if code != 0 or not stdout:
            code, stdout, _ = self._run_git(["diff", "HEAD"])
        return stdout

    def get_changed_files(self, commit_ref: str = "HEAD~1..HEAD") -> List[str]:
        code, stdout, _ = self._run_git(["diff", "--name-only", commit_ref])
        if code == 0 and stdout:
            return [line.strip() for line in stdout.splitlines() if line.strip()]
        code, stdout, _ = self._run_git(["diff", "--name-only", "HEAD"])
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    def get_working_diff(self, files: Optional[List[str]] = None) -> str:
        args = ["diff", "HEAD"]
        if files:
            args += ["--"] + files
        _, stdout, _ = self._run_git(args)
        return stdout

    # ------------------------------------------------------------------ branches
    def create_ai_branch(self, commit_hash: str, prefix: str = "ai/fix-") -> str:
        branch_name = f"{prefix}{commit_hash[:7]}"
        code, _, stderr = self._run_git(["checkout", "-b", branch_name])
        if code != 0:
            code_co, _, stderr_co = self._run_git(["checkout", branch_name])
            if code_co != 0:
                raise RuntimeError(
                    f"Failed to create or switch to safety branch '{branch_name}': {stderr} | {stderr_co}"
                )
        return branch_name

    def checkout(self, ref: str) -> bool:
        code, _, _ = self._run_git(["checkout", "--quiet", ref])
        return code == 0

    def delete_branch(self, name: str) -> bool:
        code, _, _ = self._run_git(["branch", "-D", name])
        return code == 0

    def stage_and_commit(self, message: str, files: Optional[List[str]] = None) -> bool:
        if files:
            for f in files:
                code_add, _, _ = self._run_git(["add", "--", f])
                if code_add != 0:
                    return False
        else:
            code_add, _, _ = self._run_git(["add", "-u"])
            if code_add != 0:
                return False
        # GITFIX_RUNNING stops the GitFix post-commit hook from re-triggering on our own commit.
        code_commit, _, _ = self._run_git(["commit", "-m", message], env={"GITFIX_RUNNING": "1"})
        return code_commit == 0

    def get_file_content(self, relative_path: str) -> Optional[str]:
        full_path = self.repo_dir / relative_path
        if full_path.exists() and full_path.is_file():
            try:
                return full_path.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def reset_hard(self):
        """Discard ALL tracked changes. Not used by the repair pipeline (it rolls back only its own edits)."""
        self._run_git(["reset", "--hard", "HEAD"])

    # ------------------------------------------------------------------ worktrees
    def add_detached_worktree(self, target_dir: Path, ref: str) -> Tuple[bool, str]:
        code, _, stderr = self._run_git(["worktree", "add", "--detach", str(target_dir), ref])
        return code == 0, stderr

    def create_worktree(self, branch_name: str, target_dir: Path) -> Tuple[bool, str]:
        """Create a dedicated, clean git worktree for isolated repair operations."""
        code, stdout, stderr = self._run_git(["worktree", "add", "-b", branch_name, str(target_dir)])
        if code != 0:
            code, stdout, stderr = self._run_git(["worktree", "add", str(target_dir), branch_name])
        return (code == 0, stderr if code != 0 else "")

    def remove_worktree(self, target_dir: Path, force: bool = True) -> bool:
        args = ["worktree", "remove", str(target_dir)]
        if force:
            args.append("--force")
        code, _, _ = self._run_git(args)
        self._run_git(["worktree", "prune"])
        return code == 0

    # ------------------------------------------------------------------ remotes
    def push_branch(self, branch_name: str, remote: str = "origin") -> Tuple[bool, str]:
        try:
            res = subprocess.run(
                ["git", "push", "-u", remote, branch_name],
                cwd=self.repo_dir, capture_output=True, text=True, timeout=120,
            )
            return res.returncode == 0, res.stderr.strip()
        except Exception as e:
            return False, str(e)

    def get_github_slug(self, remote: str = "origin") -> Optional[str]:
        """'owner/repo' parsed from a GitHub remote URL, if it is one."""
        code, url, _ = self._run_git(["remote", "get-url", remote])
        if code != 0:
            return None
        m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
        return f"{m.group(1)}/{m.group(2)}" if m else None

    def get_default_branch(self, remote: str = "origin") -> Optional[str]:
        code, stdout, _ = self._run_git(["symbolic-ref", "--quiet", "--short", f"refs/remotes/{remote}/HEAD"])
        if code == 0 and stdout.startswith(f"{remote}/"):
            return stdout[len(remote) + 1:]
        return None
