import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..patcher.unified_diff import PatchError, apply_unified_diff, looks_like_unified_diff
from ..runner.executor import ExecutionResult, TestExecutor


@dataclass
class ToolResult:
    success: bool
    output: str
    metadata: Optional[Dict[str, Any]] = None


CommandRunner = Callable[[str], ExecutionResult]
_SAFE_REVISION = re.compile(r"^[A-Za-z0-9_./~^@{}-]+(?:\.\.\.?[A-Za-z0-9_./~^@{}-]+)?$")


class AgentTools:
    """File inspection, search, test and patch tools exposed to the LLM.

    `runner` executes test commands. The orchestrator passes the VerificationAgent's
    runner, so tests the model triggers run in the same sandbox as final verification.
    """

    def __init__(
        self,
        repo_dir: Path,
        test_command: Optional[str] = None,
        security_agent: Optional[Any] = None,
        runner: Optional[CommandRunner] = None,
    ):
        self.repo_dir = Path(repo_dir).resolve()
        self.test_command = test_command or "pytest"
        self.security_agent = security_agent
        self.runner: CommandRunner = runner or TestExecutor(self.repo_dir, timeout=120).run_command
        # (path, original content or None if the file did not exist)
        self.backups: List[Tuple[Path, Optional[str]]] = []

    def read_file(self, filepath: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> ToolResult:
        target_path = (self.repo_dir / filepath).resolve()
        if not target_path.is_relative_to(self.repo_dir) or not target_path.is_file():
            return ToolResult(success=False, output=f"Error: File '{filepath}' does not exist or is outside workspace.")
        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            total_lines = len(lines)
            s_idx = max(1, int(start_line)) - 1 if start_line else 0
            e_idx = min(total_lines, int(end_line)) if end_line else total_lines
            output = "".join(f"{i + 1}: {lines[i]}" for i in range(s_idx, e_idx))
            return ToolResult(success=True, output=output, metadata={"total_lines": total_lines, "showing": (s_idx + 1, e_idx)})
        except Exception as e:
            return ToolResult(success=False, output=f"Error reading file '{filepath}': {e}")

    def search_code(self, query: str, file_pattern: Optional[str] = None) -> ToolResult:
        results: List[str] = []
        try:
            try:
                regex = re.compile(query, re.IGNORECASE)
            except re.error:
                regex = re.compile(re.escape(query), re.IGNORECASE)
            for root, dirs, files in os.walk(self.repo_dir):
                dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", "node_modules", ".venv", "venv", "target", "dist", "build"}]
                for file in files:
                    if file_pattern and not file.endswith(file_pattern):
                        continue
                    full_path = Path(root) / file
                    rel_path = full_path.relative_to(self.repo_dir)
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            for idx, line in enumerate(f, start=1):
                                if regex.search(line):
                                    results.append(f"{rel_path}:{idx}: {line.strip()}")
                                    if len(results) >= 50:
                                        break
                    except Exception:
                        continue
                    if len(results) >= 50:
                        break
                if len(results) >= 50:
                    break
            if not results:
                return ToolResult(success=True, output=f"No matches found for search query: '{query}'.")
            return ToolResult(success=True, output="\n".join(results[:50]))
        except Exception as e:
            return ToolResult(success=False, output=f"Search failed: {e}")

    def git_diff(self, revision: str = "HEAD~1..HEAD") -> ToolResult:
        if not _SAFE_REVISION.match(revision or "") or revision.startswith("-"):
            return ToolResult(success=False, output=f"Invalid revision: {revision!r}")
        try:
            res = subprocess.run(["git", "diff", revision, "--"], cwd=self.repo_dir, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                return ToolResult(success=True, output=(res.stdout or "No diff output.")[:5000])
            return ToolResult(success=False, output=res.stderr or "Git diff command failed.")
        except Exception as e:
            return ToolResult(success=False, output=f"Git diff failed: {e}")

    def _validate_custom_command(self, custom_command: str) -> Optional[str]:
        """Custom commands may only narrow the configured test command (e.g. add a test path or -k filter)."""
        if any(ch in custom_command for ch in [";", "&", "|", "`", "$(", ">", "<", "\n"]):
            return "Security Policy Blocked: Custom test command contains disallowed shell control characters."
        try:
            base = shlex.split(self.test_command)
            custom = shlex.split(custom_command)
        except ValueError:
            return "Security Policy Blocked: Could not parse custom test command."
        if custom[: len(base)] != base:
            return f"Security Policy Blocked: Custom test command must start with the project test command `{self.test_command}`."
        return None

    def run_test(self, custom_command: Optional[str] = None) -> ToolResult:
        cmd = self.test_command
        if custom_command:
            error = self._validate_custom_command(custom_command)
            if error:
                return ToolResult(success=False, output=error)
            cmd = custom_command
        try:
            res = self.runner(cmd)
            return ToolResult(
                success=res.passed,
                output=res.output[-4000:],
                metadata={"exit_code": res.exit_code, "passed": res.passed},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Test execution error: {e}")

    def apply_patch(self, filepath: str, new_content: str) -> ToolResult:
        """Audit, then write full file content (or apply a single-file unified diff). Reversible."""
        target_path = (self.repo_dir / filepath).resolve()
        if not target_path.is_relative_to(self.repo_dir):
            return ToolResult(success=False, output="Security Error: File path outside workspace boundary.")

        orig_content = target_path.read_text(encoding="utf-8") if target_path.is_file() else None
        if looks_like_unified_diff(new_content):
            try:
                new_content = apply_unified_diff(orig_content or "", new_content)
            except PatchError as e:
                return ToolResult(success=False, output=f"Patch for '{filepath}' did not apply: {e}. Send the full file content instead.")

        if self.security_agent:
            is_safe, violations = self.security_agent.audit_file_modification(filepath, new_content)
            if not is_safe:
                return ToolResult(
                    success=False,
                    output=f"Security Policy Blocked: Modification to '{filepath}' rejected. Reasons: {'; '.join(violations)}",
                    metadata={"violations": violations},
                )

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            self.backups.append((target_path, orig_content))
            target_path.write_text(new_content, encoding="utf-8")
            return ToolResult(success=True, output=f"Successfully updated file: '{filepath}'.")
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to apply patch to '{filepath}': {e}")

    def rollback(self) -> None:
        """Restore every file touched by apply_patch to its pre-session state."""
        for path, orig_content in reversed(self.backups):
            try:
                if orig_content is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.write_text(orig_content, encoding="utf-8")
            except Exception as e:
                print(f"[AgentTools] Rollback error for {path}: {e}")
        self.backups.clear()

    def commit_backups(self) -> None:
        """Forget backups once changes are committed, so a later rollback can't undo them."""
        self.backups.clear()


def get_agent_tools_schema() -> List[Dict[str, Any]]:
    return [
        {
            "name": "read_file",
            "description": "Read contents of a source file with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Relative file path from workspace root."},
                    "start_line": {"type": "integer", "description": "1-based starting line number (optional)."},
                    "end_line": {"type": "integer", "description": "1-based ending line number (optional)."},
                },
                "required": ["filepath"],
            },
        },
        {
            "name": "search_code",
            "description": "Search the repository for functions, classes, symbols, or error messages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Regex pattern or exact string."},
                    "file_pattern": {"type": "string", "description": "Optional file extension filter (e.g. '.py')."},
                },
                "required": ["query"],
            },
        },
        {
            "name": "git_diff",
            "description": "Get git diff for a commit range (default: the failing commit, HEAD~1..HEAD).",
            "parameters": {
                "type": "object",
                "properties": {"revision": {"type": "string", "description": "Git revision or range."}},
                "required": [],
            },
        },
        {
            "name": "run_test",
            "description": "Run the project test suite. custom_command may only narrow the default test command (e.g. add a test path).",
            "parameters": {
                "type": "object",
                "properties": {"custom_command": {"type": "string", "description": "Optional narrowed test command."}},
                "required": [],
            },
        },
        {
            "name": "apply_patch",
            "description": "Replace a source file with new content. Test files, CI config and dependency manifests are blocked.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Relative file path to update."},
                    "new_content": {"type": "string", "description": "Full new file content."},
                },
                "required": ["filepath", "new_content"],
            },
        },
    ]
