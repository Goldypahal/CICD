import subprocess
import tempfile
from pathlib import Path
from gitfix.agents.orchestrator import GitFixOrchestrator
from gitfix.llm.mock_provider import MockLLMProvider
from gitfix.config import Config

def test_orchestrator_repair_flow_with_mock_llm():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Initialize git repo in tmpdir
        subprocess.run(["git", "init"], cwd=root, capture_output=True)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=root, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, capture_output=True)

        # Create broken python file and passing test
        app_file = root / "app.py"
        test_file = root / "test_app.py"

        app_file.write_text("def multiply(a, b):\n    return a + b\n", encoding="utf-8")
        test_file.write_text("from app import multiply\ndef test_multiply():\n    assert multiply(3, 4) == 12\n", encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=root, capture_output=True)

        # Setup mock LLM that returns correct code
        mock_llm = MockLLMProvider(
            mock_files=[
                {
                    "path": "app.py",
                    "content": "def multiply(a, b):\n    return a * b\n"
                }
            ],
            explanation="Fixed multiplication logic"
        )

        config = Config(str(root))
        config._data["validation"]["test_command"] = "pytest"
        config._data["git"]["auto_commit"] = True

        orchestrator = GitFixOrchestrator(
            repo_dir=root,
            config=config,
            llm_provider=mock_llm
        )

        result = orchestrator.run_repair_flow(auto_commit=True)
        assert result.success is True
        assert result.retries_used == 1
        assert app_file.read_text(encoding="utf-8") == "def multiply(a, b):\n    return a * b\n"
