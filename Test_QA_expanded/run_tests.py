"""Command-line entry point of the ammeter testing framework.

Examples:
    python run_tests.py                                   # run with config/config.yaml
    python run_tests.py --ammeters greenlee entes --count 50 --frequency 5
    python run_tests.py --duration 10 --frequency 4       # 40 measurements
    python run_tests.py --simulate-faults --drop-rate 0.2 --garbage-rate 0.1 --seed 1
    python run_tests.py --no-emulators                    # talk to emulators already running
    python run_tests.py --list-runs
    python run_tests.py --show <run_id>
    python run_tests.py --compare <run_id_a> <run_id_b>
"""
import argparse
import json
import sys

from src.testing.report import format_console_summary
from src.testing.results_store import ResultStore, RunNotFoundError
from src.testing.test_framework import AmmeterTestFramework
from src.utils.config import ConfigError
from src.utils.logger import configure_logging


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ammeter testing framework", formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__)
    p.add_argument("--config", default="config/config.yaml", help="path to the YAML config (default: %(default)s)")
    p.add_argument("--ammeters", nargs="+", metavar="NAME", help="ammeters to test (default: from config)")
    p.add_argument("--count", type=int, help="number of measurements")
    p.add_argument("--duration", type=float, help="total duration in seconds")
    p.add_argument("--frequency", type=float, help="sampling frequency in Hz")
    p.add_argument("--no-emulators", action="store_true", help="do not start emulators; use already running ones")
    p.add_argument("--results-dir", help="where to store results (default: from config)")
    p.add_argument("--no-plots", action="store_true", help="skip plot generation")
    p.add_argument("--log-level", help="DEBUG, INFO, WARNING, ...")
    faults = p.add_argument_group("error simulation (emulators started by the framework only)")
    faults.add_argument("--simulate-faults", action="store_true", help="enable fault injection")
    faults.add_argument("--drop-rate", type=float, help="probability of dropping the connection (0-1)")
    faults.add_argument("--garbage-rate", type=float, help="probability of a garbage reply (0-1)")
    faults.add_argument("--delay-rate", type=float, help="probability of a delayed reply (0-1)")
    faults.add_argument("--delay-ms", type=float, help="delay applied to delayed replies")
    faults.add_argument("--seed", type=int, help="seed for a reproducible fault sequence")
    hist = p.add_argument_group("result history")
    hist.add_argument("--list-runs", action="store_true", help="list archived runs and exit")
    hist.add_argument("--show", metavar="RUN_ID", help="print the summary of an archived run and exit")
    hist.add_argument("--compare", nargs=2, metavar=("RUN_A", "RUN_B"), help="compare two archived runs and exit")
    return p


def overrides_from_args(args) -> dict:
    """Translate CLI flags into config overrides. Only flags actually given are included."""
    candidates = {
        "testing.sampling.measurements_count": args.count,
        "testing.sampling.total_duration_seconds": args.duration,
        "testing.sampling.sampling_frequency_hz": args.frequency,
        "result_management.results_dir": args.results_dir,
        "logging.level": args.log_level,
        "fault_simulation.drop_rate": args.drop_rate,
        "fault_simulation.garbage_rate": args.garbage_rate,
        "fault_simulation.delay_rate": args.delay_rate,
        "fault_simulation.delay_ms": args.delay_ms,
        "fault_simulation.seed": args.seed,
    }
    overrides = {k: v for k, v in candidates.items() if v is not None}
    if args.no_emulators:
        overrides["testing.start_emulators"] = False
    if args.no_plots:
        overrides["analysis.visualization.enabled"] = False
    if args.simulate_faults:
        overrides["fault_simulation.enabled"] = True
    # Two sampling flags fully define the plan, so the file's value for the third one is
    # cleared (otherwise e.g. --duration 10 --frequency 4 would clash with count: 30 from the file).
    sampling = {"measurements_count": args.count, "total_duration_seconds": args.duration,
                "sampling_frequency_hz": args.frequency}
    if sum(v is not None for v in sampling.values()) >= 2:
        for key, value in sampling.items():
            if value is None:
                overrides[f"testing.sampling.{key}"] = None
    return overrides


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        framework = AmmeterTestFramework(args.config, overrides_from_args(args))
        configure_logging(framework.config["logging"]["level"])

        if args.list_runs:
            runs = framework.store.list_runs()
            if not runs:
                print("No archived runs found in", framework.store.results_dir)
            for r in runs:
                print(f"{r['run_id']}  {str(r['status']):<22} {','.join(r['ammeters']):<28} most reliable: {r['most_reliable']}")
            return 0
        if args.show:
            print(format_console_summary(framework.store.load_run(args.show), framework.config["analysis"]["statistical_metrics"]))
            return 0
        if args.compare:
            print(json.dumps(framework.store.compare_runs(*args.compare), indent=2))
            return 0

        result = framework.run(args.ammeters)
    except (ConfigError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except RunNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except RuntimeError as exc:  # e.g. an emulator port is already in use
        print(f"Error: {exc}", file=sys.stderr)
        return 3

    print(format_console_summary(result, framework.config["analysis"]["statistical_metrics"]))
    print(f"\nResults saved in: {result['run_dir']}")
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
