from pathlib import Path
from typing import Optional
from .base import ProjectInfo
from .python import PythonDetector
from .node import NodeDetector
from .java import JavaDetector
from .golang import GoDetector
from .rust import RustDetector

DETECTORS = [
    PythonDetector,
    NodeDetector,
    JavaDetector,
    GoDetector,
    RustDetector,
]

def detect_project(root_dir: Optional[Path] = None) -> ProjectInfo:
    target_dir = Path(root_dir or Path.cwd()).resolve()
    for detector_cls in DETECTORS:
        info = detector_cls(target_dir).detect()
        if info:
            return info

    # Only now accept a bare *.py file as evidence of a Python project, so that e.g. a
    # Node repo with a helper script at the root isn't misdetected as Python.
    loose = PythonDetector(target_dir)
    loose.loose = True
    info = loose.detect()
    if info:
        return info

    # Default fallback if unknown
    return ProjectInfo(
        language="Unknown",
        test_command="pytest" if list(target_dir.glob("*.py")) else "npm test",
    )
