from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BenchmarkBug:
    id: str
    language: str
    category: str  # Syntax, Logic, Type, Dependency, Concurrency, API misuse
    description: str
    test_command: str
    target_files: List[str]


class BenchmarkDataset:
    """Multi-language evaluation suite dataset for AI coding agent benchmarking."""

    def __init__(self):
        self.bugs: List[BenchmarkBug] = self._load_default_suite()

    def _load_default_suite(self) -> List[BenchmarkBug]:
        return [
            BenchmarkBug(
                id="py-001",
                language="Python",
                category="Logic Error",
                description="Off-by-one error in array slicing logic.",
                test_command="pytest tests/test_patcher.py",
                target_files=["gitfix/patcher/applier.py"],
            ),
            BenchmarkBug(
                id="py-002",
                language="Python",
                category="Type Error",
                description="Unchecked NoneType dereference in stack trace parser.",
                test_command="pytest tests/test_detector.py",
                target_files=["gitfix/analyzer/stack_trace.py"],
            ),
            BenchmarkBug(
                id="js-001",
                language="Node.js",
                category="Syntax Error",
                description="Missing async await keyword in network request function.",
                test_command="npm test",
                target_files=["src/api.js"],
            ),
            BenchmarkBug(
                id="go-001",
                language="Go",
                category="Concurrency Error",
                description="Data race on shared state map without mutex lock.",
                test_command="go test ./...",
                target_files=["pkg/store.go"],
            ),
            BenchmarkBug(
                id="rs-001",
                language="Rust",
                category="Borrow Checker",
                description="Use of moved value in loop closure.",
                test_command="cargo test",
                target_files=["src/main.rs"],
            ),
        ]

    def get_bugs_by_language(self, language: str) -> List[BenchmarkBug]:
        return [b for b in self.bugs if b.language.lower() == language.lower()]
