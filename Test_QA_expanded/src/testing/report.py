"""Console summary and standalone HTML report for a run (stdlib only)."""
import html
from pathlib import Path
from typing import Dict, List, Optional


def _fmt(value, digits: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    return str(value)


def format_console_summary(result: Dict, metrics: Optional[List[str]] = None) -> str:
    metrics = metrics or ["mean", "median", "std", "min", "max"]
    plan = result["metadata"]["sampling"]
    lines = [
        "",
        f"Run {result['run_id']}  [{result['status']}]",
        f"Sampling: {plan['count']} measurements @ {plan['frequency_hz']:g} Hz (~{plan['duration_s']:g}s)",
        "",
    ]
    header = ["ammeter", "ok/total", "err%"] + metrics + ["cv", "consistency", "z", "conforms"]
    rows = [header]
    for name, info in result["ammeters"].items():
        st = info["stats"]
        rows.append([name, f"{st['count_ok']}/{st['count_attempted']}", _fmt((st["error_rate"] or 0) * 100, 3)]
                    + [_fmt(st.get(m)) for m in metrics]
                    + [_fmt(st.get("cv")), _fmt(st.get("consistency")), _fmt(st.get("z_score"), 3),
                       _fmt(st.get("conforms"))])
    widths = [max(len(r[i]) for r in rows) for i in range(len(header))]
    for i, row in enumerate(rows):
        lines.append("  ".join(cell.ljust(widths[j]) for j, cell in enumerate(row)))
        if i == 0:
            lines.append("  ".join("-" * w for w in widths))
    comparison = result.get("comparison") or {}
    if comparison.get("ranking"):
        lines += ["", "Reliability ranking (" + comparison["method"] + "):"]
        for r in comparison["ranking"]:
            lines.append(f"  {r['rank']}. {r['ammeter']:<9} availability={r['availability']:.0%}  "
                         f"cv={_fmt(r['cv'])}  conforms={_fmt(r['conforms'])}")
        lines.append(f"Most reliable: {comparison.get('most_reliable') or 'n/a'}")
    return "\n".join(lines)


def write_html_report(result: Dict, run_dir: Path, plots: List[Path]) -> Path:
    esc = html.escape
    st_rows = []
    for name, info in result["ammeters"].items():
        st = info["stats"]
        cells = [name, f"{st['count_ok']}/{st['count_attempted']}", _fmt((st["error_rate"] or 0) * 100, 3),
                 *(_fmt(st.get(k)) for k in ("mean", "median", "std", "min", "max", "cv")),
                 _fmt(st.get("consistency")), _fmt(st.get("achieved_frequency_hz")),
                 _fmt(st.get("mean_latency_ms")), _fmt(st.get("z_score"), 3), _fmt(st.get("conforms"))]
        st_rows.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in cells) + "</tr>")
    rank_rows = []
    for r in (result.get("comparison") or {}).get("ranking", []):
        cells = [r["rank"], r["ammeter"], f"{r['availability']:.0%}", _fmt(r["cv"]), _fmt(r["relative_precision"], 3),
                 _fmt(r["z_score"], 3), _fmt(r["conforms"])]
        rank_rows.append("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in cells) + "</tr>")
    images = "".join(f'<figure><img src="{esc(p.name)}" alt="{esc(p.stem)}"><figcaption>{esc(p.stem)}</figcaption></figure>'
                     for p in plots)
    meta = result["metadata"]
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Ammeter run {esc(result['run_id'])}</title>
<style>body{{font-family:sans-serif;margin:2rem;max-width:1100px}}table{{border-collapse:collapse;margin:1rem 0}}
td,th{{border:1px solid #bbb;padding:4px 8px;text-align:right}}th{{background:#eee}}td:first-child,th:first-child{{text-align:left}}
figure{{display:inline-block;margin:.5rem}}img{{max-width:520px}}</style></head><body>
<h1>Ammeter test run {esc(result['run_id'])}</h1>
<p>Status: <b>{esc(str(result['status']))}</b> &middot; started {esc(str(result['started_at']))} &middot;
finished {esc(str(result['finished_at']))}<br>
Sampling: {meta['sampling']['count']} measurements @ {meta['sampling']['frequency_hz']:g} Hz
&middot; host {esc(meta['host'])} &middot; Python {esc(meta['python'])}</p>
<h2>Statistics</h2><table><tr><th>ammeter</th><th>ok/total</th><th>err %</th><th>mean (A)</th><th>median</th><th>std</th>
<th>min</th><th>max</th><th>CV</th><th>consistency</th><th>achieved Hz</th><th>latency ms</th><th>z</th><th>conforms</th></tr>
{''.join(st_rows)}</table>
<h2>Reliability ranking</h2><p>{esc((result.get('comparison') or {}).get('method', ''))}</p>
<table><tr><th>rank</th><th>ammeter</th><th>availability</th><th>CV</th><th>CV vs best</th><th>z</th><th>conforms</th></tr>
{''.join(rank_rows)}</table>
<p>Most reliable: <b>{esc(str((result.get('comparison') or {}).get('most_reliable')))}</b></p>
<h2>Plots</h2>{images or '<p>No plots (disabled or matplotlib not installed).</p>'}
</body></html>"""
    path = run_dir / "report.html"
    path.write_text(page, encoding="utf-8")
    return path
