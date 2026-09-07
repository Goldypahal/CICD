from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..runner.docker_sandbox import DockerSandboxRunner, SandboxConfig
from ..runner.executor import TestExecutionResult


@dataclass
class VerificationResult:
    passed: bool
    execution_result: TestExecutionResult
    environment: str


class VerificationAgent:
    """Verifies generated patches by executing test suites in Docker sandboxes or isolated processes."""

    def __init__(self, repo_dir: Path, use_sandbox: bool = True):
        self.repo_dir = Path(repo_dir).resolve()
        self.use_sandbox = use_sandbox
        self.sandbox_runner = DockerSandboxRunner(self.repo_dir, SandboxConfig())

    def verify(self, test_command: str) -> VerificationResult:
        print("[VerificationAgent] 🧪 Running test suite verification...")
        if self.use_sandbox:
            res = self.sandbox_runner.run_sandbox_test(test_command)
            env = "docker_sandbox" if self.sandbox_runner.docker_available else "local_process"
        else:
            res = self.sandbox_runner.fallback_executor.run_command(test_command)
            env = "local_process"

        return VerificationResult(
            passed=res.passed,
            execution_result=res,
            environment=env,
        )
