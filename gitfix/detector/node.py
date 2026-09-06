import json
from pathlib import Path
from typing import Optional
from .base import BaseDetector, ProjectInfo

class NodeDetector(BaseDetector):
    def detect(self) -> Optional[ProjectInfo]:
        pkg_json_path = self.root_dir / "package.json"
        if not pkg_json_path.exists():
            return None

        package_manager = "npm"
        if (self.root_dir / "yarn.lock").exists():
            package_manager = "yarn"
        elif (self.root_dir / "pnpm-lock.yaml").exists():
            package_manager = "pnpm"
        elif (self.root_dir / "bun.lockb").exists():
            package_manager = "bun"

        scripts = {}
        deps = {}
        try:
            with open(pkg_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                scripts = data.get("scripts", {})
                deps.update(data.get("dependencies", {}))
                deps.update(data.get("devDependencies", {}))
        except Exception:
            pass

        language = "TypeScript" if (self.root_dir / "tsconfig.json").exists() else "JavaScript"

        framework = None
        if "next" in deps:
            framework = "Next.js"
        elif "react" in deps:
            framework = "React"
        elif "express" in deps:
            framework = "Express"
        elif "vue" in deps:
            framework = "Vue"

        test_framework = "Jest" if "jest" in deps or "vitest" in deps else None
        
        test_cmd = f"{package_manager} test" if "test" in scripts else f"{package_manager} run test"
        build_cmd = f"{package_manager} run build" if "build" in scripts else None
        lint_cmd = f"{package_manager} run lint" if "lint" in scripts else None

        return ProjectInfo(
            language=language,
            framework=framework,
            package_manager=package_manager,
            test_framework=test_framework,
            test_command=test_cmd,
            build_command=build_cmd,
            lint_command=lint_cmd,
            config_files=["package.json"],
        )
