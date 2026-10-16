import pytest
from pathlib import Path
from gitfix.llm.nemotron import NemotronProvider
from gitfix.llm import get_llm_provider
from gitfix.config import Config, DEFAULT_CONFIG
from gitfix.runner.docker_sandbox import DockerSandboxRunner, SandboxConfig

def test_nemotron_requires_api_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    provider = NemotronProvider()
    assert provider.api_key is None
    res = provider.generate_fix("dummy prompt")
    assert "NVIDIA_API_KEY environment variable is not configured" in res["explanation"]
    assert res["files"] == []

def test_unknown_provider_raises_error():
    with pytest.raises(ValueError, match="Unsupported LLM provider 'unknown_provider'"):
        get_llm_provider(provider_name="unknown_provider")

def test_config_deepcopy_isolation(tmp_path: Path):
    cfg1 = Config(str(tmp_path))
    # Mutate nested dictionary in cfg1
    cfg1._data["agent"]["model"] = "custom-mutated-model"
    
    # Verify DEFAULT_CONFIG was not mutated
    assert DEFAULT_CONFIG["agent"]["model"] != "custom-mutated-model"

def test_docker_sandbox_fails_closed_when_unavailable(tmp_path: Path):
    runner = DockerSandboxRunner(tmp_path, SandboxConfig(allow_host_fallback=False))
    # Force docker_available to False
    runner.docker_available = False
    result = runner.run_sandbox_test("echo 'untrusted'")
    assert result.passed is False
    assert result.exit_code == -1
    assert "failed closed" in result.stderr.lower()

def test_pre_audit_blocks_disallowed_file_before_write(tmp_path: Path):
    from gitfix.agents.security_agent import SecurityAgent
    from gitfix.llm.tools import AgentTools

    sec_agent = SecurityAgent(tmp_path)
    tools = AgentTools(tmp_path, security_agent=sec_agent)
    
    blocked_path = ".github/workflows/malicious.yml"
    res = tools.apply_patch(blocked_path, "name: evil\non: push\n")
    assert res.success is False
    assert "Security Policy Blocked" in res.output
    # Ensure file was NEVER created on disk
    assert not (tmp_path / blocked_path).exists()

def test_pre_audit_blocks_dangerous_content_payload(tmp_path: Path):
    from gitfix.agents.security_agent import SecurityAgent
    from gitfix.llm.tools import AgentTools

    sec_agent = SecurityAgent(tmp_path)
    tools = AgentTools(tmp_path, security_agent=sec_agent)

    target_file = "service.py"
    res = tools.apply_patch(target_file, "def steal():\n    return open('/etc/shadow').read()\n")
    assert res.success is False
    assert "Security Policy Blocked" in res.output
    assert not (tmp_path / target_file).exists()

def test_command_chaining_blocked_in_run_test(tmp_path: Path):
    from gitfix.llm.tools import AgentTools

    tools = AgentTools(tmp_path)
    res = tools.run_test("pytest ; rm -rf /")
    assert res.success is False
    assert "Security Policy Blocked" in res.output

def test_transactional_rollback_in_agent_tools(tmp_path: Path):
    from gitfix.llm.tools import AgentTools

    target = tmp_path / "app.py"
    target.write_text("initial = True\n", encoding="utf-8")

    tools = AgentTools(tmp_path)
    res = tools.apply_patch("app.py", "initial = False\n")
    assert res.success is True
    assert target.read_text(encoding="utf-8") == "initial = False\n"

    # Roll back
    tools.rollback()
    assert target.read_text(encoding="utf-8") == "initial = True\n"

