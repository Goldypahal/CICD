import os
from pathlib import Path
import pytest
from gitfix.llm.tools import AgentTools


def test_agent_tools_read_file(tmp_path: Path):
    test_file = tmp_path / "sample.py"
    test_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    tools = AgentTools(tmp_path)
    res = tools.read_file("sample.py")
    assert res.success is True
    assert "1: def hello():" in res.output
    assert "2:     return 'world'" in res.output


def test_agent_tools_search_code(tmp_path: Path):
    test_file = tmp_path / "app.py"
    test_file.write_text("class UserService:\n    pass\n", encoding="utf-8")

    tools = AgentTools(tmp_path)
    res = tools.search_code("UserService")
    assert res.success is True
    assert "app.py:1: class UserService:" in res.output


def test_agent_tools_apply_patch(tmp_path: Path):
    tools = AgentTools(tmp_path)
    res = tools.apply_patch("new_module.py", "x = 42\n")
    assert res.success is True
    assert (tmp_path / "new_module.py").read_text(encoding="utf-8") == "x = 42\n"
