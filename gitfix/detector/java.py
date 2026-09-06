from pathlib import Path
from typing import Optional
from .base import BaseDetector, ProjectInfo

class JavaDetector(BaseDetector):
    def detect(self) -> Optional[ProjectInfo]:
        pom_xml = self.root_dir / "pom.xml"
        build_gradle = self.root_dir / "build.gradle"
        build_gradle_kts = self.root_dir / "build.gradle.kts"

        if not (pom_xml.exists() or build_gradle.exists() or build_gradle_kts.exists()):
            return None

        if pom_xml.exists():
            return ProjectInfo(
                language="Java",
                package_manager="Maven",
                test_framework="JUnit",
                test_command="mvn test",
                build_command="mvn compile",
                config_files=["pom.xml"],
            )
        else:
            cmd = "./gradlew test" if (self.root_dir / "gradlew").exists() else "gradle test"
            build_cmd = "./gradlew build" if (self.root_dir / "gradlew").exists() else "gradle build"
            cfg = "build.gradle" if build_gradle.exists() else "build.gradle.kts"
            return ProjectInfo(
                language="Java",
                package_manager="Gradle",
                test_framework="JUnit",
                test_command=cmd,
                build_command=build_cmd,
                config_files=[cfg],
            )
