from pathlib import Path
from gitfix.benchmark.dataset import BenchmarkDataset


def test_benchmark_dataset_loading():
    dataset = BenchmarkDataset()
    assert len(dataset.bugs) > 0
    py_bugs = dataset.get_bugs_by_language("Python")
    assert len(py_bugs) > 0
    assert py_bugs[0].language == "Python"
