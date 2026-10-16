import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Optional


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

    DANGEROUS_CONTENT_PATTERNS = [
        r"(?:/etc/passwd|/etc/shadow)",
        r"(?:curl|wget)\s+https?://",
        r"nc\s+-e\s+",
        r"bash\s+-i\s+>&",
        r"powershell\s+-(?:enc|encodedcommand)",
    ]

    def __init__(self, repo_dir: Path, allow_dependency_edits: bool = False):
        self.repo_dir = Path(repo_dir).resolve()
        self.allow_dependency_edits = allow_dependency_edits

    def audit_file_modification(self, filepath: str, new_content: str = "") -> Tuple[bool, List[str]]:
        """Pre-audit an individual file path and its content before modification."""
        violations: List[str] = []
        clean_path = filepath.replace("\\", "/").strip()

        # Path traversal checks
        if ".." in clean_path.split("/"):
            violations.append(f"Directory traversal detected in filepath: '{filepath}'")

        try:
            target_path = (self.repo_dir / filepath).resolve()
            if not target_path.is_relative_to(self.repo_dir):
                violations.append(f"File path outside workspace boundary: '{filepath}'")
        except Exception as e:
            violations.append(f"Invalid file path '{filepath}': {e}")

        # Disallowed infrastructure and dependency files
        for pattern in self.DISALLOWED_PATTERNS:
            if pattern in clean_path:
                if self.allow_dependency_edits and pattern in [
                    "pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml", "build.gradle"
                ]:
                    continue
                violations.append(
                    f"Modification to sensitive infrastructure/dependency file blocked: '{filepath}' (Rule: {pattern})"
                )

        # Content inspection
        if new_content:
            for c_pat in self.DANGEROUS_CONTENT_PATTERNS:
                if re.search(c_pat, new_content, re.IGNORECASE):
                    violations.append(
                        f"Potentially dangerous payload pattern '{c_pat}' detected in proposed fix for '{filepath}'"
                    )

        return (len(violations) == 0, violations)

    def audit_patch(self, modified_files: List[str]) -> SecurityAuditResult:
        print("[SecurityAgent] 🛡️ Auditing proposed patch files for security policy compliance...")
        blocked: List[str] = []
        all_violations: List[str] = []

        for filepath in modified_files:
            is_safe, violations = self.audit_file_modification(filepath)
            if not is_safe:
                blocked.append(filepath)
                all_violations.extend(violations)

        is_safe = len(blocked) == 0
        if is_safe:
            print("[SecurityAgent] ✅ Patch passed all security checks.")
        else:
            print(f"[SecurityAgent] 🛑 Security Policy Violation: Blocked {len(blocked)} file modification(s).")

        return SecurityAuditResult(
            is_safe=is_safe,
            blocked_files=blocked,
            violations=all_violations,
        )
