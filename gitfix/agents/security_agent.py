import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import List, Tuple


@dataclass
class SecurityAuditResult:
    is_safe: bool
    blocked_files: List[str]
    violations: List[str]


# Files that define what "passing" means. If the agent could edit these it could make
# any failure "pass" by weakening or deleting the test, so they are blocked by default.
TEST_FILE_GLOBS = [
    "test_*.py", "*_test.py", "conftest.py",
    "*.test.js", "*.test.jsx", "*.test.ts", "*.test.tsx", "*.test.mjs", "*.test.cjs",
    "*.spec.js", "*.spec.jsx", "*.spec.ts", "*.spec.tsx", "*.spec.mjs", "*.spec.cjs",
    "*_test.go", "*Test.java", "*Tests.java", "*IT.java",
    "pytest.ini", "tox.ini", "jest.config.*", "vitest.config.*", "karma.conf.*", ".mocharc*",
]
TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "testdata"}


def is_test_file(filepath: str) -> bool:
    clean = filepath.replace("\\", "/").strip()
    while clean.startswith("./"):
        clean = clean[2:]
    p = PurePosixPath(clean)
    if any(part in TEST_DIR_NAMES for part in p.parts[:-1]):
        return True
    return any(fnmatch.fnmatch(p.name, g) for g in TEST_FILE_GLOBS)


class SecurityAgent:
    """Policy check applied to every file the agent tries to write.

    This is a guard-rail, not a sandbox: content patterns catch obvious payloads only.
    Real isolation comes from running tests in the Docker sandbox with no network.
    """

    DEPENDENCY_FILES = [
        "pyproject.toml", "setup.py", "setup.cfg", "requirements", "Pipfile", "poetry.lock", "uv.lock",
        "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", ".npmrc",
        "Cargo.toml", "Cargo.lock", "go.mod", "go.sum", "pom.xml", "build.gradle", "settings.gradle",
    ]

    INFRA_PATTERNS = [
        ".github/", ".circleci/", ".gitlab-ci", "Jenkinsfile", ".git/", ".gitfix/",
        "Dockerfile", "docker-compose", "Makefile", ".env", "secrets", ".pre-commit-config",
    ]

    # Kept for backwards compatibility with code that referenced the old attribute.
    DISALLOWED_PATTERNS = INFRA_PATTERNS + DEPENDENCY_FILES

    DANGEROUS_CONTENT_PATTERNS = [
        r"(?:/etc/passwd|/etc/shadow)",
        r"(?:curl|wget)\s+https?://",
        r"nc\s+-e\s+",
        r"bash\s+-i\s+>&",
        r"powershell\s+-(?:enc|encodedcommand)",
        r"\bGITHUB_TOKEN\b",
        r"\b(?:AWS_SECRET_ACCESS_KEY|GEMINI_API_KEY|OPENAI_API_KEY|NVIDIA_API_KEY)\b",
        r"\.ssh/",
    ]

    def __init__(self, repo_dir: Path, allow_dependency_edits: bool = False, allow_test_edits: bool = False):
        self.repo_dir = Path(repo_dir).resolve()
        self.allow_dependency_edits = allow_dependency_edits
        self.allow_test_edits = allow_test_edits

    def audit_file_modification(self, filepath: str, new_content: str = "") -> Tuple[bool, List[str]]:
        violations: List[str] = []
        clean_path = filepath.replace("\\", "/").strip()

        if not clean_path:
            violations.append("Empty file path.")
            return False, violations

        if ".." in clean_path.split("/") or clean_path.startswith("/"):
            violations.append(f"Directory traversal or absolute path detected: '{filepath}'")

        try:
            target_path = (self.repo_dir / clean_path).resolve()
            if not target_path.is_relative_to(self.repo_dir):
                violations.append(f"File path outside workspace boundary: '{filepath}'")
        except Exception as e:
            violations.append(f"Invalid file path '{filepath}': {e}")

        for pattern in self.INFRA_PATTERNS:
            if pattern in clean_path:
                violations.append(f"Modification to infrastructure file blocked: '{filepath}' (Rule: {pattern})")

        if not self.allow_dependency_edits:
            for pattern in self.DEPENDENCY_FILES:
                if pattern in PurePosixPath(clean_path).name:
                    violations.append(f"Modification to dependency manifest blocked: '{filepath}' (Rule: {pattern})")

        if not self.allow_test_edits and is_test_file(clean_path):
            violations.append(
                f"Modification to test file blocked: '{filepath}'. Fix the code under test instead; "
                "set agent.allow_test_edits: true in .gitfix/config.yaml to permit test edits."
            )

        if new_content:
            for c_pat in self.DANGEROUS_CONTENT_PATTERNS:
                if re.search(c_pat, new_content, re.IGNORECASE):
                    violations.append(f"Potentially dangerous pattern '{c_pat}' detected in proposed fix for '{filepath}'")

        return (len(violations) == 0, violations)

    def audit_patch(self, modified_files: List[str]) -> SecurityAuditResult:
        print("[SecurityAgent] 🛡️ Auditing patched files against security policy...")
        blocked: List[str] = []
        all_violations: List[str] = []

        for filepath in modified_files:
            is_safe, violations = self.audit_file_modification(filepath)
            if not is_safe:
                blocked.append(filepath)
                all_violations.extend(violations)

        if blocked:
            print(f"[SecurityAgent] 🛑 Security Policy Violation: Blocked {len(blocked)} file modification(s).")
        else:
            print("[SecurityAgent] ✅ Patch passed all security checks.")

        return SecurityAuditResult(is_safe=not blocked, blocked_files=blocked, violations=all_violations)
