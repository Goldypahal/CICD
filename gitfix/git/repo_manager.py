import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class GitRepoManager:
    def __init__(self, repo_dir: Optional[Path] = None):
        self.repo_dir = Path(repo_dir or Path.cwd()).resolve()

    def _run_git(self, args: List[str]) -> Tuple[int, str, str]:
        res = subprocess.run(
            ["git"] + args,
            cwd=self.repo_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()

    def is_git_repo(self) -> bool:
        code, stdout, _ = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return code == 0 and stdout == "true"

    def get_current_commit(self) -> str:
        code, stdout, _ = self._run_git(["rev-parse", "HEAD"])
        return stdout if code == 0 else ""

    def get_current_branch(self) -> str:
        code, stdout, _ = self._run_git(["rev-parse", "--abbrev-ref", "HEAD"])
        return stdout if code == 0 else ""

    def get_commit_diff(self, commit_ref: str = "HEAD~1..HEAD") -> str:
        code, stdout, stderr = self._run_git(["diff", commit_ref])
        if code != 0 or not stdout:
            # Fallback to unstaged/staged diff if commit diff unavailable
            code, stdout, _ = self._run_git(["diff", "HEAD"])
        return stdout

    def get_changed_files(self, commit_ref: str = "HEAD~1..HEAD") -> List[str]:
        code, stdout, _ = self._run_git(["diff", "--name-only", commit_ref])
        if code == 0 and stdout:
            return [line.strip() for line in stdout.splitlines() if line.strip()]
        # Fallback
        code, stdout, _ = self._run_git(["diff", "--name-only", "HEAD"])
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    def create_ai_branch(self, commit_hash: str, prefix: str = "ai/fix-") -> str:
        branch_name = f"{prefix}{commit_hash[:7]}"
        # Checkout -b branch_name
        self._run_git(["checkout", "-b", branch_name])
        return branch_name

    def stage_and_commit(self, message: str) -> bool:
        code_add, _, _ = self._run_git(["add", "."])
        if code_add != 0:
            return False
        code_commit, _, _ = self._run_git(["commit", "-m", message])
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
        self._run_git(["reset", "--hard", "HEAD"])
