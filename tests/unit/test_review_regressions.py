"""Regression tests for the issues found in the end-to-end review.

Each test reproduces a concrete failure from the original pipeline.
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

from gitfix.agents.orchestrator import GitFixOrchestrator
from gitfix.agents.regression_agent import RegressionAgent
from gitfix.agents.security_agent import SecurityAgent, is_test_file
from gitfix.analyzer.stack_trace import StackTraceParser
from gitfix.cli import cli
from gitfix.config import Config
from gitfix.detector import detect_project
from gitfix.git.pr_manager import GitHubPRManager
from gitfix.git.repo_manager import GitRepoManager
from gitfix.git.watcher import HOOK_MARKER, GitWatcher
from gitfix.llm.mock_provider import MockLLMProvider
from gitfix.llm.provider import BaseLLMProvider
from gitfix.llm.tools import AgentTools
from gitfix.patcher import PatchError, apply_unified_diff
from gitfix.runner import docker_sandbox
from gitfix.runner.docker_sandbox import DockerSandboxRunner, SandboxConfig

PYTEST = f"{sys.executable} -m pytest -q -p no:cacheprovider"
GOOD = "def multiply(a, b):\n    return a * b\n"
BAD = "def multiply(a, b):\n    return a + b\n"
TEST = "from app import multiply\n\ndef test_multiply():\n    assert multiply(3, 4) == 12\n"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def regressed_repo(tmp_path: Path) -> Path:
    """Two commits: a passing baseline, then a commit that breaks multiply()."""
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "app.py").write_text(GOOD)
    (tmp_path / "test_app.py").write_text(TEST)
    (tmp_path / ".gitignore").write_text(".gitfix/\n__pycache__/\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    (tmp_path / "app.py").write_text(BAD)
    git(tmp_path, "commit", "-qam", "introduce bug")
    return tmp_path


def make_config(root: Path, **agent: Any) -> Config:
    cfg = Config(str(root))
    cfg._data["validation"]["test_command"] = PYTEST
    cfg._data["agent"]["max_retries"] = agent.pop("max_retries", 2)
    cfg._data["agent"].update(agent)
    return cfg


class ScriptedLLM(BaseLLMProvider):
    """Returns queued responses in order and records every prompt it receives."""

    def __init__(self, responses: List[Dict[str, Any]]):
        super().__init__(model="scripted")
        self.responses = list(responses)
        self.prompts: List[str] = []

    def generate_fix(self, prompt: str) -> Dict[str, Any]:
        self.prompts.append(prompt)
        return self.responses.pop(0) if self.responses else {"explanation": "give up"}


# --------------------------------------------------------------------------- action / CLI
def test_cli_accepts_exact_flags_built_by_action_yml():
    """action.yml used to pass `--auto-pr=true --sandbox=true`, which click rejects."""
    ctx = cli.commands["fix"].make_context(
        "fix", ["--auto-pr", "--sandbox", "--provider", "gemini", "--model", "gemini-2.5-flash", "--base-branch", "main"]
    )
    assert ctx.params["auto_pr"] is True and ctx.params["sandbox"] is True
    assert ctx.params["base_branch"] == "main"

    action = Path(__file__).resolve().parents[2] / "action.yml"
    text = action.read_text()
    assert "--auto-pr=" not in text and "--sandbox=" not in text
    assert 'pip install "${{ github.action_path }}"' in text


# --------------------------------------------------------------------------- git safety
def test_regression_check_keeps_detached_head_in_place(regressed_repo: Path):
    """CI checks out a detached SHA. The old code ran `git checkout HEAD` to 'go back' and stayed on HEAD~1."""
    git(regressed_repo, "checkout", "-q", "--detach", "HEAD")
    before = git(regressed_repo, "rev-parse", "HEAD")

    res = RegressionAgent(regressed_repo, PYTEST).analyze_regression()

    assert res.is_regression and res.baseline_passed and not res.current_passed
    assert git(regressed_repo, "rev-parse", "HEAD") == before
    assert (regressed_repo / "app.py").read_text() == BAD
    assert git(regressed_repo, "worktree", "list").count("\n") == 0  # temp worktree cleaned up


def test_refuses_to_run_on_dirty_tree_and_preserves_edits(regressed_repo: Path):
    (regressed_repo / "test_app.py").write_text(TEST + "# my unsaved notes\n")
    llm = MockLLMProvider(mock_files=[{"path": "app.py", "content": GOOD}])

    res = GitFixOrchestrator(regressed_repo, make_config(regressed_repo), llm, use_sandbox=False).run_repair_flow(auto_commit=True)

    assert res.success is False and "Uncommitted changes" in res.summary
    assert "my unsaved notes" in (regressed_repo / "test_app.py").read_text()
    assert (regressed_repo / "app.py").read_text() == BAD


def test_failed_run_reverts_only_its_own_edits_and_returns_to_branch(regressed_repo: Path):
    (regressed_repo / "scratch.txt").write_text("untracked user file\n")
    still_broken = "def multiply(a, b):\n    return a - b\n"
    llm = MockLLMProvider(mock_files=[{"path": "app.py", "content": still_broken}, {"path": "helper.py", "content": "x = 1\n"}])

    res = GitFixOrchestrator(regressed_repo, make_config(regressed_repo, max_retries=1), llm, use_sandbox=False).run_repair_flow()

    assert res.success is False
    assert (regressed_repo / "scratch.txt").read_text() == "untracked user file\n"
    assert (regressed_repo / "app.py").read_text() == BAD
    assert not (regressed_repo / "helper.py").exists()
    assert git(regressed_repo, "branch", "--show-current") == "main"
    assert "ai/fix-" not in git(regressed_repo, "branch", "--list")


def test_post_commit_hook_does_not_clobber_existing_hook(tmp_path: Path):
    git(tmp_path, "init", "-q")
    hook = tmp_path / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho mine\n")
    assert GitWatcher(GitRepoManager(tmp_path)).install_post_commit_hook() is False
    assert hook.read_text() == "#!/bin/sh\necho mine\n"

    hook.unlink()
    assert GitWatcher(GitRepoManager(tmp_path)).install_post_commit_hook() is True
    text = hook.read_text()
    assert HOOK_MARKER in text and "GITFIX_RUNNING" in text and "--auto-commit" not in text


# --------------------------------------------------------------------------- verification integrity
def test_fix_that_guts_the_test_is_rejected(regressed_repo: Path):
    llm = MockLLMProvider(mock_files=[{"path": "test_app.py", "content": "def test_multiply():\n    assert True\n"}])

    res = GitFixOrchestrator(regressed_repo, make_config(regressed_repo), llm, use_sandbox=False).run_repair_flow(auto_commit=True)

    assert res.success is False
    assert (regressed_repo / "test_app.py").read_text() == TEST
    assert git(regressed_repo, "log", "-1", "--format=%s") == "introduce bug"


@pytest.mark.parametrize("path", ["test_app.py", "tests/helpers.py", "pkg/foo_test.py", "src/a.spec.ts", "conftest.py", "x/FooTest.java", "./tests/x.py"])
def test_test_file_detection(path: str):
    assert is_test_file(path)
    assert SecurityAgent(Path("/tmp")).audit_file_modification(path)[0] is False


@pytest.mark.parametrize("path", ["app.py", "src/latest.py", "contest.py", ".github_utils.py"])
def test_non_test_files_allowed(path: str):
    assert not is_test_file(path)


def test_allow_test_edits_opt_in(tmp_path: Path):
    assert SecurityAgent(tmp_path, allow_test_edits=True).audit_file_modification("tests/test_x.py")[0] is True


def test_successful_repair_commits_and_records_memory(regressed_repo: Path):
    llm = MockLLMProvider(mock_files=[{"path": "app.py", "content": GOOD}], explanation="use * not +")
    orch = GitFixOrchestrator(regressed_repo, make_config(regressed_repo), llm, use_sandbox=False)

    res = orch.run_repair_flow(auto_commit=True)

    assert res.success and res.retries_used == 1 and res.modified_files == ["app.py"]
    assert (regressed_repo / "app.py").read_text() == GOOD
    assert git(regressed_repo, "log", "-1", "--format=%s").startswith("fix(ai-agent)")
    records = json.loads((regressed_repo / ".gitfix" / "history.json").read_text())
    assert records[0]["summary"] == "use * not +" and "return a * b" in records[0]["patch_diff"]


def test_memory_is_fed_back_into_the_prompt(regressed_repo: Path):
    (regressed_repo / ".gitfix").mkdir()
    (regressed_repo / ".gitfix" / "history.json").write_text(json.dumps([{
        "error_type": "AssertionError", "error_message": "assert 7 == 12", "summary": "PAST-FIX-MARKER",
        "commit_hash": "abc", "modified_files": [], "patch_diff": "",
    }]))
    llm = ScriptedLLM([{"explanation": "fix", "files": [{"path": "app.py", "content": GOOD}]}])

    res = GitFixOrchestrator(regressed_repo, make_config(regressed_repo), llm, use_sandbox=False).run_repair_flow(auto_commit=True)

    assert res.success
    assert "PAST-FIX-MARKER" in llm.prompts[0]


# --------------------------------------------------------------------------- tool-calling loop
def test_tool_schema_is_sent_and_tool_calls_are_executed(regressed_repo: Path):
    llm = ScriptedLLM([
        {"tool_calls": [{"name": "read_file", "args": {"filepath": "app.py"}}], "explanation": "look"},
        {"tool_calls": [{"name": "apply_patch", "args": {"filepath": "app.py", "new_content": GOOD}}], "explanation": "fix op"},
    ])

    res = GitFixOrchestrator(regressed_repo, make_config(regressed_repo), llm, use_sandbox=False).run_repair_flow(auto_commit=True)

    assert res.success
    first = json.loads(llm.prompts[0])
    assert first[0]["role"] == "system" and '"apply_patch"' in first[0]["content"] and "tool_calls" in first[0]["content"]
    second = json.loads(llm.prompts[1])
    assert any(m["role"] == "tool" and "return a + b" in m["content"] for m in second)


def test_failing_fix_feeds_test_output_back_to_model(regressed_repo: Path):
    llm = ScriptedLLM([
        {"explanation": "try 1", "files": [{"path": "app.py", "content": "def multiply(a, b):\n    return a - b\n"}]},
        {"explanation": "try 2", "files": [{"path": "app.py", "content": GOOD}]},
    ])
    res = GitFixOrchestrator(regressed_repo, make_config(regressed_repo), llm, use_sandbox=False).run_repair_flow(auto_commit=True)
    assert res.success
    assert "assert -1 == 12" in llm.prompts[1]


def test_unconfigured_provider_fails_fast(regressed_repo: Path, monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    cfg = make_config(regressed_repo)
    cfg._data["agent"]["provider"] = "nemotron"

    res = GitFixOrchestrator(regressed_repo, cfg, use_sandbox=False).run_repair_flow(auto_pr=True)

    assert res.success is False and "NVIDIA_API_KEY" in res.summary
    assert "ai/fix-" not in git(regressed_repo, "branch", "--list")


def test_custom_test_command_must_narrow_project_command(tmp_path: Path):
    tools = AgentTools(tmp_path, test_command="pytest")
    assert "must start with" in tools.run_test("python -c 'import os'").output
    assert "Security Policy Blocked" in tools.run_test("pytest > /tmp/x").output


# --------------------------------------------------------------------------- sandbox
def test_every_test_run_goes_through_the_sandbox(regressed_repo: Path, monkeypatch):
    """Previously the agent loop and regression check ran tests on the host even with --sandbox."""
    calls: List[str] = []

    def fake_run(self, command):
        calls.append(str(self.repo_dir))
        return self.fallback_executor.run_command(command)

    monkeypatch.setattr(DockerSandboxRunner, "run_command", fake_run)
    llm = MockLLMProvider(mock_files=[{"path": "app.py", "content": GOOD}])
    orch = GitFixOrchestrator(regressed_repo, make_config(regressed_repo), llm, use_sandbox=True, _docker_available=True)
    host_calls: List[str] = []
    monkeypatch.setattr(orch.verification_agent.host_executor, "run_command", lambda c: host_calls.append(c))

    res = orch.run_repair_flow(auto_commit=True)

    assert res.success
    assert host_calls == []
    # current HEAD, baseline worktree, agent's run_test, final verification
    assert len(calls) >= 4
    assert any(c != str(regressed_repo) for c in calls), "baseline should run in a separate worktree"


def test_sandbox_installs_deps_with_network_then_tests_without(tmp_path: Path, monkeypatch):
    seen: List[List[str]] = []

    def fake_subprocess_run(cmd, **kwargs):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(docker_sandbox.subprocess, "run", fake_subprocess_run)
    runner = DockerSandboxRunner(tmp_path, SandboxConfig(image="python:3.11-slim", setup_command="pip install pytest"), docker_available=True)

    assert runner.run_command("pytest").passed
    assert runner.run_command("pytest").passed  # setup image is reused

    setup_runs = [c for c in seen if c[:2] == ["docker", "run"] and "pip install pytest" in c]
    test_runs = [c for c in seen if c[:2] == ["docker", "run"] and c[-1] == "pytest"]
    commits = [c for c in seen if c[:2] == ["docker", "commit"]]
    assert len(setup_runs) == 1 and "none" not in setup_runs[0]
    assert len(commits) == 1
    tag = commits[0][-1]
    assert len(test_runs) == 2
    for c in test_runs:
        assert c[c.index("--network") + 1] == "none" and tag in c

    runner.cleanup()
    assert ["docker", "rmi", "-f", tag] in seen


def test_sandbox_setup_failure_is_reported(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        docker_sandbox.subprocess, "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1 if "run" in cmd[:2] else 0, stdout="", stderr="no such package"),
    )
    runner = DockerSandboxRunner(tmp_path, SandboxConfig(setup_command="pip install nope"), docker_available=True)
    res = runner.run_command("pytest")
    assert not res.passed and "setup failed" in res.stderr and "no such package" in res.stderr


def test_detected_projects_get_sandbox_image_and_install_command(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    info = detect_project(tmp_path)
    assert info.sandbox_image == "python:3.11-slim" and "pytest" in info.install_command


def test_node_repo_with_root_python_script_is_not_python(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
    (tmp_path / "build_helper.py").write_text("print(1)\n")
    info = detect_project(tmp_path)
    assert info.language == "JavaScript" and info.sandbox_image == "node:20-slim"


# --------------------------------------------------------------------------- patching / parsing
def test_unified_diff_preserves_rest_of_file():
    orig = "".join(f"line{i}\n" for i in range(1, 11))
    diff = "--- a/f\n+++ b/f\n@@ -4,3 +4,3 @@\n line4\n-line5\n+LINE5\n line6\n"
    out = apply_unified_diff(orig, diff)
    assert out == orig.replace("line5\n", "LINE5\n")


def test_unified_diff_rejects_mismatched_context():
    with pytest.raises(PatchError):
        apply_unified_diff("a\nb\nc\n", "--- a/f\n+++ b/f\n@@ -1,2 +1,2 @@\n x\n-b\n+B\n")


def test_unified_diff_respects_missing_final_newline():
    assert apply_unified_diff("a\nb", "--- a/f\n+++ b/f\n@@ -1,1 +1,1 @@\n-a\n+A\n") == "A\nb"


def test_apply_patch_tool_applies_diff_instead_of_writing_it_verbatim(tmp_path: Path):
    (tmp_path / "app.py").write_text(BAD)
    diff = "--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n def multiply(a, b):\n-    return a + b\n+    return a * b\n"
    assert AgentTools(tmp_path).apply_patch("app.py", diff).success
    assert (tmp_path / "app.py").read_text() == GOOD


def test_parser_extracts_pytest_error():
    out = (
        "    def test_multiply():\n>       assert multiply(3, 4) == 12\nE       assert 7 == 12\n"
        "E        +  where 7 = multiply(3, 4)\n\ntest_app.py:4: AssertionError\n"
        "FAILED test_app.py::test_multiply - assert 7 == 12\n"
        "E   ZeroDivisionError: division by zero\n"
    )
    parsed = StackTraceParser().parse(out)
    assert parsed.error_type == "ZeroDivisionError" and parsed.error_message == "division by zero"
    assert any(f.filename == "test_app.py" and f.line_number == 4 for f in parsed.frames)


# --------------------------------------------------------------------------- config / PRs
def test_config_test_command_override_is_honored(regressed_repo: Path):
    cfg = Config(str(regressed_repo))
    cfg._data["validation"]["test_command"] = "make check"
    orch = GitFixOrchestrator(regressed_repo, cfg, MockLLMProvider(), use_sandbox=False)
    assert orch.test_command == "make check"


def test_pr_push_failure_is_reported(regressed_repo: Path):
    res = GitHubPRManager(regressed_repo).create_pull_request("ai/fix-x", "t", "b")
    assert res.success is False and res.pr_url is None and "push failed" in res.message.lower()


def test_pr_compare_url_uses_real_remote(regressed_repo: Path):
    git(regressed_repo, "remote", "add", "origin", "git@github.com:Goldypahal/CICD.git")
    url = GitHubPRManager(regressed_repo).compare_url("ai/fix-abc", "main")
    assert url == "https://github.com/Goldypahal/CICD/compare/main...ai/fix-abc?expand=1"


def test_provider_error_aborts_instead_of_retrying(regressed_repo: Path):
    llm = ScriptedLLM([{"error": "400 INVALID_ARGUMENT", "files": []}] * 5)

    res = GitFixOrchestrator(regressed_repo, make_config(regressed_repo, max_retries=5), llm, use_sandbox=False).run_repair_flow()

    assert res.success is False and "400 INVALID_ARGUMENT" in res.summary
    assert res.retries_used == 1 and len(llm.prompts) == 1
    assert git(regressed_repo, "branch", "--show-current") == "main"


def test_gemini_client_uses_v1beta(monkeypatch):
    from google import genai
    from gitfix.llm.gemini import GeminiProvider

    captured = {}

    class FakeModels:
        def generate_content(self, **kw):
            return type("R", (), {"text": '{"explanation": "ok", "files": []}'})()

    class FakeClient:
        def __init__(self, **kw):
            captured.update(kw)
            self.models = FakeModels()

    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.delenv("GEMINI_API_VERSION", raising=False)
    monkeypatch.setattr(genai, "Client", FakeClient)
    assert GeminiProvider().generate_fix("p") == {"explanation": "ok", "files": []}
    assert captured["http_options"].api_version == "v1beta"
