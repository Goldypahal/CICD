import os
import subprocess
import time
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
    execution_time: float = 0.0

    @property
    def output(self) -> str:
        """Combined stdout + stderr. Test runners split diagnostics across both streams."""
        return "\n".join(part for part in (self.stdout, self.stderr) if part).strip()


TestExecutionResult = ExecutionResult

# Python's bytecode cache is validated by source mtime (whole seconds) + size. A same-size fix
# written within a second of the previous test run would be judged against stale bytecode.
TEST_ENV = {"PYTHONDONTWRITEBYTECODE": "1"}


class TestExecutor:
    """Runs commands directly on the host. Only used when the Docker sandbox is disabled."""

    __test__ = False  # not a pytest test class

    def __init__(self, root_dir: Optional[Path] = None, timeout: int = 120):
        self.root_dir = Path(root_dir or Path.cwd()).resolve()
        self.timeout = timeout

    def run_command(self, command: str) -> ExecutionResult:
        if not command:
            return ExecutionResult(command="", exit_code=0, stdout="", stderr="", passed=True)

        start = time.time()
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
                env={**os.environ, **TEST_ENV},
            )
            return ExecutionResult(
                command=command,
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                passed=res.returncode == 0,
                execution_time=time.time() - start,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Command execution timed out after {self.timeout} seconds.",
                passed=False,
                execution_time=float(self.timeout),
            )
        except Exception as e:
            return ExecutionResult(
                command=command,
                exit_code=-1,
                stdout="",
                stderr=f"Execution error: {e}",
                passed=False,
            )
