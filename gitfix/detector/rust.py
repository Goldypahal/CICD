from pathlib import Path
from typing import Optional
from .base import BaseDetector, ProjectInfo

class RustDetector(BaseDetector):
    def detect(self) -> Optional[ProjectInfo]:
        cargo_toml = self.root_dir / "Cargo.toml"
        if not cargo_toml.exists():
            return None

        return ProjectInfo(
            language="Rust",
            package_manager="cargo",
            test_framework="cargo test",
            test_command="cargo test",
            build_command="cargo build",
            config_files=["Cargo.toml"],
        )
