from pathlib import Path
from typing import Optional
from .base import BaseDetector, ProjectInfo

class GoDetector(BaseDetector):
    def detect(self) -> Optional[ProjectInfo]:
        go_mod = self.root_dir / "go.mod"
        if not go_mod.exists():
            return None

        return ProjectInfo(
            language="Go",
            package_manager="go modules",
            test_framework="go test",
            test_command="go test ./...",
            build_command="go build ./...",
            config_files=["go.mod"],
        )
