"""Cross-ammeter comparison: which measurement method is the most reliable?

Why not "closest to the true value"?
The emulators draw independent random values from different physical models, so no
shared ground truth exists. Reliability is therefore judged on three things that CAN
be measured for every ammeter:

1. Availability  – share of measurements that succeeded (1 - error_rate).
2. Conformance   – is the observed mean statistically compatible with the mean
                   expected from the emulator's documented ranges (z-score)?
3. Precision     – the coefficient of variation (std/mean): unit-free, so ammeters
                   with very different current ranges can be compared fairly.

Ranking: higher availability first, then conforming before non-conforming, then lower CV.
"""
from typing import Dict, List


def compare_ammeters(stats_by_name: Dict[str, Dict]) -> Dict:
    rows: List[Dict] = []
    for name, st in stats_by_name.items():
        error_rate = st.get("error_rate")
        rows.append({
            "ammeter": name,
            "availability": (1 - error_rate) if error_rate is not None else 0.0,
            "mean": st.get("mean"),
            "cv": st.get("cv"),
            "consistency": st.get("consistency"),
            "z_score": st.get("z_score"),
            "conforms": st.get("conforms"),
            "mean_latency_ms": st.get("mean_latency_ms"),
        })

    def sort_key(row: Dict):
        cv = row["cv"] if row["cv"] is not None else float("inf")
        conforms_rank = 0 if row["conforms"] in (True, None) else 1
        return (-round(row["availability"], 6), conforms_rank, cv)

    rows.sort(key=sort_key)
    usable = [r for r in rows if r["availability"] > 0 and r["cv"] is not None]
    best_cv = min((r["cv"] for r in usable), default=None)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
        row["relative_precision"] = (row["cv"] / best_cv) if (best_cv and row["cv"] is not None) else None

    return {
        "method": "rank by availability, then conformance to expected mean, then coefficient of variation",
        "ranking": rows,
        "most_reliable": rows[0]["ammeter"] if usable else None,
    }
