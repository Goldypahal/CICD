from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import Config
from ..detector import detect_project
from ..git.repo_manager import GitRepoManager
from ..analyzer.stack_trace import StackTraceParser
from ..analyzer.code_retriever import CodeRetriever
from ..analyzer.context_builder import ContextBuilder
from ..runner.executor import TestExecutor
from ..patcher.applier import CodePatcher
from ..memory.error_db import ErrorDatabase
from ..llm import get_llm_provider, BaseLLMProvider

@dataclass
class OrchestratorResult:
    success: bool
    commit_hash: str
    branch_created: Optional[str]
    retries_used: int
    summary: str
    modified_files: List[str]

class GitFixOrchestrator:
    def __init__(self, repo_dir: Optional[Path] = None, config: Optional[Config] = None, llm_provider: Optional[BaseLLMProvider] = None):
        self.repo_dir = Path(repo_dir or Path.cwd()).resolve()
        self.config = config or Config(str(self.repo_dir))
        self.repo_manager = GitRepoManager(self.repo_dir)
        self.project_info = detect_project(self.repo_dir)
        self.executor = TestExecutor(self.repo_dir, timeout=self.config.timeout_seconds)
        self.patcher = CodePatcher(self.repo_dir)
        self.retriever = CodeRetriever(self.repo_manager)
        self.context_builder = ContextBuilder(self.retriever)
        self.stack_parser = StackTraceParser()
        self.error_db = ErrorDatabase(self.repo_dir / self.config.get("memory.db_path", ".gitfix/history.json"))
        
        self.llm = llm_provider or get_llm_provider(
            provider_name=self.config.provider,
            model=self.config.model,
        )

    def run_repair_flow(self, auto_commit: Optional[bool] = None) -> OrchestratorResult:
        commit_hash = self.repo_manager.get_current_commit() or "HEAD"
        print(f"\n[GitFix-Agent] 🤖 Initiating autonomous maintenance for commit {commit_hash[:7]}")
        print(f"[GitFix-Agent] Project Detected: {self.project_info.language} | Framework: {self.project_info.framework or 'None'}")
        print(f"[GitFix-Agent] Test Command: {self.project_info.test_command}")

        # 1. Initial Test Run to verify failure
        print("[GitFix-Agent] Step 1/5: Running test suite to capture error state...")
        res = self.executor.run_command(self.project_info.test_command)
        if res.passed:
            print("[GitFix-Agent] ✅ All tests passed! No regression or failure detected.")
            return OrchestratorResult(
                success=True,
                commit_hash=commit_hash,
                branch_created=None,
                retries_used=0,
                summary="No test failures detected.",
                modified_files=[],
            )

        print(f"[GitFix-Agent] ❌ Test failure confirmed (exit code {res.exit_code}). Collecting failure context...")

        # 2. Branch Safety Strategy
        should_auto_commit = self.config.auto_commit if auto_commit is None else auto_commit
        branch_created = None
        if not should_auto_commit and self.config.branch_strategy == "ai-branch":
            curr_branch = self.repo_manager.get_current_branch()
            if not curr_branch.startswith(self.config.get("git.branch_prefix", "ai/fix-")):
                branch_created = self.repo_manager.create_ai_branch(commit_hash)
                print(f"[GitFix-Agent] 🛡️ Switched to safety branch: {branch_created}")

        # 3. Iterative Repair Loop
        diff = self.repo_manager.get_commit_diff()
        changed_files = self.repo_manager.get_changed_files()
        max_retries = self.config.max_retries

        latest_output = res.stderr or res.stdout
        all_modified_files = []

        for attempt in range(1, max_retries + 1):
            print(f"\n[GitFix-Agent] --- Repair Attempt {attempt}/{max_retries} ---")
            
            # Parse stack trace
            parsed_error = self.stack_parser.parse(latest_output)
            print(f"[GitFix-Agent] Diagnosed Error Signature: {parsed_error.error_type}: {parsed_error.error_message}")

            # Query RAG Error Database
            similar_fixes = []
            if self.config.get("memory.enabled", True):
                similar_fixes = self.error_db.query_similar_errors(parsed_error.error_type, parsed_error.error_message)
                if similar_fixes:
                    print(f"[GitFix-Agent] 🧠 RAG Memory: Found {len(similar_fixes)} historical fix patterns.")

            # Build context packet
            context = self.context_builder.build_context(
                project_info=self.project_info,
                commit_hash=commit_hash,
                diff=diff,
                changed_files=changed_files,
                parsed_error=parsed_error,
                historical_fixes=similar_fixes,
            )

            prompt = self.context_builder.format_prompt(context)

            # Generate fix with LLM
            print("[GitFix-Agent] Requesting fix generation from LLM...")
            llm_response = self.llm.generate_fix(prompt)
            explanation = llm_response.get("explanation", "Automated fix applied.")
            files_to_fix = llm_response.get("files", [])

            if not files_to_fix:
                print(f"[GitFix-Agent] ⚠️ LLM returned no modified files. Explanation: {explanation}")
                continue

            print(f"[GitFix-Agent] LLM Proposed Fix Explanation: {explanation}")
            
            # Apply patch
            success, modified_files, backups = self.patcher.apply_fix_payload(files_to_fix)
            if not success:
                print("[GitFix-Agent] ❌ Patch application failed. Retrying...")
                continue

            all_modified_files.extend(modified_files)

            # Verification run
            print("[GitFix-Agent] Step 4/5: Running test suite to verify patch...")
            verify_res = self.executor.run_command(self.project_info.test_command)
            
            if verify_res.passed:
                print(f"\n[GitFix-Agent] 🎉 SUCCESS! Tests passed after {attempt} attempt(s).")
                
                # Commit fix
                commit_msg = f"fix(ai-agent): resolve {parsed_error.error_type}\n\nRoot cause: {explanation}"
                committed = self.repo_manager.stage_and_commit(commit_msg)
                if committed:
                    print("[GitFix-Agent] ✅ Git commit successfully created.")

                # Save to RAG Memory
                patch_diff = self.repo_manager.get_commit_diff("HEAD~1..HEAD")
                self.error_db.save_fix(
                    error_type=parsed_error.error_type,
                    error_message=parsed_error.error_message,
                    commit_hash=commit_hash,
                    summary=explanation,
                    modified_files=modified_files,
                    patch_diff=patch_diff,
                )

                return OrchestratorResult(
                    success=True,
                    commit_hash=commit_hash,
                    branch_created=branch_created,
                    retries_used=attempt,
                    summary=explanation,
                    modified_files=list(set(all_modified_files)),
                )
            else:
                print(f"[GitFix-Agent] ❌ Test suite still failing after attempt {attempt}. Rolling back patch...")
                self.patcher.rollback(backups)
                latest_output = verify_res.stderr or verify_res.stdout

        print(f"\n[GitFix-Agent] 🛑 Max retries ({max_retries}) reached without resolving the test failure.")
        return OrchestratorResult(
            success=False,
            commit_hash=commit_hash,
            branch_created=branch_created,
            retries_used=max_retries,
            summary="Failed to repair regression within max retries.",
            modified_files=list(set(all_modified_files)),
        )
