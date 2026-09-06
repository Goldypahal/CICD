from pathlib import Path
from typing import Dict, List, Optional
from ..git.repo_manager import GitRepoManager

class CodeRetriever:
    def __init__(self, repo_manager: GitRepoManager):
        self.repo_manager = repo_manager

    def get_file_snippet(self, rel_path: str, center_line: Optional[int] = None, window: int = 30) -> Optional[str]:
        content = self.repo_manager.get_file_content(rel_path)
        if not content:
            return None

        lines = content.splitlines()
        if center_line is None or center_line <= 0 or center_line > len(lines):
            # Return full content if small, or trimmed first 150 lines
            if len(lines) <= 150:
                return content
            return "\n".join(lines[:150]) + "\n... [truncated]"

        start = max(0, center_line - window)
        end = min(len(lines), center_line + window)
        snippet_lines = [f"{i+1:4d} | {lines[i]}" for i in range(start, end)]
        return f"File: {rel_path} (Lines {start+1}-{end})\n" + "\n".join(snippet_lines)

    def find_related_test_files(self, changed_files: List[str]) -> List[str]:
        test_files = []
        for file in changed_files:
            p = Path(file)
            stem = p.stem
            # Common test naming conventions
            candidates = [
                f"tests/test_{stem}.py",
                f"tests/{stem}.test.ts",
                f"tests/{stem}.spec.ts",
                f"tests/{stem}Test.java",
                f"{p.parent}/test_{stem}.py",
                f"{p.parent}/{stem}.test.js",
            ]
            for cand in candidates:
                if (self.repo_manager.repo_dir / cand).exists():
                    test_files.append(cand)

        # Also search for any files matching test pattern
        for f in self.repo_manager.repo_dir.rglob("test_*.*"):
            rel = str(f.relative_to(self.repo_manager.repo_dir)).replace("\\", "/")
            if rel not in test_files:
                test_files.append(rel)

        return test_files[:5]
