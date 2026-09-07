import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..git.repo_manager import GitRepoManager
from ..runner.executor import TestExecutionResult, TestExecutor


@dataclass
class RegressionAnalysisResult:
    is_regression: bool
    target_commit: str
    baseline_passed: bool
    current_passed: bool
    summary: str


class RegressionAgent:
    """Verifies whether a test failure is a genuine regression introduced by recent commit(s)."""

    def __init__(self, repo_dir: Path, test_command: str):
        self.repo_dir = Path(repo_dir).resolve()
        self.repo_manager = GitRepoManager(self.repo_dir)
        self.test_command = test_command
        self.executor = TestExecutor(self.repo_dir)

    def analyze_regression(self, commit_hash: Optional[str] = None) -> RegressionAnalysisResult:
        current_commit = commit_hash or self.repo_manager.get_current_commit() or "HEAD"
        print(f"[RegressionAgent] 🔍 Analyzing commit regression for {current_commit[:7]}...")

        # 1. Run tests on current HEAD
        curr_res = self.executor.run_command(self.test_command)
        if curr_res.passed:
            return RegressionAnalysisResult(
                is_regression=False,
                target_commit=current_commit,
                baseline_passed=True,
                current_passed=True,
                summary="Current commit passes all tests. No failure detected.",
            )

        # Check if HEAD~1 exists
        has_parent = False
        try:
            rev_res = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD~1"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            has_parent = rev_res.returncode == 0
        except Exception:
            has_parent = False

        if not has_parent:
            print("[RegressionAgent] ℹ️ Root commit detected (no HEAD~1 parent). Treating initial failure as target repair.")
            return RegressionAnalysisResult(
                is_regression=True,
                target_commit=current_commit,
                baseline_passed=False,
                current_passed=False,
                summary="Initial root commit failure.",
            )

        # 2. Run tests on HEAD~1 baseline to verify if commit introduced regression
        print("[RegressionAgent] ⏪ Checking baseline test state at HEAD~1...")
        curr_branch = self.repo_manager.get_current_branch()
        try:
            subprocess.run(
                ["git", "checkout", "HEAD~1"],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )
            baseline_res = self.executor.run_command(self.test_command)
        finally:
            subprocess.run(
                ["git", "checkout", curr_branch or current_commit],
                cwd=self.repo_dir,
                capture_output=True,
                text=True,
            )

        if baseline_res.passed and not curr_res.passed:
            print(f"[RegressionAgent] 🎯 Confirmed: Commit {current_commit[:7]} introduced a regression (HEAD~1 passed, HEAD failed).")
            return RegressionAnalysisResult(
                is_regression=True,
                target_commit=current_commit,
                baseline_passed=True,
                current_passed=False,
                summary=f"Commit {current_commit[:7]} introduced a test regression.",
            )
        elif not baseline_res.passed:
            print("[RegressionAgent] ⚠️ Baseline HEAD~1 was already failing. Pre-existing test failure detected.")
            return RegressionAnalysisResult(
                is_regression=False,
                target_commit=current_commit,
                baseline_passed=False,
                current_passed=False,
                summary="Failure existed prior to recent commit (pre-existing bug).",
            )

        return RegressionAnalysisResult(
            is_regression=True,
            target_commit=current_commit,
            baseline_passed=False,
            current_passed=False,
            summary="Test suite failed.",
        )
