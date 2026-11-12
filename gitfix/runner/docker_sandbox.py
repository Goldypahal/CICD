import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from .executor import TEST_ENV, ExecutionResult, TestExecutionResult, TestExecutor

# Base images per detected language. Each one ships the toolchain needed to run that
# language's test command; project dependencies are added by the setup stage below.
DEFAULT_IMAGES = {
    "Python": "python:3.11-slim",
    "JavaScript": "node:20-slim",
    "TypeScript": "node:20-slim",
    "Go": "golang:1.22",
    "Rust": "rust:1",
    "Java": "maven:3.9-eclipse-temurin-17",
}
FALLBACK_IMAGE = "python:3.11-slim"


@dataclass
class SandboxConfig:
    cpu_limit: str = "2.0"
    memory_limit: str = "2g"
    timeout_seconds: int = 300
    read_only_root: bool = False
    network_disabled: bool = True
    image: Optional[str] = None
    # Command that installs the project's test dependencies (e.g. `pip install -e .[dev]`).
    # It runs once, WITH network access, in a separate container that is then snapshotted
    # with `docker commit`. Test runs use that snapshot with networking disabled, so
    # untrusted AI-written code never gets network access.
    setup_command: Optional[str] = None
    allow_host_fallback: bool = False


class DockerSandboxRunner:
    """Runs test commands inside a resource-limited, network-isolated Docker container."""

    def __init__(self, repo_dir: Path, config: Optional[SandboxConfig] = None, docker_available: Optional[bool] = None):
        self.repo_dir = Path(repo_dir).resolve()
        self.config = config or SandboxConfig()
        self.fallback_executor = TestExecutor(self.repo_dir, timeout=self.config.timeout_seconds)
        self.docker_available = self._check_docker() if docker_available is None else docker_available
        self._prepared_image: Optional[str] = None
        self._setup_error: Optional[str] = None
        self._owned_images: List[str] = []

    # ------------------------------------------------------------------ helpers
    def _docker(self, args: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout or self.config.timeout_seconds,
        )

    def _check_docker(self) -> bool:
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
            return res.returncode == 0
        except Exception:
            return False

    @property
    def base_image(self) -> str:
        return self.config.image or FALLBACK_IMAGE

    def _limits(self) -> List[str]:
        args = ["--cpus", self.config.cpu_limit, "--memory", self.config.memory_limit]
        if self.config.read_only_root:
            args.append("--read-only")
        return args

    def _prepare_image(self) -> Tuple[Optional[str], Optional[str]]:
        """Return (image, error). Builds the dependency snapshot once per runner."""
        if self._prepared_image or self._setup_error:
            return self._prepared_image, self._setup_error
        if not self.config.setup_command:
            self._prepared_image = self.base_image
            return self._prepared_image, None

        container = f"gitfix-setup-{uuid.uuid4().hex[:12]}"
        tag = f"gitfix-sandbox:{uuid.uuid4().hex[:12]}"
        print(f"[DockerSandbox] 📦 Installing test dependencies in setup container ({self.base_image})...")
        try:
            res = self._docker(
                ["run", "--name", container, *self._limits(),
                 "-v", f"{self.repo_dir}:/workspace", "-w", "/workspace",
                 self.base_image, "sh", "-c", self.config.setup_command],
                timeout=max(self.config.timeout_seconds, 900),
            )
            if res.returncode != 0:
                self._setup_error = (
                    f"Sandbox dependency setup failed (exit {res.returncode}) running "
                    f"`{self.config.setup_command}`:\n{(res.stdout + res.stderr)[-3000:]}"
                )
                return None, self._setup_error
            commit = self._docker(["commit", container, tag], timeout=300)
            if commit.returncode != 0:
                self._setup_error = f"docker commit failed: {commit.stderr.strip()}"
                return None, self._setup_error
            self._owned_images.append(tag)
            self._prepared_image = tag
            return tag, None
        except subprocess.TimeoutExpired:
            self._setup_error = "Sandbox dependency setup timed out."
            return None, self._setup_error
        except Exception as e:
            self._setup_error = f"Sandbox dependency setup error: {e}"
            return None, self._setup_error
        finally:
            try:
                self._docker(["rm", "-f", container], timeout=60)
            except Exception:
                pass

    def build_run_args(self, image: str, command: str) -> List[str]:
        args = ["run", "--rm", *self._limits(), "-v", f"{self.repo_dir}:/workspace", "-w", "/workspace"]
        for key, value in TEST_ENV.items():
            args.extend(["-e", f"{key}={value}"])
        if self.config.network_disabled:
            args.extend(["--network", "none"])
        args.extend([image, "sh", "-c", command])
        return args

    # ------------------------------------------------------------------ public
    def run_command(self, command: str) -> ExecutionResult:
        """Run a command in the sandbox, failing closed if Docker is unavailable."""
        if not self.docker_available:
            if not self.config.allow_host_fallback:
                msg = (
                    "Docker daemon is unavailable. Test execution failed closed for security. "
                    "Use --no-sandbox to execute tests on the host system."
                )
                print(f"[DockerSandbox] 🛑 {msg}")
                return ExecutionResult(command=command, passed=False, exit_code=-1, stdout="", stderr=msg)
            print("[DockerSandbox] ⚠️ Docker unavailable. Falling back to host execution (allow_host_fallback=True).")
            return self.fallback_executor.run_command(command)

        image, error = self._prepare_image()
        if error:
            return ExecutionResult(command=command, passed=False, exit_code=-1, stdout="", stderr=error)

        print(f"[DockerSandbox] 🛡️ Running in sandbox ({image}, CPUs={self.config.cpu_limit}, Mem={self.config.memory_limit}, network={'off' if self.config.network_disabled else 'on'})")
        start = time.time()
        try:
            res = self._docker(self.build_run_args(image, command))
            return ExecutionResult(
                command=command,
                passed=res.returncode == 0,
                exit_code=res.returncode,
                stdout=res.stdout,
                stderr=res.stderr,
                execution_time=time.time() - start,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                command=command, passed=False, exit_code=-1, stdout="",
                stderr=f"Execution timed out after {self.config.timeout_seconds}s in Docker sandbox.",
                execution_time=float(self.config.timeout_seconds),
            )
        except Exception as e:
            return ExecutionResult(
                command=command, passed=False, exit_code=-1, stdout="",
                stderr=f"Docker sandbox error: {e}. Execution failed closed.",
            )

    # Backwards-compatible name
    run_sandbox_test = run_command

    def cleanup(self) -> None:
        for tag in self._owned_images:
            try:
                self._docker(["rmi", "-f", tag], timeout=120)
            except Exception:
                pass
        self._owned_images.clear()
        self._prepared_image = None
