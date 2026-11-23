"""Statistical analysis of the samples collected from one ammeter."""
import math
import statistics
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

from src.testing.sampler import Sample, SamplingPlan

# Coefficient-of-variation thresholds for the human-readable consistency label.
CV_STABLE = 0.25
CV_MODERATE = 0.75


def consistency_label(cv: Optional[float]) -> Optional[str]:
    if cv is None:
        return None
    if cv < CV_STABLE:
        return "stable"
    if cv < CV_MODERATE:
        return "moderate"
    return "variable"


def compute_statistics(values: Sequence[float]) -> Dict[str, Optional[float]]:
    """Descriptive statistics. Anything undefined for the data (e.g. std of 1 value) is None."""
    n = len(values)
    if n == 0:
        return {k: None for k in ("mean", "median", "std", "variance", "min", "max", "range",
                                  "cv", "q1", "q3", "iqr", "p95", "outliers")}
    mean = statistics.fmean(values)
    std = statistics.stdev(values) if n > 1 else None  # sample standard deviation (n-1)
    result: Dict[str, Optional[float]] = {
        "mean": mean,
        "median": statistics.median(values),
        "std": std,
        "variance": std * std if std is not None else None,
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "cv": (std / abs(mean)) if (std is not None and mean != 0) else None,
        "q1": None, "q3": None, "iqr": None, "p95": None, "outliers": None,
    }
    if n > 1:
        quartiles = statistics.quantiles(values, n=4, method="inclusive")
        q1, q3 = quartiles[0], quartiles[2]
        iqr = q3 - q1
        result.update(
            q1=q1, q3=q3, iqr=iqr,
            p95=statistics.quantiles(values, n=100, method="inclusive")[94],
            outliers=sum(1 for v in values if v < q1 - 1.5 * iqr or v > q3 + 1.5 * iqr),
        )
    return result


def _timing_statistics(samples: List[Sample]) -> Dict[str, Optional[float]]:
    latencies = [s.latency_ms for s in samples]
    offsets = [s.offset_s for s in samples]
    intervals = [b - a for a, b in zip(offsets, offsets[1:])]
    achieved = None
    if len(offsets) > 1 and offsets[-1] > offsets[0]:
        achieved = (len(offsets) - 1) / (offsets[-1] - offsets[0])
    return {
        "duration_s": (offsets[-1] - offsets[0]) if offsets else None,
        "achieved_frequency_hz": achieved,
        "interval_jitter_ms": statistics.stdev(intervals) * 1000.0 if len(intervals) > 1 else None,
        "mean_latency_ms": statistics.fmean(latencies) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
    }


def conformance(mean: Optional[float], n_ok: int, expected: Optional[Tuple[float, float]],
                z_threshold: float) -> Dict[str, Optional[float]]:
    """
    Compare the observed mean with the theoretical mean using a z-score:
        z = (mean - expected_mean) / (expected_std / sqrt(n))
    """
    if expected is None:
        return {"expected_mean": None, "expected_std": None, "z_score": None, "conforms": None}
    exp_mean, exp_std = expected
    z = None
    conforms = None
    if mean is not None and n_ok > 0 and exp_std > 0:
        z = (mean - exp_mean) / (exp_std / math.sqrt(n_ok))
        conforms = abs(z) <= z_threshold
    return {"expected_mean": exp_mean, "expected_std": exp_std, "z_score": z, "conforms": conforms}


def analyze_samples(samples: List[Sample], plan: Optional[SamplingPlan] = None,
                    expected: Optional[Tuple[float, float]] = None,
                    z_threshold: float = 4.0) -> Dict:
    """Full per-ammeter analysis: measurement stats, availability, timing and conformance."""
    values = [s.value for s in samples if s.value is not None]
    failed = [s for s in samples if s.value is None]
    n_attempted = len(samples)
    stats: Dict = {
        "count_requested": plan.count if plan else n_attempted,
        "count_attempted": n_attempted,
        "count_ok": len(values),
        "count_failed": len(failed),
        "error_rate": (len(failed) / n_attempted) if n_attempted else None,
        "error_types": dict(Counter((s.error or "").split(":")[0] for s in failed)),
        "requested_frequency_hz": plan.frequency_hz if plan else None,
    }
    stats.update(compute_statistics(values))
    stats["consistency"] = consistency_label(stats["cv"])
    stats.update(_timing_statistics(samples))
    stats.update(conformance(stats["mean"], len(values), expected, z_threshold))
    return stats
