import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .repo_manager import GitRepoManager


@dataclass
class PRResult:
    success: bool
    branch: str
    pr_url: Optional[str]
    message: str
    compare_url: Optional[str] = None


class GitHubPRManager:
    """Pushes the safety branch and opens a GitHub Pull Request via the `gh` CLI."""

    def __init__(self, repo_dir: Path):
        self.repo_dir = Path(repo_dir).resolve()
        self.repo_manager = GitRepoManager(self.repo_dir)

    def compare_url(self, branch_name: str, base_branch: str) -> Optional[str]:
        slug = self.repo_manager.get_github_slug()
        if not slug:
            return None
        return f"https://github.com/{slug}/compare/{base_branch}...{branch_name}?expand=1"

    def create_pull_request(self, branch_name: str, title: str, body: str, base_branch: str = "main") -> PRResult:
        print(f"[GitHubPRManager] 🚀 Pushing '{branch_name}' and opening a PR against '{base_branch}'...")

        pushed, err = self.repo_manager.push_branch(branch_name)
        if not pushed:
            return PRResult(False, branch_name, None, f"Git push failed: {err}")

        compare = self.compare_url(branch_name, base_branch)
        try:
            gh_res = subprocess.run(
                ["gh", "pr", "create", "--title", title, "--body", body, "--base", base_branch, "--head", branch_name],
                cwd=self.repo_dir, capture_output=True, text=True, timeout=60,
            )
        except FileNotFoundError:
            return PRResult(
                False, branch_name, None,
                "Branch pushed, but the GitHub CLI (gh) is not installed, so no PR was opened."
                + (f" Open it here: {compare}" if compare else ""),
                compare_url=compare,
            )
        except Exception as e:
            return PRResult(False, branch_name, None, f"Branch pushed, but `gh pr create` failed: {e}", compare_url=compare)

        if gh_res.returncode != 0:
            return PRResult(
                False, branch_name, None,
                f"Branch pushed, but `gh pr create` failed: {(gh_res.stderr or gh_res.stdout).strip()}",
                compare_url=compare,
            )

        pr_url = gh_res.stdout.strip().splitlines()[-1] if gh_res.stdout.strip() else None
        print(f"[GitHubPRManager] 🎉 Pull Request created: {pr_url}")
        return PRResult(True, branch_name, pr_url, "Pull Request created via GitHub CLI.", compare_url=compare)
