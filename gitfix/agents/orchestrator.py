from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..config import Config
from ..detector import detect_project
from ..git.pr_manager import GitHubPRManager
from ..git.repo_manager import GitRepoManager
from ..llm import BaseLLMProvider, get_llm_provider
from ..memory.error_db import ErrorDatabase
from .diagnosis_agent import DiagnosisAgent
from .patch_agent import PatchAgent
from .regression_agent import RegressionAgent
from .security_agent import SecurityAgent
from .verification_agent import VerificationAgent


@dataclass
class OrchestratorResult:
    success: bool
    commit_hash: str
    branch_created: Optional[str]
    pr_url: Optional[str]
    retries_used: int
    summary: str
    modified_files: List[str]


class GitFixOrchestrator:
    """Production-grade multi-agent pipeline orchestrating repository regression maintenance."""

    def __init__(
        self,
        repo_dir: Optional[Path] = None,
        config: Optional[Config] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        use_sandbox: bool = True,
    ):
        self.repo_dir = Path(repo_dir or Path.cwd()).resolve()
        self.config = config or Config(str(self.repo_dir))
        self.repo_manager = GitRepoManager(self.repo_dir)
        self.project_info = detect_project(self.repo_dir)
        self.memory = ErrorDatabase(self.repo_dir / self.config.get("memory.db_path", ".gitfix/history.json"))
        
        self.llm = llm_provider or get_llm_provider(
            provider_name=self.config.provider,
            model=self.config.model,
        )

        # Specialized Agent Initialization
        self.security_agent = SecurityAgent(self.repo_dir)
        self.regression_agent = RegressionAgent(self.repo_dir, self.project_info.test_command)
        self.diagnosis_agent = DiagnosisAgent(self.repo_dir)
        self.patch_agent = PatchAgent(
            self.repo_dir,
            self.llm,
            self.project_info.test_command,
            security_agent=self.security_agent,
        )
        self.verification_agent = VerificationAgent(self.repo_dir, use_sandbox=use_sandbox)
        self.pr_manager = GitHubPRManager(self.repo_dir)

    def run_repair_flow(self, auto_commit: Optional[bool] = None, auto_pr: bool = False) -> OrchestratorResult:
        commit_hash = self.repo_manager.get_current_commit() or "HEAD"
        print(f"\n[GitFix-Orchestrator] 🤖 Pipeline initialized for commit {commit_hash[:7]}")
        print(f"[GitFix-Orchestrator] Language: {self.project_info.language} | Framework: {self.project_info.framework or 'None'}")
        print(f"[GitFix-Orchestrator] Test Command: {self.project_info.test_command}")

        # Step 1: Regression Analysis
        print("\n[GitFix-Orchestrator] --- Phase 1: Regression Attribution ---")
        reg_analysis = self.regression_agent.analyze_regression(commit_hash)
        if not reg_analysis.is_regression and reg_analysis.baseline_passed:
            print("[GitFix-Orchestrator] ✅ No test failures detected.")
            return OrchestratorResult(
                success=True,
                commit_hash=commit_hash,
                branch_created=None,
                pr_url=None,
                retries_used=0,
                summary="No test failure detected.",
                modified_files=[],
            )

        # Initial Test Failure Output
        verify_res = self.verification_agent.verify(self.project_info.test_command)
        latest_output = verify_res.execution_result.stderr or verify_res.execution_result.stdout

        # Step 2: Safety Branch Strategy
        print("\n[GitFix-Orchestrator] --- Phase 2: Safety Workspace & Branching ---")
        should_auto_commit = self.config.auto_commit if auto_commit is None else auto_commit
        branch_created = None
        if not should_auto_commit or auto_pr:
            branch_created = self.repo_manager.create_ai_branch(commit_hash)
            print(f"[GitFix-Orchestrator] 🛡️ Switched to safety branch: {branch_created}")

        # Step 3: Iterative Multi-Agent Repair Loop
        print("\n[GitFix-Orchestrator] --- Phase 3: Diagnosis, Repair & Verification ---")
        max_retries = self.config.max_retries
        all_modified_files = []

        for attempt in range(1, max_retries + 1):
            print(f"\n[GitFix-Orchestrator] Step Attempt {attempt}/{max_retries}")
            
            # Diagnosis
            diag_report = self.diagnosis_agent.diagnose(
                test_output=latest_output,
                project_info=self.project_info,
                commit_hash=commit_hash,
            )

            # Patch Generation & Application
            patch_res = self.patch_agent.generate_and_apply_fix(diag_report.context_prompt)
            if not patch_res.modified_files:
                print("[GitFix-Orchestrator] ⚠️ No patch files modified. Retrying...")
                continue

            # Security Audit
            sec_audit = self.security_agent.audit_patch(patch_res.modified_files)
            if not sec_audit.is_safe:
                print(f"[GitFix-Orchestrator] 🛑 Security policy blocked patch: {sec_audit.violations}")
                # Rollback changes immediately so unauthorized files do not persist on disk
                self.repo_manager.reset_hard()
                continue

            all_modified_files.extend(patch_res.modified_files)

            # Verification
            verify_res = self.verification_agent.verify(self.project_info.test_command)
            if verify_res.passed:
                print(f"\n[GitFix-Orchestrator] 🎉 SUCCESS! Tests passed after attempt {attempt}.")
                
                commit_msg = f"fix(ai-agent): resolve {diag_report.parsed_error.error_type}\n\nRoot cause: {patch_res.explanation}"
                committed = False
                if should_auto_commit or auto_pr:
                    committed = self.repo_manager.stage_and_commit(commit_msg, files=patch_res.modified_files)
                    if not committed:
                        print("[GitFix-Orchestrator] ❌ Failed to commit repair changes.")
                        return OrchestratorResult(
                            success=False,
                            commit_hash=commit_hash,
                            branch_created=branch_created,
                            pr_url=None,
                            retries_used=attempt,
                            summary="Tests passed, but git commit failed.",
                            modified_files=list(set(all_modified_files)),
                        )

                pr_url = None
                if auto_pr and branch_created and committed:
                    pr_res = self.pr_manager.create_pull_request(
                        branch_name=branch_created,
                        title=f"fix(ai-agent): resolve regression in {commit_hash[:7]}",
                        body=f"## GitFix Autonomous Repair Report\n\n- **Error Type**: `{diag_report.parsed_error.error_type}`\n- **Fix Explanation**: {patch_res.explanation}\n- **Modified Files**: {patch_res.modified_files}",
                    )
                    pr_url = pr_res.pr_url

                return OrchestratorResult(
                    success=True,
                    commit_hash=commit_hash,
                    branch_created=branch_created,
                    pr_url=pr_url,
                    retries_used=attempt,
                    summary=patch_res.explanation,
                    modified_files=list(set(all_modified_files)),
                )
            else:
                latest_output = verify_res.execution_result.stderr or verify_res.execution_result.stdout

        print(f"\n[GitFix-Orchestrator] 🛑 Max retries ({max_retries}) reached without resolving regression.")
        self.repo_manager.reset_hard()
        return OrchestratorResult(
            success=False,
            commit_hash=commit_hash,
            branch_created=branch_created,
            pr_url=None,
            retries_used=max_retries,
            summary="Failed to repair regression within max retries. Unverified changes were reverted.",
            modified_files=list(set(all_modified_files)),
        )
