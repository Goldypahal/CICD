from pathlib import Path
from typing import Optional
from .base import BaseDetector, ProjectInfo

class PythonDetector(BaseDetector):
    def detect(self) -> Optional[ProjectInfo]:
        pyproject = self.root_dir / "pyproject.toml"
        setup_py = self.root_dir / "setup.py"
        req_txt = self.root_dir / "requirements.txt"
        pipfile = self.root_dir / "Pipfile"

        config_files = []
        if pyproject.exists(): config_files.append("pyproject.toml")
        if setup_py.exists(): config_files.append("setup.py")
        if req_txt.exists(): config_files.append("requirements.txt")
        if pipfile.exists(): config_files.append("Pipfile")

        if not config_files and not list(self.root_dir.glob("*.py")):
            return None

        package_manager = "pip"
        if pipfile.exists():
            package_manager = "pipenv"
        elif (self.root_dir / "poetry.lock").exists():
            package_manager = "poetry"
        elif (self.root_dir / "uv.lock").exists():
            package_manager = "uv"

        # Framework detection
        framework = None
        content = ""
        if req_txt.exists():
            try:
                content += req_txt.read_text(encoding="utf-8")
            except Exception:
                pass
        if pyproject.exists():
            try:
                content += pyproject.read_text(encoding="utf-8")
            except Exception:
                pass

        if "fastapi" in content.lower():
            framework = "FastAPI"
        elif "django" in content.lower():
            framework = "Django"
        elif "flask" in content.lower():
            framework = "Flask"

        # Test command detection
        test_framework = "pytest"
        test_command = "pytest"
        if package_manager == "poetry":
            test_command = "poetry run pytest"
        elif package_manager == "uv":
            test_command = "uv run pytest"

        entry_point = None
        if (self.root_dir / "app" / "main.py").exists():
            entry_point = "app/main.py"
        elif (self.root_dir / "main.py").exists():
            entry_point = "main.py"

        return ProjectInfo(
            language="Python",
            framework=framework,
            package_manager=package_manager,
            test_framework=test_framework,
            test_command=test_command,
            build_command=None,
            lint_command="flake8" if (self.root_dir / ".flake8").exists() else None,
            entry_point=entry_point,
            config_files=config_files,
        )
