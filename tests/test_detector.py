import tempfile
from pathlib import Path
from gitfix.detector import detect_project

def test_detect_python_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "pyproject.toml").write_text('[tool.poetry]\nname="sample"\n[tool.poetry.dependencies]\nfastapi="^0.100"', encoding="utf-8")
        info = detect_project(root)
        assert info.language == "Python"
        assert info.framework == "FastAPI"
        assert info.test_command == "pytest"

def test_detect_node_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "package.json").write_text('{"scripts": {"test": "jest"}, "dependencies": {"next": "^14.0"}}', encoding="utf-8")
        info = detect_project(root)
        assert info.language == "JavaScript"
        assert info.framework == "Next.js"
        assert info.test_command == "npm test"

def test_detect_java_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "pom.xml").write_text("<project></project>", encoding="utf-8")
        info = detect_project(root)
        assert info.language == "Java"
        assert info.package_manager == "Maven"
        assert info.test_command == "mvn test"

def test_detect_golang_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "go.mod").write_text("module example.com/app", encoding="utf-8")
        info = detect_project(root)
        assert info.language == "Go"
        assert info.test_command == "go test ./..."

def test_detect_rust_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "Cargo.toml").write_text('[package]\nname="sample"', encoding="utf-8")
        info = detect_project(root)
        assert info.language == "Rust"
        assert info.test_command == "cargo test"
