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
        detector = detector_cls(target_dir)
        info = detector.detect()
        if info:
            return info
            
    # Default fallback if unknown
    return ProjectInfo(
        language="Unknown",
        test_command="pytest" if list(target_dir.glob("*.py")) else "npm test",
    )
