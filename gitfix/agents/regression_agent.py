import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..git.repo_manager import GitRepoManager
from .verification_agent import VerificationAgent


@dataclass
class RegressionAnalysisResult:
    is_regression: bool
    target_commit: str
    baseline_passed: bool
    current_passed: bool
    summary: str
    current_output: str = ""


class RegressionAgent:
    """Checks whether a test failure was introduced by the latest commit.

    The parent commit is tested in a temporary `git worktree`, so the user's checkout
    (branch, detached HEAD, and any files) is never moved or modified.
    """

    def __init__(self, repo_dir: Path, test_command: str, runner: Optional[VerificationAgent] = None):
        self.repo_dir = Path(repo_dir).resolve()
        self.repo_manager = GitRepoManager(self.repo_dir)
        self.test_command = test_command
        self.runner = runner or VerificationAgent(self.repo_dir, use_sandbox=False)

    def analyze_regression(self, commit_hash: Optional[str] = None) -> RegressionAnalysisResult:
        current_commit = commit_hash or self.repo_manager.get_current_commit() or "HEAD"
        print(f"[RegressionAgent] 🔍 Analyzing commit regression for {current_commit[:7]}...")

        curr_res = self.runner.run(self.test_command)
        if curr_res.passed:
            return RegressionAnalysisResult(
                is_regression=False,
                target_commit=current_commit,
                baseline_passed=True,
                current_passed=True,
                summary="Current commit passes all tests. No failure detected.",
            )

        parent = self.repo_manager.resolve_ref("HEAD~1")
        if not parent:
            print("[RegressionAgent] ℹ️ No parent commit available. Treating failure as repair target.")
            return RegressionAnalysisResult(
                is_regression=True,
                target_commit=current_commit,
                baseline_passed=False,
                current_passed=False,
                summary="Initial root commit failure.",
                current_output=curr_res.output,
            )

        print(f"[RegressionAgent] ⏪ Checking baseline at {parent[:7]} in an isolated worktree...")
        tmp_root = Path(tempfile.mkdtemp(prefix="gitfix-baseline-"))
        worktree_dir = tmp_root / "baseline"
        ok, err = self.repo_manager.add_detached_worktree(worktree_dir, parent)
        if not ok:
            shutil.rmtree(tmp_root, ignore_errors=True)
            print(f"[RegressionAgent] ⚠️ Could not create baseline worktree: {err}")
            return RegressionAnalysisResult(
                is_regression=True,
                target_commit=current_commit,
                baseline_passed=False,
                current_passed=False,
                summary=f"Could not create baseline worktree: {err}",
                current_output=curr_res.output,
            )

        baseline_runner = self.runner.for_directory(worktree_dir)
        try:
            baseline_res = baseline_runner.run(self.test_command)
        finally:
            baseline_runner.cleanup()
            self.repo_manager.remove_worktree(worktree_dir)
            shutil.rmtree(tmp_root, ignore_errors=True)

        if baseline_res.passed:
            print(f"[RegressionAgent] 🎯 Confirmed: {current_commit[:7]} introduced a regression (parent passed).")
            return RegressionAnalysisResult(
                is_regression=True,
                target_commit=current_commit,
                baseline_passed=True,
                current_passed=False,
                summary=f"Commit {current_commit[:7]} introduced a test regression.",
                current_output=curr_res.output,
            )

        print("[RegressionAgent] ⚠️ Parent commit was already failing. Pre-existing test failure detected.")
        return RegressionAnalysisResult(
            is_regression=False,
            target_commit=current_commit,
            baseline_passed=False,
            current_passed=False,
            summary="Failure existed prior to recent commit (pre-existing bug).",
            current_output=curr_res.output,
        )
