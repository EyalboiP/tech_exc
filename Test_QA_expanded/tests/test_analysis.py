import math
import statistics

import pytest

from Ammeters.registry import AMMETER_REGISTRY
from src.testing.analysis import analyze_samples, compute_statistics, conformance
from src.testing.comparison import compare_ammeters
from src.testing.sampler import Sample, resolve_sampling


def make_samples(values):
    return [Sample(i, 1000.0 + i, i * 0.1, v, 5.0, None if v is not None else "AmmeterConnectionError: x")
            for i, v in enumerate(values)]


def test_known_statistics():
    st = compute_statistics([1.0, 2.0, 3.0, 4.0, 10.0])
    assert st["mean"] == pytest.approx(4.0)
    assert st["median"] == 3.0
    assert st["std"] == pytest.approx(statistics.stdev([1, 2, 3, 4, 10]))  # sample std (n-1)
    assert (st["min"], st["max"], st["range"]) == (1.0, 10.0, 9.0)
    assert st["cv"] == pytest.approx(st["std"] / 4.0)
    assert st["outliers"] == 1  # 10 is beyond Q3 + 1.5*IQR


def test_edge_cases_do_not_crash():
    one = compute_statistics([5.0])
    assert one["mean"] == 5.0 and one["std"] is None and one["cv"] is None
    empty = compute_statistics([])
    assert all(v is None for v in empty.values())
    same = compute_statistics([2.0, 2.0, 2.0])
    assert same["std"] == 0 and same["cv"] == 0 and same["outliers"] == 0
    zero_mean = compute_statistics([-1.0, 1.0])
    assert zero_mean["mean"] == 0 and zero_mean["cv"] is None


def test_analyze_counts_failures_and_timing():
    plan = resolve_sampling(5, None, 10)
    st = analyze_samples(make_samples([1.0, None, 3.0, None, 5.0]), plan)
    assert (st["count_ok"], st["count_failed"], st["count_attempted"]) == (3, 2, 5)
    assert st["error_rate"] == pytest.approx(0.4)
    assert st["error_types"] == {"AmmeterConnectionError": 2}
    assert st["mean"] == pytest.approx(3.0)
    assert st["achieved_frequency_hz"] == pytest.approx(10.0)
    assert st["mean_latency_ms"] == pytest.approx(5.0)


def test_analyze_all_failed():
    st = analyze_samples(make_samples([None, None]), resolve_sampling(2, None, 10))
    assert st["count_ok"] == 0 and st["mean"] is None and st["error_rate"] == 1.0


def test_conformance_z_score():
    ok = conformance(10.5, 100, (10.0, 5.0), 4.0)   # z = 0.5 / 0.5 = 1
    assert ok["z_score"] == pytest.approx(1.0) and ok["conforms"] is True
    bad = conformance(20.0, 100, (10.0, 5.0), 4.0)
    assert bad["conforms"] is False
    assert conformance(1.0, 10, None, 4.0)["conforms"] is None


def test_theoretical_statistics_match_a_large_simulation():
    """The analytic expected mean/std of each emulator agree with brute-force sampling."""
    for name, cls in AMMETER_REGISTRY.items():
        exp_mean, exp_std = cls.expected_statistics()
        emulator = cls(port=1)
        values = [emulator.measure_current() for _ in range(40000)]
        assert statistics.fmean(values) == pytest.approx(exp_mean, rel=0.06), name
        assert statistics.stdev(values) == pytest.approx(exp_std, rel=0.15), name  # heavy tail for greenlee
    assert math.isclose(AMMETER_REGISTRY["entes"].expected_statistics()[0], 0.055 * 1250)


def test_comparison_ranking_prefers_availability_then_conformance_then_cv():
    stats = {
        "a": {"error_rate": 0.0, "cv": 0.9, "conforms": True},
        "b": {"error_rate": 0.0, "cv": 0.3, "conforms": True},
        "c": {"error_rate": 0.5, "cv": 0.01, "conforms": True},   # precise but unavailable
        "d": {"error_rate": 0.0, "cv": 0.1, "conforms": False},   # precise but off-expectation
    }
    result = compare_ammeters(stats)
    assert [r["ammeter"] for r in result["ranking"]] == ["b", "a", "d", "c"]
    assert result["most_reliable"] == "b"
    # relative precision = CV / best CV among ammeters that returned data (c: 0.01), so b = 0.3/0.01
    assert result["ranking"][0]["relative_precision"] == pytest.approx(30.0)


def test_comparison_with_no_usable_ammeter():
    result = compare_ammeters({"a": {"error_rate": 1.0, "cv": None, "conforms": None}})
    assert result["most_reliable"] is None
