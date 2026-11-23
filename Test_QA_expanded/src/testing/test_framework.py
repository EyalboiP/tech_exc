"""AmmeterTestFramework: config-driven orchestration of a full test run."""
import contextlib
import copy
import importlib.util
import getpass
import logging
import platform
import socket
import sys
import threading
from datetime import datetime
from typing import Dict, List, Optional

from Ammeters.registry import AMMETER_REGISTRY
from src.testing.ammeter_client import AmmeterClient
from src.testing.analysis import analyze_samples
from src.testing.comparison import compare_ammeters
from src.testing.emulators import EmulatorManager
from src.testing.report import write_html_report
from src.testing.results_store import ResultStore
from src.testing.sampler import SamplingPlan, resolve_sampling, run_sampling
from src.testing.visualization import generate_plots
from src.utils.config import ConfigError, apply_overrides, load_config, validate_config
from src.utils.logger import TestLogger

FRAMEWORK_VERSION = "1.0.0"
logger = logging.getLogger(__name__)


class AmmeterTestFramework:
    __test__ = False  # not a pytest test class, despite the name

    def __init__(self, config_path: str = "config/config.yaml", overrides: Optional[Dict] = None):
        """
        overrides: {"testing.sampling.measurements_count": 50, ...} applied on top of the file.
        """
        self.config = apply_overrides(load_config(config_path, validate=False), overrides)
        validate_config(self.config)
        rm = self.config["result_management"]
        self.store = ResultStore(rm["results_dir"], rm["save_json"], rm["save_csv"], rm["save_sqlite"])

    # ------------------------------------------------------------------ setup
    @property
    def sampling_plan(self) -> SamplingPlan:
        s = self.config["testing"]["sampling"]
        return resolve_sampling(s["measurements_count"], s["total_duration_seconds"], s["sampling_frequency_hz"])

    def selected_ammeters(self, names: Optional[List[str]] = None) -> List[str]:
        names = names or self.config["testing"]["ammeters"] or list(self.config["ammeters"])
        unknown = [n for n in names if n not in self.config["ammeters"]]
        if unknown:
            raise ConfigError(f"Unknown ammeter(s) {unknown}; configured: {list(self.config['ammeters'])}")
        return list(names)

    def _client(self, name: str) -> AmmeterClient:
        cfg, testing = self.config["ammeters"][name], self.config["testing"]
        return AmmeterClient(name, cfg["port"], cfg["command"], host=testing["host"],
                             timeout=testing["timeout_seconds"], retries=testing["retries"])

    # ------------------------------------------------------------- one ammeter
    def run_test(self, ammeter_type: str, plan: Optional[SamplingPlan] = None,
                 stop_event: Optional[threading.Event] = None) -> Dict:
        """
        Sample and analyse ONE ammeter (its emulator/device must already be reachable).
        Returns {"port", "command", "stats", "samples"}; nothing is written to disk.
        """
        if ammeter_type not in self.config["ammeters"]:
            raise ConfigError(f"Unknown ammeter '{ammeter_type}'; configured: {list(self.config['ammeters'])}")
        plan = plan or self.sampling_plan
        samples = run_sampling(self._client(ammeter_type), plan, stop_event)
        cls = AMMETER_REGISTRY.get(ammeter_type)
        expected = cls.expected_statistics() if cls else None
        stats = analyze_samples(samples, plan, expected, self.config["analysis"]["conformance_z_threshold"])
        cfg = self.config["ammeters"][ammeter_type]
        return {"port": cfg["port"], "command": cfg["command"], "stats": stats,
                "samples": [s.to_dict() for s in samples]}

    # --------------------------------------------------------------- full run
    def run(self, ammeters: Optional[List[str]] = None, stop_event: Optional[threading.Event] = None) -> Dict:
        """
        Full session: start emulators (if configured), sample every selected ammeter
        concurrently, analyse, compare, archive, plot and write the HTML report.
        Returns the result dict; raw samples are under result["samples"], the run folder
        under result["run_dir"].
        """
        names = self.selected_ammeters(ammeters)
        plan = self.sampling_plan  # fail fast on a bad sampling config
        stop_event = stop_event or threading.Event()
        run_id = self.store.new_run_id()
        test_logger = TestLogger(f"run_{run_id[-6:]}", log_dir=str(self.store.results_dir / "logs"),
                                 level=self.config["logging"]["level"], console=False)
        started = datetime.now()
        test_logger.info(f"Run {run_id} starting: ammeters={names}, plan={plan}")

        outcomes: Dict[str, Dict] = {}
        manager_cm = (EmulatorManager(self.config, names) if self.config["testing"]["start_emulators"]
                      else contextlib.nullcontext())
        try:
            with manager_cm:
                threads = [threading.Thread(target=self._worker, args=(n, plan, stop_event, outcomes),
                                            name=f"sampler-{n}", daemon=True) for n in names]
                for t in threads:
                    t.start()
                try:
                    for t in threads:
                        while t.is_alive():
                            t.join(0.2)
                except KeyboardInterrupt:
                    test_logger.warning("Interrupted by user - stopping sampling, saving partial results")
                    stop_event.set()
                    for t in threads:
                        t.join(timeout=self.config["testing"]["timeout_seconds"] + 1)
        finally:
            finished = datetime.now()

        status = "interrupted" if stop_event.is_set() else (
            "completed_with_errors"
            if any(o["stats"]["count_failed"] or o["stats"].get("fatal_error") for o in outcomes.values())
            else "completed")
        samples = {n: outcomes[n].pop("samples") for n in names if n in outcomes}
        result = {
            "run_id": run_id,
            "status": status,
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": finished.isoformat(timespec="seconds"),
            "metadata": {
                "framework_version": FRAMEWORK_VERSION,
                "host": socket.gethostname(),
                "user": getpass.getuser(),
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "sampling": {"count": plan.count, "frequency_hz": plan.frequency_hz, "duration_s": plan.duration_s},
                "emulators_started": self.config["testing"]["start_emulators"],
                "fault_simulation": copy.deepcopy(self.config["fault_simulation"]),
                "config": copy.deepcopy(self.config),
            },
            "ammeters": {n: outcomes[n] for n in names if n in outcomes},
        }
        result["comparison"] = compare_ammeters({n: o["stats"] for n, o in result["ammeters"].items()})

        run_dir = self.store.save_run(result, samples)
        viz = self.config["analysis"]["visualization"]
        plots = generate_plots(result, samples, run_dir, viz["plot_types"]) if viz["enabled"] else []
        if plots:
            result["plots"] = [p.name for p in plots]
            self.store.save_run(result, samples)  # re-save so the plot list is archived too
        if self.config["result_management"]["html_report"]:
            write_html_report(result, run_dir, plots, self._no_plots_reason(viz, plots))
        test_logger.info(f"Run {run_id} finished with status {status}; saved to {run_dir}")
        test_logger.close()

        result["samples"] = samples
        result["run_dir"] = str(run_dir)
        return result

    @staticmethod
    def _no_plots_reason(viz: Dict, plots: List) -> Optional[str]:
        if plots:
            return None
        if not viz["enabled"]:
            return "plotting is disabled (analysis.visualization.enabled is false, or --no-plots was used)."
        if importlib.util.find_spec("matplotlib") is None:
            return "matplotlib is not installed. Run: pip install -r requirements-optional.txt"
        return "no successful samples to plot."

    def _worker(self, name: str, plan: SamplingPlan, stop_event: threading.Event, outcomes: Dict[str, Dict]) -> None:
        try:
            outcomes[name] = self.run_test(name, plan, stop_event)
        except Exception as exc:  # never let one ammeter take the whole run down
            logger.exception("Test of %s crashed", name)
            cfg = self.config["ammeters"][name]
            stats = analyze_samples([], plan)
            stats["fatal_error"] = f"{type(exc).__name__}: {exc}"
            outcomes[name] = {"port": cfg["port"], "command": cfg["command"], "stats": stats, "samples": []}
