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


class GitHubPRManager:
    """Manages creation of safety branches, pushing to remote origin, and creating GitHub Pull Requests."""

    def __init__(self, repo_dir: Path):
        self.repo_dir = Path(repo_dir).resolve()
        self.repo_manager = GitRepoManager(self.repo_dir)

    def create_pull_request(
        self,
        branch_name: str,
        title: str,
        body: str,
        base_branch: str = "main",
    ) -> PRResult:
        print(f"[GitHubPRManager] 🚀 Preparing Pull Request for branch '{branch_name}'...")
        
        # 1. Push branch to remote origin
        try:
            push_res = subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if push_res.returncode != 0:
                return PRResult(
                    success=False,
                    branch=branch_name,
                    pr_url=None,
                    message=f"Git push failed: {push_res.stderr.strip()}",
                )
        except Exception as e:
            return PRResult(
                success=False,
                branch=branch_name,
                pr_url=None,
                message=f"Failed to push branch to remote: {str(e)}",
            )

        # 2. Use GitHub CLI `gh` if installed to create PR
        try:
            gh_cmd = [
                "gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--base", base_branch,
                "--head", branch_name,
            ]
            gh_res = subprocess.run(
                gh_cmd,
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if gh_res.returncode == 0:
                pr_url = gh_res.stdout.strip()
                print(f"[GitHubPRManager] 🎉 Pull Request successfully created: {pr_url}")
                return PRResult(
                    success=True,
                    branch=branch_name,
                    pr_url=pr_url,
                    message="Pull Request created successfully via GitHub CLI.",
                )
        except Exception:
            pass

        # Fallback message if gh CLI is not available
        print(f"[GitHubPRManager] ✅ Branch '{branch_name}' pushed to GitHub origin. PR can be opened on GitHub.")
        return PRResult(
            success=True,
            branch=branch_name,
            pr_url=f"https://github.com/origin/compare/{branch_name}",
            message="Branch pushed successfully. Open PR via GitHub web UI.",
        )
