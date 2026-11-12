from pathlib import Path
from typing import Optional
from .base import BaseDetector, ProjectInfo

PIP_INSTALL = (
    "pip install -q pytest"
    " && if [ -f requirements.txt ]; then pip install -q -r requirements.txt; fi"
    " && if [ -f requirements-dev.txt ]; then pip install -q -r requirements-dev.txt; fi"
    " && if [ -f pyproject.toml ] || [ -f setup.py ]; then pip install -q -e '.[dev]' || pip install -q -e .; fi"
)


class PythonDetector(BaseDetector):
    """Strict mode needs a Python manifest. Loose mode (used only after every other
    detector has declined) also accepts bare *.py files at the repo root."""

    loose: bool = False

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

        if not config_files and not (self.loose and list(self.root_dir.glob("*.py"))):
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
        install_command = PIP_INSTALL
        if package_manager == "poetry":
            test_command = "poetry run pytest"
            install_command = "pip install -q poetry && poetry install --no-interaction"
        elif package_manager == "uv":
            test_command = "uv run pytest"
            install_command = "pip install -q uv && uv sync"
        elif package_manager == "pipenv":
            install_command = "pip install -q pipenv pytest && pipenv install --dev --system"

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
            install_command=install_command,
            sandbox_image="python:3.11-slim",
        )
