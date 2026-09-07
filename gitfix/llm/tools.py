import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ToolResult:
    success: bool
    output: str
    metadata: Optional[Dict[str, Any]] = None


class AgentTools:
    """Provides file inspection, code search, testing, and patch tools for agentic LLM loops."""

    def __init__(self, repo_dir: Path, test_command: Optional[str] = None):
        self.repo_dir = Path(repo_dir).resolve()
        self.test_command = test_command or "pytest"

    def read_file(
        self, filepath: str, start_line: Optional[int] = None, end_line: Optional[int] = None
    ) -> ToolResult:
        """Read file content with line numbers and optional slicing."""
        target_path = (self.repo_dir / filepath).resolve()
        if not target_path.is_relative_to(self.repo_dir) or not target_path.exists():
            return ToolResult(success=False, output=f"Error: File '{filepath}' does not exist or is outside workspace.")

        try:
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            s_idx = max(1, start_line) - 1 if start_line else 0
            e_idx = min(total_lines, end_line) if end_line else total_lines

            formatted_lines = [
                f"{i + 1}: {lines[i]}" for i in range(s_idx, e_idx)
            ]
            output = "".join(formatted_lines)
            return ToolResult(
                success=True,
                output=output,
                metadata={"total_lines": total_lines, "showing": (s_idx + 1, e_idx)},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Error reading file '{filepath}': {str(e)}")

    def search_code(self, query: str, file_pattern: Optional[str] = None) -> ToolResult:
        """Search codebase for symbols, functions, or text patterns."""
        results = []
        try:
            regex = re.compile(query, re.IGNORECASE)
            for root, _, files in os.walk(self.repo_dir):
                if ".git" in root or "__pycache__" in root or "node_modules" in root:
                    continue
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

            if not results:
                return ToolResult(success=True, output=f"No matches found for search query: '{query}'.")

            return ToolResult(success=True, output="\n".join(results[:50]))
        except Exception as e:
            return ToolResult(success=False, output=f"Search failed: {str(e)}")

    def git_diff(self, revision: str = "HEAD~1..HEAD") -> ToolResult:
        """Fetch git diff for given commit range or working tree."""
        try:
            cmd = ["git", "diff", revision]
            res = subprocess.run(cmd, cwd=self.repo_dir, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                output = res.stdout if res.stdout else "No diff output."
                return ToolResult(success=True, output=output[:5000])
            return ToolResult(success=False, output=res.stderr or "Git diff command failed.")
        except Exception as e:
            return ToolResult(success=False, output=f"Git diff failed: {str(e)}")

    def run_test(self, custom_command: Optional[str] = None) -> ToolResult:
        """Execute project test command and return test runner output."""
        cmd = custom_command or self.test_command
        try:
            res = subprocess.run(cmd, cwd=self.repo_dir, capture_output=True, text=True, shell=True, timeout=60)
            combined_output = (res.stdout + "\n" + res.stderr).strip()
            passed = res.returncode == 0
            return ToolResult(
                success=passed,
                output=combined_output[:4000],
                metadata={"exit_code": res.returncode, "passed": passed},
            )
        except Exception as e:
            return ToolResult(success=False, output=f"Test execution error: {str(e)}")

    def apply_patch(self, filepath: str, new_content: str) -> ToolResult:
        """Overwrite file content with updated code."""
        target_path = (self.repo_dir / filepath).resolve()
        if not target_path.is_relative_to(self.repo_dir):
            return ToolResult(success=False, output="Security Error: File path outside workspace boundary.")

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return ToolResult(success=True, output=f"Successfully updated file: '{filepath}'.")
        except Exception as e:
            return ToolResult(success=False, output=f"Failed to apply patch to '{filepath}': {str(e)}")


def get_agent_tools_schema() -> List[Dict[str, Any]]:
    """Return JSON Schema definitions for agentic LLM tool calling."""
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
            "description": "Search repository codebase for functions, classes, symbols, or error messages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search regex pattern or exact string."},
                    "file_pattern": {"type": "string", "description": "Optional file extension filter (e.g. '.py')."},
                },
                "required": ["query"],
            },
        },
        {
            "name": "git_diff",
            "description": "Get git diff for current working changes or commit range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "revision": {"type": "string", "description": "Git revision or range, default 'HEAD~1..HEAD'."}
                },
                "required": [],
            },
        },
        {
            "name": "run_test",
            "description": "Run project test suite to verify whether current code passes tests.",
            "parameters": {
                "type": "object",
                "properties": {
                    "custom_command": {"type": "string", "description": "Optional custom test command."}
                },
                "required": [],
            },
        },
        {
            "name": "apply_patch",
            "description": "Write updated replacement code to target file.",
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
