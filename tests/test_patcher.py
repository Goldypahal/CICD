import tempfile
from pathlib import Path
from gitfix.patcher import CodePatcher

def test_apply_and_rollback_fix_payload():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        target_file = root / "src" / "math.py"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")

        patcher = CodePatcher(root)
        payload = [
            {
                "path": "src/math.py",
                "content": "def add(a, b):\n    return a + b\n"
            }
        ]

        success, modified, backups = patcher.apply_fix_payload(payload)
        assert success is True
        assert modified == ["src/math.py"]
        assert target_file.read_text(encoding="utf-8") == "def add(a, b):\n    return a + b\n"

        # Test rollback
        patcher.rollback(backups)
        assert target_file.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"
