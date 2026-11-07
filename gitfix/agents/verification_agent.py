import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..runner.docker_sandbox import DockerSandboxRunner, SandboxConfig
from ..runner.executor import ExecutionResult, TestExecutionResult, TestExecutor


@dataclass
class VerificationResult:
    passed: bool
    execution_result: TestExecutionResult
    environment: str


class VerificationAgent:
    """Single entry point for executing test commands.

    Every test run in the pipeline (regression baseline, the agent's own run_test tool,
    and final verification) goes through this class, so the sandbox setting applies
    uniformly. AI-written code is never executed on the host while the sandbox is on.
    """

    def __init__(
        self,
        repo_dir: Path,
        use_sandbox: bool = True,
        sandbox_config: Optional[SandboxConfig] = None,
        timeout_seconds: int = 300,
        _docker_available: Optional[bool] = None,
    ):
        self.repo_dir = Path(repo_dir).resolve()
        self.use_sandbox = use_sandbox
        self.timeout_seconds = timeout_seconds
        self.sandbox_config = sandbox_config or SandboxConfig(timeout_seconds=timeout_seconds)
        self._docker_available = _docker_available
        self.host_executor = TestExecutor(self.repo_dir, timeout=timeout_seconds)
        self.sandbox_runner: Optional[DockerSandboxRunner] = None
        if use_sandbox:
            self.sandbox_runner = DockerSandboxRunner(self.repo_dir, self.sandbox_config, docker_available=_docker_available)

    @property
    def environment(self) -> str:
        return "docker_sandbox" if self.use_sandbox else "local_process"

    def run(self, command: str) -> ExecutionResult:
        if self.sandbox_runner is not None:
            return self.sandbox_runner.run_command(command)
        return self.host_executor.run_command(command)

    def verify(self, test_command: str) -> VerificationResult:
        print(f"[VerificationAgent] 🧪 Running test suite ({self.environment})...")
        res = self.run(test_command)
        return VerificationResult(passed=res.passed, execution_result=res, environment=self.environment)

    def for_directory(self, directory: Path) -> "VerificationAgent":
        """Same execution policy, bound to another checkout (e.g. a baseline worktree)."""
        return VerificationAgent(
            directory,
            use_sandbox=self.use_sandbox,
            sandbox_config=dataclasses.replace(self.sandbox_config),
            timeout_seconds=self.timeout_seconds,
            _docker_available=self._docker_available,
        )

    def cleanup(self) -> None:
        if self.sandbox_runner is not None:
            self.sandbox_runner.cleanup()
