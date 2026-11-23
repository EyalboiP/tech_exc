"""Archiving of test runs: JSON + CSV per run folder, plus a SQLite index of everything.

Layout:
    <results_dir>/runs/<run_id>/result.json   run metadata + per-ammeter statistics
    <results_dir>/runs/<run_id>/samples.csv   every raw sample
    <results_dir>/results.db                  SQLite: runs, ammeter_stats, samples
"""
import csv
import json
import logging
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SAMPLE_FIELDS = ["ammeter", "index", "timestamp", "offset_s", "value", "latency_ms", "error"]


class RunNotFoundError(KeyError):
    pass


class ResultStore:
    def __init__(self, results_dir: str = "results", save_json: bool = True, save_csv: bool = True,
                 save_sqlite: bool = True):
        self.results_dir = Path(results_dir)
        self.save_json = save_json
        self.save_csv = save_csv
        self.save_sqlite = save_sqlite

    @property
    def runs_dir(self) -> Path:
        return self.results_dir / "runs"

    @property
    def db_path(self) -> Path:
        return self.results_dir / "results.db"

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    @staticmethod
    def new_run_id() -> str:
        """Sortable and unique: local timestamp + random suffix."""
        return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # ------------------------------------------------------------------ saving
    def save_run(self, result: Dict, samples: Dict[str, List[Dict]]) -> Path:
        """Persist a run. `result` must not contain raw samples (they are passed separately)."""
        run_id = result["run_id"]
        run_dir = self.run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        if self.save_json:
            with open(run_dir / "result.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
        if self.save_csv:
            with open(run_dir / "samples.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=SAMPLE_FIELDS)
                writer.writeheader()
                for name, rows in samples.items():
                    for row in rows:
                        writer.writerow({"ammeter": name, **{k: row.get(k) for k in SAMPLE_FIELDS[1:]}})
        if self.save_sqlite:
            self._save_sqlite(result, samples)
        logger.info("Run %s saved to %s", run_id, run_dir)
        return run_dir

    def _connect(self) -> sqlite3.Connection:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT,
                status TEXT, ammeters TEXT, result_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS ammeter_stats (
                run_id TEXT, ammeter TEXT, count_ok INTEGER, error_rate REAL, mean REAL,
                median REAL, std REAL, min REAL, max REAL, cv REAL, achieved_frequency_hz REAL,
                PRIMARY KEY (run_id, ammeter));
            CREATE TABLE IF NOT EXISTS samples (
                run_id TEXT, ammeter TEXT, idx INTEGER, timestamp REAL, offset_s REAL,
                value REAL, latency_ms REAL, error TEXT);
            CREATE INDEX IF NOT EXISTS idx_samples_run ON samples (run_id, ammeter);
        """)
        return conn

    def _save_sqlite(self, result: Dict, samples: Dict[str, List[Dict]]) -> None:
        run_id = result["run_id"]
        conn = self._connect()
        try:
            with conn:
                conn.execute("INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?)", (
                    run_id, result.get("started_at"), result.get("finished_at"), result.get("status"),
                    ",".join(result["ammeters"]), json.dumps(result, default=str)))
                for name, info in result["ammeters"].items():
                    st = info["stats"]
                    conn.execute("INSERT OR REPLACE INTO ammeter_stats VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                        run_id, name, st.get("count_ok"), st.get("error_rate"), st.get("mean"),
                        st.get("median"), st.get("std"), st.get("min"), st.get("max"), st.get("cv"),
                        st.get("achieved_frequency_hz")))
                conn.execute("DELETE FROM samples WHERE run_id = ?", (run_id,))
                conn.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?)", [
                    (run_id, name, r["index"], r["timestamp"], r["offset_s"], r["value"], r["latency_ms"], r["error"])
                    for name, rows in samples.items() for r in rows])
        finally:
            conn.close()

    # ----------------------------------------------------------------- reading
    def list_runs(self) -> List[Dict]:
        """Summaries of every stored run, oldest first. Unreadable runs are skipped with a warning."""
        summaries: Dict[str, Dict] = {}
        if self.runs_dir.is_dir():
            for path in sorted(self.runs_dir.glob("*/result.json")):
                try:
                    summaries[path.parent.name] = self._summary(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, ValueError, KeyError) as exc:
                    logger.warning("Skipping unreadable run %s: %s", path.parent.name, exc)
        if self.db_path.is_file():
            try:
                conn = sqlite3.connect(self.db_path)
                try:
                    for run_id, blob in conn.execute("SELECT run_id, result_json FROM runs"):
                        if run_id not in summaries:
                            summaries[run_id] = self._summary(json.loads(blob))
                finally:
                    conn.close()
            except (sqlite3.Error, ValueError, KeyError) as exc:
                logger.warning("Could not read the SQLite index: %s", exc)
        return [summaries[k] for k in sorted(summaries)]

    @staticmethod
    def _summary(result: Dict) -> Dict:
        return {
            "run_id": result["run_id"],
            "started_at": result.get("started_at"),
            "status": result.get("status"),
            "ammeters": list(result["ammeters"]),
            "most_reliable": (result.get("comparison") or {}).get("most_reliable"),
        }

    def load_run(self, run_id: str, with_samples: bool = False) -> Dict:
        """Load a stored run (JSON file first, SQLite as fallback)."""
        result: Optional[Dict] = None
        json_path = self.run_dir(run_id) / "result.json"
        if json_path.is_file():
            try:
                result = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                logger.warning("Run %s result.json is unreadable (%s); trying SQLite", run_id, exc)
        if result is None and self.db_path.is_file():
            conn = sqlite3.connect(self.db_path)
            try:
                row = conn.execute("SELECT result_json FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            finally:
                conn.close()
            if row:
                result = json.loads(row[0])
        if result is None:
            raise RunNotFoundError(f"Run '{run_id}' not found in {self.results_dir}")
        if with_samples:
            result["samples"] = self._load_samples(run_id)
        return result

    def _load_samples(self, run_id: str) -> Dict[str, List[Dict]]:
        samples: Dict[str, List[Dict]] = {}
        csv_path = self.run_dir(run_id) / "samples.csv"
        if csv_path.is_file():
            with open(csv_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    samples.setdefault(row["ammeter"], []).append({
                        "index": int(row["index"]), "timestamp": float(row["timestamp"]),
                        "offset_s": float(row["offset_s"]),
                        "value": float(row["value"]) if row["value"] not in ("", None) else None,
                        "latency_ms": float(row["latency_ms"]), "error": row["error"] or None})
        elif self.db_path.is_file():
            conn = sqlite3.connect(self.db_path)
            try:
                for name, idx, ts, off, val, lat, err in conn.execute(
                        "SELECT ammeter, idx, timestamp, offset_s, value, latency_ms, error FROM samples "
                        "WHERE run_id = ? ORDER BY ammeter, idx", (run_id,)):
                    samples.setdefault(name, []).append(
                        {"index": idx, "timestamp": ts, "offset_s": off, "value": val,
                         "latency_ms": lat, "error": err})
            finally:
                conn.close()
        return samples

    def compare_runs(self, run_a: str, run_b: str) -> Dict:
        """Per-ammeter differences between two stored runs (b relative to a)."""
        a, b = self.load_run(run_a), self.load_run(run_b)
        metrics = ("mean", "median", "std", "cv", "error_rate", "mean_latency_ms")
        comparison: Dict[str, Dict] = {}
        for name in a["ammeters"]:
            if name not in b["ammeters"]:
                continue
            sa, sb = a["ammeters"][name]["stats"], b["ammeters"][name]["stats"]
            entry = {}
            for metric in metrics:
                va, vb = sa.get(metric), sb.get(metric)
                delta = (vb - va) if (va is not None and vb is not None) else None
                pct = (delta / abs(va) * 100.0) if (delta is not None and va) else None
                entry[metric] = {"a": va, "b": vb, "delta": delta, "delta_pct": pct}
            comparison[name] = entry
        return {"run_a": run_a, "run_b": run_b, "ammeters": comparison,
                "only_in_a": sorted(set(a["ammeters"]) - set(b["ammeters"])),
                "only_in_b": sorted(set(b["ammeters"]) - set(a["ammeters"]))}
