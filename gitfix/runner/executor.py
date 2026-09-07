import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

@dataclass
class ExecutionResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    passed: bool

TestExecutionResult = ExecutionResult


class TestExecutor:
    def __init__(self, root_dir: Optional[Path] = None, timeout: int = 120):
        self.root_dir = Path(root_dir or Path.cwd()).resolve()
        self.timeout = timeout

    def run_command(self, command: str) -> ExecutionResult:
        if not command:
            return ExecutionResult(command="", exit_code=0, stdout="", stderr="", passed=True)

        try:
            res = subprocess.run(
                command,
                shell=True,
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
            passed = res.returncode == 0
            return ExecutionResult(
                command=command,
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                passed=passed,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Command execution timed out after {self.timeout} seconds.",
                passed=False,
            )
        except Exception as e:
            return ExecutionResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Execution error: {e}",
                passed=False,
            )
