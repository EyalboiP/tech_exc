"""Plots for a test run. matplotlib is optional: without it, plotting is skipped with a warning."""
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def generate_plots(result: Dict, samples: Dict[str, List[Dict]], out_dir: Path,
                   plot_types: List[str]) -> List[Path]:
    """Write PNG files into out_dir and return their paths ([] if matplotlib is unavailable)."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless: no display needed
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib is not installed - plots skipped (pip install matplotlib)")
        return []

    out_dir.mkdir(parents=True, exist_ok=True)
    values = {n: [r["value"] for r in rows if r["value"] is not None] for n, rows in samples.items()}
    values = {n: v for n, v in values.items() if v}
    written: List[Path] = []

    def save(fig, filename: str) -> None:
        path = out_dir / filename
        fig.tight_layout()
        fig.savefig(path, dpi=110)
        plt.close(fig)
        written.append(path)

    if "time_series" in plot_types:
        for name, rows in samples.items():
            ok = [r for r in rows if r["value"] is not None]
            failed = [r for r in rows if r["value"] is None]
            if not ok:
                continue
            fig, ax = plt.subplots(figsize=(8, 3.6))
            ax.plot([r["offset_s"] for r in ok], [r["value"] for r in ok], marker="o", ms=3, lw=1, label="measurement")
            if failed:
                ymin = min(r["value"] for r in ok)
                ax.scatter([r["offset_s"] for r in failed], [ymin] * len(failed), marker="x", color="red",
                           label=f"failed ({len(failed)})")
            mean = result["ammeters"][name]["stats"].get("mean")
            if mean is not None:
                ax.axhline(mean, ls="--", color="gray", label=f"mean {mean:.4g} A")
            ax.set(title=f"{name}: current over time", xlabel="time since start (s)", ylabel="current (A)")
            ax.legend(loc="best", fontsize=8)
            ax.grid(alpha=0.3)
            save(fig, f"{name}_time_series.png")

    if "histogram" in plot_types:
        for name, vals in values.items():
            fig, ax = plt.subplots(figsize=(6, 3.6))
            ax.hist(vals, bins=min(20, max(5, len(vals) // 2)), edgecolor="white")
            ax.set(title=f"{name}: distribution", xlabel="current (A)", ylabel="count")
            ax.grid(alpha=0.3)
            save(fig, f"{name}_histogram.png")

    if "boxplot" in plot_types and values:
        # Normalised by each ammeter's mean so ammeters with very different ranges share one axis.
        names = list(values)
        normalised = [[v / (sum(vals) / len(vals)) for v in vals] for vals in values.values()]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.boxplot(normalised)
        ax.set_xticklabels(names)  # works across matplotlib versions (labels= was renamed tick_labels=)
        ax.axhline(1.0, ls="--", color="gray")
        ax.set(title="Relative spread (value / mean)", ylabel="value / mean")
        ax.grid(alpha=0.3)
        save(fig, "comparison_boxplot.png")

    return written
