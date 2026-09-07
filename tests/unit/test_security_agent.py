from pathlib import Path
from gitfix.agents.security_agent import SecurityAgent


def test_security_agent_allows_normal_code(tmp_path: Path):
    agent = SecurityAgent(tmp_path)
    res = agent.audit_patch(["src/utils.py", "gitfix/cli.py"])
    assert res.is_safe is True
    assert len(res.blocked_files) == 0


def test_security_agent_blocks_sensitive_files(tmp_path: Path):
    agent = SecurityAgent(tmp_path)
    res = agent.audit_patch([".github/workflows/deploy.yml", "src/main.py"])
    assert res.is_safe is False
    assert ".github/workflows/deploy.yml" in res.blocked_files
