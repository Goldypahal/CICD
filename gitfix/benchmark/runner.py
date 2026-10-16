import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..agents.orchestrator import GitFixOrchestrator
from ..config import Config
from ..llm.provider import BaseLLMProvider
from .dataset import BenchmarkBug, BenchmarkDataset


@dataclass
class BenchmarkMetrics:
    total_bugs: int
    evaluated_bugs: int
    repaired_bugs: int
    failed_bugs: int
    skipped_bugs: int
    first_attempt_successes: int
    repair_success_rate: float
    first_attempt_success_rate: float
    avg_retries: float
    avg_repair_time_sec: float
    language_breakdown: Dict[str, Dict[str, float]]


class BenchmarkRunner:
    """Evaluates GitFix autonomous maintenance agent against standardized, isolated benchmark suites."""

    def __init__(
        self,
        repo_dir: Optional[Path] = None,
        dataset: Optional[BenchmarkDataset] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
    ):
        self.repo_dir = Path(repo_dir or Path.cwd()).resolve()
        self.dataset = dataset or BenchmarkDataset()
        self.llm_provider = llm_provider

    def _is_toolchain_available(self, toolchain: str) -> bool:
        cmd_map = {
            "python": ["python", "--version"],
            "node": ["node", "--version"],
            "go": ["go", "version"],
            "rust": ["cargo", "--version"],
        }
        cmd = cmd_map.get(toolchain.lower(), [toolchain, "--version"])
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return res.returncode == 0
        except Exception:
            return False

    def run_benchmark(self) -> BenchmarkMetrics:
        print("\n" + "=" * 60)
        print("📊 STARTING GITFIX AUTONOMOUS AGENT BENCHMARK EVALUATION")
        print("=" * 60)

        total_bugs = len(self.dataset.bugs)
        repaired_count = 0
        failed_count = 0
        skipped_count = 0
        first_attempt_count = 0
        total_retries = 0
        total_time = 0.0

        lang_stats: Dict[str, Dict[str, int]] = {}

        for bug in self.dataset.bugs:
            print(f"\n[BenchmarkRunner] Evaluating Bug [{bug.id}] | Language: {bug.language} | Category: {bug.category}")
            lang = bug.language
            if lang not in lang_stats:
                lang_stats[lang] = {"total": 0, "repaired": 0, "failed": 0, "skipped": 0}
            lang_stats[lang]["total"] += 1

            # Check required toolchain availability
            if not self._is_toolchain_available(bug.required_toolchain):
                print(f"[BenchmarkRunner] ⏭️ Skipping [{bug.id}] - '{bug.required_toolchain}' runtime toolchain is not available in environment.")
                skipped_count += 1
                lang_stats[lang]["skipped"] += 1
                continue

            start_time = time.time()

            # Execute bug repair in an isolated temporary Git repository fixture
            with tempfile.TemporaryDirectory() as tmpdir:
                fixture_root = Path(tmpdir).resolve()

                # 1. Initialize clean git repository
                subprocess.run(["git", "init"], cwd=fixture_root, capture_output=True)
                subprocess.run(["git", "config", "user.name", "BenchmarkRunner"], cwd=fixture_root, capture_output=True)
                subprocess.run(["git", "config", "user.email", "benchmark@gitfix.ai"], cwd=fixture_root, capture_output=True)

                # 2. Write setup files and commit baseline passing state
                for rel_path, content in bug.setup_files.items():
                    fpath = fixture_root / rel_path
                    fpath.parent.mkdir(parents=True, exist_ok=True)
                    fpath.write_text(content, encoding="utf-8")

                subprocess.run(["git", "add", "."], cwd=fixture_root, capture_output=True)
                subprocess.run(["git", "commit", "-m", "chore: baseline initial passing state"], cwd=fixture_root, capture_output=True)

                # 3. Write buggy files and commit introduced regression
                for rel_path, content in bug.buggy_files.items():
                    fpath = fixture_root / rel_path
                    fpath.parent.mkdir(parents=True, exist_ok=True)
                    fpath.write_text(content, encoding="utf-8")

                subprocess.run(["git", "add", "."], cwd=fixture_root, capture_output=True)
                subprocess.run(["git", "commit", "-m", f"feat: introduce regression for benchmark bug {bug.id}"], cwd=fixture_root, capture_output=True)

                # 4. Configure orchestrator in the isolated fixture workspace
                config = Config(str(fixture_root))
                config._data["validation"]["test_command"] = bug.test_command
                config._data["git"]["auto_commit"] = True

                orchestrator = GitFixOrchestrator(
                    repo_dir=fixture_root,
                    config=config,
                    llm_provider=self.llm_provider,
                    use_sandbox=False,
                )

                result = orchestrator.run_repair_flow(auto_commit=True, auto_pr=False)

            duration = time.time() - start_time
            total_time += duration

            if result.success:
                repaired_count += 1
                lang_stats[lang]["repaired"] += 1
                if result.retries_used == 1:
                    first_attempt_count += 1
                total_retries += result.retries_used
                print(f"[BenchmarkRunner] ✅ [{bug.id}] Repaired successfully in {duration:.2f}s ({result.retries_used} retries).")
            else:
                failed_count += 1
                lang_stats[lang]["failed"] += 1
                print(f"[BenchmarkRunner] ❌ [{bug.id}] Repair failed after {result.retries_used} attempts ({duration:.2f}s).")

        evaluated_count = repaired_count + failed_count
        repair_rate = (repaired_count / evaluated_count) * 100 if evaluated_count > 0 else 0.0
        first_attempt_rate = (first_attempt_count / evaluated_count) * 100 if evaluated_count > 0 else 0.0
        avg_retries = total_retries / repaired_count if repaired_count > 0 else 0.0
        avg_time = total_time / evaluated_count if evaluated_count > 0 else 0.0

        breakdown: Dict[str, Dict[str, float]] = {}
        for l_name, l_data in lang_stats.items():
            tot = l_data["total"]
            rep = l_data["repaired"]
            ev = l_data["repaired"] + l_data["failed"]
            breakdown[l_name] = {
                "total": float(tot),
                "evaluated": float(ev),
                "repaired": float(rep),
                "skipped": float(l_data["skipped"]),
                "success_rate": (rep / ev) * 100 if ev > 0 else 0.0,
            }

        metrics = BenchmarkMetrics(
            total_bugs=total_bugs,
            evaluated_bugs=evaluated_count,
            repaired_bugs=repaired_count,
            failed_bugs=failed_count,
            skipped_bugs=skipped_count,
            first_attempt_successes=first_attempt_count,
            repair_success_rate=repair_rate,
            first_attempt_success_rate=first_attempt_rate,
            avg_retries=avg_retries,
            avg_repair_time_sec=avg_time,
            language_breakdown=breakdown,
        )

        self._print_report(metrics)
        return metrics

    def _print_report(self, m: BenchmarkMetrics) -> None:
        print("\n" + "=" * 60)
        print("🏆 GITFIX BENCHMARK EVALUATION SUMMARY REPORT")
        print("=" * 60)
        print(f"Total Benchmark Suite Bugs:   {m.total_bugs}")
        print(f"Total Evaluated in Sandbox:   {m.evaluated_bugs}")
        print(f"Successfully Repaired:        {m.repaired_bugs}")
        print(f"Failed Repairs:               {m.failed_bugs}")
        print(f"Skipped (Toolchain missing):  {m.skipped_bugs}")
        print(f"Repair Success Rate:          {m.repair_success_rate:.1f}%")
        print(f"First-Attempt Success Rate:   {m.first_attempt_success_rate:.1f}%")
        print(f"Average Retries per Repair:   {m.avg_retries:.2f}")
        print(f"Average Repair Time:          {m.avg_repair_time_sec:.2f}s")
        print("-" * 60)
        print("Language Performance Breakdown:")
        for lang, stats in m.language_breakdown.items():
            ev = int(stats['evaluated'])
            rep = int(stats['repaired'])
            sk = int(stats['skipped'])
            if ev > 0:
                print(f"  - {lang:12s}: {rep}/{ev} repaired ({stats['success_rate']:.1f}%) [skipped: {sk}]")
            else:
                print(f"  - {lang:12s}: 0 evaluated (toolchain unavailable) [skipped: {sk}]")
        print("=" * 60 + "\n")
