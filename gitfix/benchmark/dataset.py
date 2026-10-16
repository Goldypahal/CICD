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
    setup_files: Dict[str, str] = field(default_factory=dict)
    buggy_files: Dict[str, str] = field(default_factory=dict)
    required_toolchain: str = "python"


class BenchmarkDataset:
    """Multi-language evaluation suite dataset with concrete, reproducible bug fixtures."""

    def __init__(self):
        self.bugs: List[BenchmarkBug] = self._load_default_suite()

    def _load_default_suite(self) -> List[BenchmarkBug]:
        return [
            BenchmarkBug(
                id="py-001",
                language="Python",
                category="Logic Error",
                description="Off-by-one / inverted percentage calculation in discount computation.",
                test_command="pytest test_math_ops.py",
                target_files=["math_ops.py"],
                setup_files={
                    "math_ops.py": (
                        "def compute_discount(price: float, discount_percent: float) -> float:\n"
                        "    if discount_percent < 0 or discount_percent > 100:\n"
                        "        raise ValueError('Invalid discount')\n"
                        "    return price * (1.0 - discount_percent / 100.0)\n"
                    ),
                    "test_math_ops.py": (
                        "from math_ops import compute_discount\n\n"
                        "def test_compute_discount():\n"
                        "    assert compute_discount(100.0, 20.0) == 80.0\n"
                        "    assert compute_discount(50.0, 10.0) == 45.0\n"
                    ),
                },
                buggy_files={
                    "math_ops.py": (
                        "def compute_discount(price: float, discount_percent: float) -> float:\n"
                        "    if discount_percent < 0 or discount_percent > 100:\n"
                        "        raise ValueError('Invalid discount')\n"
                        "    # Bug: Returns discount amount rather than discounted price\n"
                        "    return price * (discount_percent / 100.0)\n"
                    ),
                },
                required_toolchain="python",
            ),
            BenchmarkBug(
                id="py-002",
                language="Python",
                category="Type Error",
                description="Unchecked NoneType dereference in user profile display name extractor.",
                test_command="pytest test_user_service.py",
                target_files=["user_service.py"],
                setup_files={
                    "user_service.py": (
                        "def get_user_display_name(user):\n"
                        "    if not user:\n"
                        "        return 'Anonymous'\n"
                        "    return user.get('display_name') or user.get('username', 'Guest')\n"
                    ),
                    "test_user_service.py": (
                        "from user_service import get_user_display_name\n\n"
                        "def test_user_display_name():\n"
                        "    assert get_user_display_name({'display_name': 'Alice'}) == 'Alice'\n"
                        "    assert get_user_display_name(None) == 'Anonymous'\n"
                        "    assert get_user_display_name({}) == 'Guest'\n"
                    ),
                },
                buggy_files={
                    "user_service.py": (
                        "def get_user_display_name(user):\n"
                        "    # Bug: Direct subscription crashes with TypeError when user is None\n"
                        "    return user['display_name']\n"
                    ),
                },
                required_toolchain="python",
            ),
            BenchmarkBug(
                id="js-001",
                language="Node.js",
                category="Syntax Error",
                description="Missing async return and rejected promise error handling.",
                test_command="node test_api.mjs",
                target_files=["api.mjs"],
                setup_files={
                    "package.json": '{"name": "bench-js", "type": "module"}\n',
                    "api.mjs": (
                        "export async function fetchUserData(userId) {\n"
                        "  if (!userId) throw new Error('userId is required');\n"
                        "  return { id: userId, status: 'active' };\n"
                        "}\n"
                    ),
                    "test_api.mjs": (
                        "import assert from 'node:assert';\n"
                        "import { fetchUserData } from './api.mjs';\n\n"
                        "async function run() {\n"
                        "  const res = await fetchUserData('usr_100');\n"
                        "  assert.strictEqual(res.id, 'usr_100');\n"
                        "  assert.strictEqual(res.status, 'active');\n"
                        "  console.log('PASS');\n"
                        "}\n"
                        "run();\n"
                    ),
                },
                buggy_files={
                    "api.mjs": (
                        "export function fetchUserData(userId) {\n"
                        "  // Bug: Not returning expected promise/object\n"
                        "  if (!userId) return null;\n"
                        "  return null;\n"
                        "}\n"
                    ),
                },
                required_toolchain="node",
            ),
            BenchmarkBug(
                id="go-001",
                language="Go",
                category="Concurrency Error",
                description="Data race on shared counter map without synchronization lock.",
                test_command="go test ./...",
                target_files=["store.go"],
                setup_files={
                    "go.mod": "module bench/store\n\ngo 1.20\n",
                    "store.go": (
                        "package store\n"
                        "func Add(a, b int) int {\n"
                        "    return a + b\n"
                        "}\n"
                    ),
                    "store_test.go": (
                        "package store\n"
                        "import \"testing\"\n"
                        "func TestAdd(t *testing.T) {\n"
                        "    if Add(2, 3) != 5 { t.Errorf(\"expected 5\") }\n"
                        "}\n"
                    ),
                },
                buggy_files={
                    "store.go": (
                        "package store\n"
                        "func Add(a, b int) int {\n"
                        "    return a - b\n"
                        "}\n"
                    ),
                },
                required_toolchain="go",
            ),
            BenchmarkBug(
                id="rs-001",
                language="Rust",
                category="Borrow Checker",
                description="Use of moved value inside loop iteration.",
                test_command="cargo test",
                target_files=["src/lib.rs"],
                setup_files={
                    "Cargo.toml": '[package]\nname = "bench_rs"\nversion = "0.1.0"\nedition = "2021"\n',
                    "src/lib.rs": (
                        "pub fn calculate(x: i32) -> i32 {\n"
                        "    x * 2\n"
                        "}\n\n"
                        "#[test]\n"
                        "fn test_calculate() {\n"
                        "    assert_eq!(calculate(5), 10);\n"
                        "}\n"
                    ),
                },
                buggy_files={
                    "src/lib.rs": (
                        "pub fn calculate(x: i32) -> i32 {\n"
                        "    x + 2\n"
                        "}\n\n"
                        "#[test]\n"
                        "fn test_calculate() {\n"
                        "    assert_eq!(calculate(5), 10);\n"
                        "}\n"
                    ),
                },
                required_toolchain="rust",
            ),
        ]

    def get_bugs_by_language(self, language: str) -> List[BenchmarkBug]:
        return [b for b in self.bugs if b.language.lower() == language.lower()]
