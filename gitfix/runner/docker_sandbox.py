import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .executor import TestExecutionResult, TestExecutor


@dataclass
class SandboxConfig:
    cpu_limit: str = "2.0"
    memory_limit: str = "2g"
    timeout_seconds: int = 60
    read_only_root: bool = False
    network_disabled: bool = True
    image: str = "python:3.11-slim"


class DockerSandboxRunner:
    """Runs test execution inside a hardened Docker sandbox with resource limits."""

    def __init__(self, repo_dir: Path, config: Optional[SandboxConfig] = None):
        self.repo_dir = Path(repo_dir).resolve()
        self.config = config or SandboxConfig()
        self.fallback_executor = TestExecutor(self.repo_dir, timeout=self.config.timeout_seconds)
        self.docker_available = self._check_docker()

    def _check_docker(self) -> bool:
        """Check if Docker CLI and daemon are responsive."""
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.returncode == 0
        except Exception:
            return False

    def run_sandbox_test(self, command: str) -> TestExecutionResult:
        """Run test command inside Docker container or fallback to local process executor."""
        if not self.docker_available:
            print("[DockerSandbox] ⚠️ Docker daemon unavailable. Falling back to local process runner.")
            return self.fallback_executor.run_command(command)

        print(f"[DockerSandbox] 🛡️ Running test in Docker sandbox (CPUs={self.config.cpu_limit}, Mem={self.config.memory_limit})...")
        
        docker_cmd = [
            "docker", "run", "--rm",
            "--cpus", self.config.cpu_limit,
            "--memory", self.config.memory_limit,
            "-v", f"{self.repo_dir}:/workspace",
            "-w", "/workspace",
        ]

        if self.config.network_disabled:
            docker_cmd.extend(["--network", "none"])

        docker_cmd.extend([self.config.image, "sh", "-c", command])

        try:
            res = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds,
            )
            passed = res.returncode == 0
            return TestExecutionResult(
                command=command,
                passed=passed,
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                execution_time=0.0,
            )
        except subprocess.TimeoutExpired:
            return TestExecutionResult(
                command=command,
                passed=False,
                exit_code=-1,
                stdout="",
                stderr=f"Execution timed out after {self.config.timeout_seconds}s in Docker sandbox.",
                execution_time=float(self.config.timeout_seconds),
            )
        except Exception as e:
            print(f"[DockerSandbox] ❌ Docker error: {str(e)}. Falling back to local runner.")
            return self.fallback_executor.run_command(command)
