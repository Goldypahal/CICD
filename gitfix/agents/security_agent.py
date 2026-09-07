from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


@dataclass
class SecurityAuditResult:
    is_safe: bool
    blocked_files: List[str]
    violations: List[str]


class SecurityAgent:
    """Scans proposed code modifications to enforce security boundaries."""

    DISALLOWED_PATTERNS = [
        ".github/workflows/",
        ".circleci/",
        "Dockerfile",
        "docker-compose",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        ".env",
        "secrets",
    ]

    def __init__(self, repo_dir: Path, allow_dependency_edits: bool = False):
        self.repo_dir = Path(repo_dir).resolve()
        self.allow_dependency_edits = allow_dependency_edits

    def audit_patch(self, modified_files: List[str]) -> SecurityAuditResult:
        print("[SecurityAgent] 🛡️ Auditing proposed patch files for security policy compliance...")
        blocked: List[str] = []
        violations: List[str] = []

        for filepath in modified_files:
            clean_path = filepath.replace("\\", "/").strip()
            
            for pattern in self.DISALLOWED_PATTERNS:
                if pattern in clean_path:
                    if self.allow_dependency_edits and pattern in ["pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml", "build.gradle"]:
                        continue
                    blocked.append(filepath)
                    violations.append(f"Modification to sensitive infrastructure/dependency file blocked: '{filepath}' (Rule: {pattern})")

        is_safe = len(blocked) == 0
        if is_safe:
            print("[SecurityAgent] ✅ Patch passed all security checks.")
        else:
            print(f"[SecurityAgent] 🛑 Security Policy Violation: Blocked {len(blocked)} file modification(s).")

        return SecurityAuditResult(
            is_safe=is_safe,
            blocked_files=blocked,
            violations=violations,
        )
