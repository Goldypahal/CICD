from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..config import Config
from ..detector import detect_project
from ..git.pr_manager import GitHubPRManager
from ..git.repo_manager import GitRepoManager
from ..llm import BaseLLMProvider, get_llm_provider
from ..memory.error_db import ErrorDatabase
from ..runner.docker_sandbox import DEFAULT_IMAGES, FALLBACK_IMAGE, SandboxConfig
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
    modified_files: List[str] = field(default_factory=list)
    pr_error: Optional[str] = None


class GitFixOrchestrator:
    """Regression check -> diagnosis -> patch -> security audit -> sandboxed verification -> commit/PR.

    Guarantees:
      * Refuses to start if tracked files have uncommitted changes.
      * Never runs `git reset --hard`; on failure it reverts only the files it wrote and
        returns to the branch/commit it started on.
      * Every test run (baseline, agent, verification) uses the same execution policy.
    """

    def __init__(
        self,
        repo_dir: Optional[Path] = None,
        config: Optional[Config] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        use_sandbox: bool = True,
        _docker_available: Optional[bool] = None,
    ):
        self.repo_dir = Path(repo_dir or Path.cwd()).resolve()
        self.config = config or Config(str(self.repo_dir))
        self.repo_manager = GitRepoManager(self.repo_dir)
        self.project_info = detect_project(self.repo_dir)
        self.test_command = self.config.test_command_override or self.project_info.test_command
        self.memory = ErrorDatabase(self.repo_dir / self.config.get("memory.db_path", ".gitfix/history.json"))
        self.memory_enabled = bool(self.config.get("memory.enabled", True))

        self.llm = llm_provider or get_llm_provider(
            provider_name=self.config.provider,
            model=self.config.model,
            temperature=self.config.temperature,
        )

        self.verification_agent = VerificationAgent(
            self.repo_dir,
            use_sandbox=use_sandbox,
            sandbox_config=self._sandbox_config(),
            timeout_seconds=self.config.timeout_seconds,
            _docker_available=_docker_available,
        )
        self.security_agent = SecurityAgent(self.repo_dir, allow_test_edits=self.config.allow_test_edits)
        self.regression_agent = RegressionAgent(self.repo_dir, self.test_command, runner=self.verification_agent)
        self.diagnosis_agent = DiagnosisAgent(self.repo_dir)
        self.patch_agent = PatchAgent(
            self.repo_dir,
            self.llm,
            self.test_command,
            security_agent=self.security_agent,
            runner=self.verification_agent.run,
        )
        self.pr_manager = GitHubPRManager(self.repo_dir)

    def _sandbox_config(self) -> SandboxConfig:
        image = self.config.get("sandbox.image", "auto")
        if not image or image == "auto":
            image = self.project_info.sandbox_image or DEFAULT_IMAGES.get(self.project_info.language, FALLBACK_IMAGE)
        setup = self.config.get("sandbox.setup_command", "auto")
        if setup == "auto":
            setup = self.project_info.install_command
        return SandboxConfig(
            image=image,
            setup_command=setup or None,
            cpu_limit=str(self.config.get("sandbox.cpu_limit", "2.0")),
            memory_limit=str(self.config.get("sandbox.memory_limit", "2g")),
            timeout_seconds=self.config.timeout_seconds,
        )

    def _resolve_base_branch(self, explicit: Optional[str], original_branch: str) -> str:
        if explicit:
            return explicit
        if original_branch and not original_branch.startswith(self.config.branch_prefix):
            return original_branch
        return self.repo_manager.get_default_branch() or "main"

    def _fail(self, commit_hash: str, summary: str, retries: int = 0, branch: Optional[str] = None) -> OrchestratorResult:
        print(f"[GitFix-Orchestrator] ❌ {summary}")
        return OrchestratorResult(False, commit_hash, branch, None, retries, summary, [])

    def run_repair_flow(
        self,
        auto_commit: Optional[bool] = None,
        auto_pr: bool = False,
        base_branch: Optional[str] = None,
    ) -> OrchestratorResult:
        try:
            return self._run(auto_commit, auto_pr, base_branch)
        finally:
            self.verification_agent.cleanup()

    def _run(self, auto_commit: Optional[bool], auto_pr: bool, base_branch: Optional[str]) -> OrchestratorResult:
        if not self.repo_manager.is_git_repo():
            return self._fail("", "Not a git repository.")
        commit_hash = self.repo_manager.get_current_commit() or "HEAD"
        original_ref = self.repo_manager.get_current_ref()
        original_branch = self.repo_manager.get_current_branch()

        print(f"\n[GitFix-Orchestrator] 🤖 Pipeline initialized for commit {commit_hash[:7]}")
        print(f"[GitFix-Orchestrator] Language: {self.project_info.language} | Framework: {self.project_info.framework or 'None'}")
        print(f"[GitFix-Orchestrator] Test Command: {self.test_command} | Execution: {self.verification_agent.environment}")

        if self.repo_manager.has_tracked_changes():
            return self._fail(
                commit_hash,
                "Uncommitted changes to tracked files. Commit or stash them first; GitFix will not run on "
                "a dirty working tree so it can never overwrite or lose your work.",
            )
        if not self.llm.is_configured():
            return self._fail(commit_hash, f"LLM provider '{self.config.provider}' is not configured: {self.llm.configuration_error()}")

        # Phase 1: regression attribution
        print("\n[GitFix-Orchestrator] --- Phase 1: Regression Attribution ---")
        reg = self.regression_agent.analyze_regression(commit_hash)
        if reg.current_passed:
            print("[GitFix-Orchestrator] ✅ No test failures detected.")
            return OrchestratorResult(True, commit_hash, None, None, 0, "No test failure detected.", [])
        print(f"[GitFix-Orchestrator] {reg.summary}")

        latest_output = reg.current_output

        # Phase 2: safety branch
        print("\n[GitFix-Orchestrator] --- Phase 2: Safety Workspace & Branching ---")
        should_auto_commit = self.config.auto_commit if auto_commit is None else auto_commit
        use_branch = auto_pr or not should_auto_commit
        branch_created: Optional[str] = None
        branch_is_new = False
        if use_branch:
            target_name = f"{self.config.branch_prefix}{commit_hash[:7]}"
            branch_is_new = not self.repo_manager.branch_exists(target_name)
            branch_created = self.repo_manager.create_ai_branch(commit_hash, prefix=self.config.branch_prefix)
            print(f"[GitFix-Orchestrator] 🛡️ Switched to safety branch: {branch_created}")

        def abandon(summary: str, retries: int) -> OrchestratorResult:
            self.patch_agent.rollback()
            if branch_created:
                self.repo_manager.checkout(original_ref)
                if branch_is_new:
                    self.repo_manager.delete_branch(branch_created)
            return self._fail(commit_hash, summary, retries)

        # Phase 3: repair loop
        print("\n[GitFix-Orchestrator] --- Phase 3: Diagnosis, Repair & Verification ---")
        max_retries = self.config.max_retries
        for attempt in range(1, max_retries + 1):
            print(f"\n[GitFix-Orchestrator] Attempt {attempt}/{max_retries}")

            parsed = self.diagnosis_agent.parser.parse(latest_output)
            similar = self.memory.query_similar_errors(parsed.error_type, parsed.error_message) if self.memory_enabled else []
            diag = self.diagnosis_agent.diagnose(
                test_output=latest_output,
                project_info=self.project_info,
                commit_hash=commit_hash,
                similar_fixes=similar,
            )

            patch_res = self.patch_agent.generate_and_apply_fix(diag.context_prompt)
            if not patch_res.modified_files:
                if not self.llm.is_configured():
                    return abandon("LLM provider became unavailable.", attempt)
                print("[GitFix-Orchestrator] ⚠️ No passing patch produced this attempt.")
                continue

            sec = self.security_agent.audit_patch(patch_res.modified_files)
            if not sec.is_safe:
                print(f"[GitFix-Orchestrator] 🛑 Security policy blocked patch: {sec.violations}")
                self.patch_agent.rollback()
                continue

            verify_res = self.verification_agent.verify(self.test_command)
            if not verify_res.passed:
                latest_output = verify_res.execution_result.output
                self.patch_agent.rollback()
                continue

            print(f"\n[GitFix-Orchestrator] 🎉 SUCCESS! Tests passed after attempt {attempt}.")
            modified = sorted(set(patch_res.modified_files))
            patch_diff = self.repo_manager.get_working_diff(modified)
            pr_url: Optional[str] = None
            pr_error: Optional[str] = None

            if should_auto_commit or auto_pr or branch_created:
                msg = (
                    f"fix(ai-agent): resolve {diag.parsed_error.error_type} from {commit_hash[:7]}\n\n"
                    f"Root cause: {patch_res.explanation}"
                )
                if not self.repo_manager.stage_and_commit(msg, files=modified):
                    return abandon("Tests passed, but git commit failed.", attempt)
                self.patch_agent.accept()

                if auto_pr and branch_created:
                    pr = self.pr_manager.create_pull_request(
                        branch_name=branch_created,
                        title=f"fix(ai-agent): resolve regression from {commit_hash[:7]}",
                        body=(
                            "## GitFix Autonomous Repair Report\n\n"
                            f"- **Failing commit**: `{commit_hash[:7]}`\n"
                            f"- **Error**: `{diag.parsed_error.error_type}`: {diag.parsed_error.error_message[:300]}\n"
                            f"- **Fix**: {patch_res.explanation}\n"
                            f"- **Modified files**: {', '.join(modified)}\n"
                            f"- **Verified in**: {verify_res.environment}\n"
                        ),
                        base_branch=self._resolve_base_branch(base_branch, original_branch),
                    )
                    pr_url = pr.pr_url
                    if not pr.success:
                        pr_error = pr.message
                        print(f"[GitFix-Orchestrator] ⚠️ {pr.message}")
                elif self.config.auto_push and branch_created:
                    ok, err = self.repo_manager.push_branch(branch_created)
                    if not ok:
                        pr_error = f"Push failed: {err}"

            if self.memory_enabled:
                self.memory.save_fix(
                    error_type=diag.parsed_error.error_type,
                    error_message=diag.parsed_error.error_message,
                    commit_hash=commit_hash,
                    summary=patch_res.explanation,
                    modified_files=modified,
                    patch_diff=patch_diff,
                )

            return OrchestratorResult(
                success=True,
                commit_hash=commit_hash,
                branch_created=branch_created,
                pr_url=pr_url,
                retries_used=attempt,
                summary=patch_res.explanation,
                modified_files=modified,
                pr_error=pr_error,
            )

        return abandon(
            f"Max retries ({max_retries}) reached without resolving the failure. GitFix's edits were reverted.",
            max_retries,
        )
