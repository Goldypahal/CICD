import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..agents.orchestrator import GitFixOrchestrator
from ..config import Config
from .dataset import BenchmarkBug, BenchmarkDataset


@dataclass
class BenchmarkMetrics:
    total_bugs: int
    repaired_bugs: int
    first_attempt_successes: int
    repair_success_rate: float
    first_attempt_success_rate: float
    avg_retries: float
    avg_repair_time_sec: float
    language_breakdown: Dict[str, Dict[str, float]]


class BenchmarkRunner:
    """Evaluates GitFix autonomous maintenance agent against standardized benchmark suites."""

    def __init__(self, repo_dir: Path, dataset: Optional[BenchmarkDataset] = None):
        self.repo_dir = Path(repo_dir).resolve()
        self.dataset = dataset or BenchmarkDataset()

    def run_benchmark(self) -> BenchmarkMetrics:
        print("\n" + "=" * 60)
        print("📊 STARTING GITFIX AUTONOMOUS AGENT BENCHMARK EVALUATION")
        print("=" * 60)

        total_bugs = len(self.dataset.bugs)
        repaired_count = 0
        first_attempt_count = 0
        total_retries = 0
        total_time = 0.0

        lang_stats: Dict[str, Dict[str, int]] = {}

        for bug in self.dataset.bugs:
            print(f"\n[BenchmarkRunner] Evaluating Bug [{bug.id}] | Language: {bug.language} | Category: {bug.category}")
            start_time = time.time()
            
            # Simulate or run repair flow
            config = Config(str(self.repo_dir))
            orchestrator = GitFixOrchestrator(repo_dir=self.repo_dir, config=config, use_sandbox=False)
            result = orchestrator.run_repair_flow(auto_commit=False, auto_pr=False)
            
            duration = time.time() - start_time
            total_time += duration

            lang = bug.language
            if lang not in lang_stats:
                lang_stats[lang] = {"total": 0, "repaired": 0}
            lang_stats[lang]["total"] += 1

            if result.success:
                repaired_count += 1
                lang_stats[lang]["repaired"] += 1
                if result.retries_used == 1:
                    first_attempt_count += 1
                total_retries += result.retries_used

        repair_rate = (repaired_count / total_bugs) * 100 if total_bugs > 0 else 0.0
        first_attempt_rate = (first_attempt_count / total_bugs) * 100 if total_bugs > 0 else 0.0
        avg_retries = total_retries / repaired_count if repaired_count > 0 else 0.0
        avg_time = total_time / total_bugs if total_bugs > 0 else 0.0

        breakdown: Dict[str, Dict[str, float]] = {}
        for l_name, l_data in lang_stats.items():
            tot = l_data["total"]
            rep = l_data["repaired"]
            breakdown[l_name] = {
                "total": float(tot),
                "repaired": float(rep),
                "success_rate": (rep / tot) * 100 if tot > 0 else 0.0,
            }

        metrics = BenchmarkMetrics(
            total_bugs=total_bugs,
            repaired_bugs=repaired_count,
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
        print(f"Total Benchmark Bugs Evaluated: {m.total_bugs}")
        print(f"Successfully Repaired:        {m.repaired_bugs}")
        print(f"Repair Success Rate:          {m.repair_success_rate:.1f}%")
        print(f"First-Attempt Success Rate:   {m.first_attempt_success_rate:.1f}%")
        print(f"Average Retries per Repair:   {m.avg_retries:.2f}")
        print(f"Average Repair Time:          {m.avg_repair_time_sec:.2f}s")
        print("-" * 60)
        print("Language Performance Breakdown:")
        for lang, stats in m.language_breakdown.items():
            print(f"  - {lang:12s}: {int(stats['repaired'])}/{int(stats['total'])} ({stats['success_rate']:.1f}%)")
        print("=" * 60 + "\n")
