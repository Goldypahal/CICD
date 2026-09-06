from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

@dataclass
class ProjectInfo:
    language: str
    framework: Optional[str] = None
    package_manager: Optional[str] = None
    test_framework: Optional[str] = None
    test_command: str = ""
    build_command: Optional[str] = None
    lint_command: Optional[str] = None
    entry_point: Optional[str] = None
    config_files: List[str] = field(default_factory=list)

class BaseDetector:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir

    def detect(self) -> Optional[ProjectInfo]:
        raise NotImplementedError
