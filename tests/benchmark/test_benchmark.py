from pathlib import Path
from gitfix.benchmark.dataset import BenchmarkDataset, BenchmarkBug
from gitfix.benchmark.runner import BenchmarkRunner
from gitfix.llm.mock_provider import MockLLMProvider


def test_benchmark_dataset_loading():
    dataset = BenchmarkDataset()
    assert len(dataset.bugs) == 5
    py_bugs = dataset.get_bugs_by_language("Python")
    assert len(py_bugs) == 2
    assert py_bugs[0].language == "Python"
    assert "math_ops.py" in py_bugs[0].target_files
    assert len(py_bugs[0].setup_files) > 0
    assert len(py_bugs[0].buggy_files) > 0


def test_benchmark_runner_isolated_evaluation(tmp_path: Path):
    # Create single-bug test dataset
    bug = BenchmarkBug(
        id="test-py-01",
        language="Python",
        category="Logic",
        description="Math logic bug",
        test_command="pytest test_calc.py",
        target_files=["calc.py"],
        setup_files={
            "calc.py": "def double(x):\n    return x * 2\n",
            "test_calc.py": "from calc import double\ndef test_double():\n    assert double(5) == 10\n",
        },
        buggy_files={
            "calc.py": "def double(x):\n    return x + 2\n",
        },
        required_toolchain="python",
    )
    dataset = BenchmarkDataset()
    dataset.bugs = [bug]

    mock_llm = MockLLMProvider(
        mock_files=[{"path": "calc.py", "content": "def double(x):\n    return x * 2\n"}],
        explanation="Fixed double formula",
    )

    runner = BenchmarkRunner(repo_dir=tmp_path, dataset=dataset, llm_provider=mock_llm)
    metrics = runner.run_benchmark()

    assert metrics.total_bugs == 1
    assert metrics.evaluated_bugs == 1
    assert metrics.repaired_bugs == 1
    assert metrics.repair_success_rate == 100.0


def test_benchmark_runner_skips_unavailable_toolchain(tmp_path: Path):
    bug = BenchmarkBug(
        id="test-unknown-01",
        language="EsotericLang",
        category="Toolchain",
        description="Unavailable toolchain",
        test_command="nonexistent_cmd test",
        target_files=["main.eso"],
        setup_files={"main.eso": "pass\n"},
        buggy_files={"main.eso": "fail\n"},
        required_toolchain="nonexistent_compiler_xyz_123",
    )
    dataset = BenchmarkDataset()
    dataset.bugs = [bug]

    runner = BenchmarkRunner(repo_dir=tmp_path, dataset=dataset)
    metrics = runner.run_benchmark()

    assert metrics.total_bugs == 1
    assert metrics.evaluated_bugs == 0
    assert metrics.skipped_bugs == 1
    assert metrics.repaired_bugs == 0
