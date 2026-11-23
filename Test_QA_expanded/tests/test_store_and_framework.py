import json
import sqlite3
import statistics

import pytest

import run_tests
from src.testing.results_store import ResultStore, RunNotFoundError
from src.testing.test_framework import AmmeterTestFramework
from src.utils.config import ConfigError


@pytest.fixture
def framework(make_config, write_config):
    def _make(**sections):
        return AmmeterTestFramework(write_config(make_config(**sections)))
    return _make


def test_full_run_archives_everything(framework):
    fw = framework()
    result = fw.run()
    assert result["status"] == "completed"
    assert set(result["ammeters"]) == {"greenlee", "entes", "circutor"}
    run_dir = fw.store.run_dir(result["run_id"])
    for filename in ("result.json", "samples.csv", "report.html"):
        assert (run_dir / filename).is_file()
    assert (fw.store.results_dir / "results.db").is_file()
    assert list((fw.store.results_dir / "logs").glob("*.log"))

    for name, info in result["ammeters"].items():
        assert info["stats"]["count_ok"] == 10
        values = [s["value"] for s in result["samples"][name]]
        assert info["stats"]["mean"] == pytest.approx(statistics.fmean(values))
        assert info["stats"]["std"] == pytest.approx(statistics.stdev(values))

    # raw samples are archived in both CSV and SQLite
    loaded = fw.store.load_run(result["run_id"], with_samples=True)
    assert len(loaded["samples"]["entes"]) == 10
    conn = sqlite3.connect(fw.store.db_path)
    assert conn.execute("SELECT COUNT(*) FROM samples WHERE run_id=?", (result["run_id"],)).fetchone()[0] == 30
    conn.close()


def test_run_ids_are_unique_and_runs_can_be_listed_and_compared(framework):
    fw = framework()
    a, b = fw.run(["entes"]), fw.run(["entes", "circutor"])
    assert a["run_id"] != b["run_id"]
    assert [r["run_id"] for r in fw.store.list_runs()] == sorted([a["run_id"], b["run_id"]])
    comparison = fw.store.compare_runs(a["run_id"], b["run_id"])
    assert set(comparison["ammeters"]) == {"entes"}
    assert comparison["only_in_b"] == ["circutor"]
    assert "delta_pct" in comparison["ammeters"]["entes"]["mean"]


def test_run_test_single_ammeter(framework):
    fw = framework(testing={"start_emulators": True})
    from src.testing.emulators import EmulatorManager
    with EmulatorManager(fw.config, ["greenlee"]):
        out = fw.run_test("greenlee")
    assert out["stats"]["count_ok"] == 10 and len(out["samples"]) == 10
    with pytest.raises(ConfigError):
        fw.run_test("unknown")


def test_unreachable_devices_are_reported_not_fatal(framework):
    fw = framework(testing={"start_emulators": False, "timeout_seconds": 0.2})
    result = fw.run()
    assert result["status"] == "completed_with_errors"
    assert all(i["stats"]["error_rate"] == 1.0 for i in result["ammeters"].values())
    assert result["comparison"]["most_reliable"] is None


def test_faulty_run_counts_errors(framework):
    fw = framework(fault_simulation={"enabled": True, "drop_rate": 0.4, "seed": 5},
                   testing={"sampling": {"measurements_count": 40, "sampling_frequency_hz": 200}})
    result = fw.run(["entes"])
    st = result["ammeters"]["entes"]["stats"]
    assert result["status"] == "completed_with_errors"
    assert 0 < st["count_failed"] < 40 and st["count_ok"] + st["count_failed"] == 40


def test_bad_sampling_config_fails_fast(framework):
    fw = framework(testing={"sampling": {"measurements_count": 10, "sampling_frequency_hz": None}})
    with pytest.raises(ConfigError, match="at least two"):
        fw.run()


def test_corrupt_run_does_not_break_listing(framework):
    fw = framework()
    good = fw.run(["entes"])
    bad_dir = fw.store.runs_dir / "20000101_000000_bad000"
    bad_dir.mkdir()
    (bad_dir / "result.json").write_text("{not json")
    assert [r["run_id"] for r in fw.store.list_runs() if r["run_id"] == good["run_id"]] == [good["run_id"]]
    with pytest.raises(RunNotFoundError):
        fw.store.load_run("does-not-exist")


def test_store_falls_back_to_sqlite_when_json_is_missing(framework):
    fw = framework()
    run = fw.run(["circutor"])
    (fw.store.run_dir(run["run_id"]) / "result.json").unlink()
    (fw.store.run_dir(run["run_id"]) / "samples.csv").unlink()
    loaded = fw.store.load_run(run["run_id"], with_samples=True)
    assert len(loaded["samples"]["circutor"]) == 10


def test_json_only_storage(make_config, write_config):
    cfg = make_config(result_management={"save_sqlite": False, "save_csv": False})
    fw = AmmeterTestFramework(write_config(cfg))
    run = fw.run(["entes"])
    assert not fw.store.db_path.exists()
    assert not (fw.store.run_dir(run["run_id"]) / "samples.csv").exists()
    assert json.loads((fw.store.run_dir(run["run_id"]) / "result.json").read_text())["run_id"] == run["run_id"]


def test_plots_are_generated_when_enabled(framework):
    pytest.importorskip("matplotlib")
    fw = framework(analysis={"visualization": {"enabled": True}})
    run = fw.run()
    pngs = {p.name for p in fw.store.run_dir(run["run_id"]).glob("*.png")}
    assert {"entes_time_series.png", "entes_histogram.png", "comparison_boxplot.png"} <= pngs


def test_cli_end_to_end(make_config, write_config, capsys):
    path = write_config(make_config())
    code = run_tests.main(["--config", path, "--ammeters", "entes", "--duration", "0.1", "--frequency", "50"])
    out = capsys.readouterr().out
    assert code == 0 and "Most reliable: entes" in out
    assert run_tests.main(["--config", path, "--list-runs"]) == 0
    assert run_tests.main(["--config", path, "--count", "5", "--frequency", "0"]) == 2
    assert run_tests.main(["--config", path, "--show", "nope"]) == 2


def test_cli_duration_and_frequency_replace_file_count(make_config, write_config):
    args = run_tests.build_parser().parse_args(["--duration", "10", "--frequency", "4"])
    overrides = run_tests.overrides_from_args(args)
    assert overrides["testing.sampling.measurements_count"] is None
