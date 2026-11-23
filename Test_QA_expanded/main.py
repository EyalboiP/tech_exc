"""Starts the three ammeter emulators, requests one measurement from each, then runs the
full test framework using config/config.yaml.

    python main.py                  # emulators + one demo reading each + full test run
    python main.py --demo-only      # just the emulators and one reading each (the original behaviour)
    python main.py --keep-running   # start the emulators and leave them up until Ctrl+C (for nc / manual testing)
    python main.py --config my.yaml

For more control (CLI flags for counts, frequency, fault simulation, history...) use run_tests.py.
"""
import argparse
import sys
import threading

from Ammeters.client import request_current_from_ammeter
from src.testing.emulators import EmulatorManager
from src.testing.report import format_console_summary
from src.testing.test_framework import AmmeterTestFramework
from src.utils.config import ConfigError, load_config
from src.utils.logger import configure_logging


def demo_requests(config: dict) -> None:
    """One raw request per ammeter, using the commands from the config (README commands)."""
    for name in config["testing"]["ammeters"] or config["ammeters"]:
        cfg = config["ammeters"][name]
        print(f"[{name}]", end=" ")
        try:
            request_current_from_ammeter(cfg["port"], cfg["command"].encode("utf-8"), host=config["testing"]["host"])
        except OSError as exc:
            print(f"request failed: {exc}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config/config.yaml")
    parser.add_argument("--demo-only", action="store_true", help="skip the full test run")
    parser.add_argument("--keep-running", action="store_true",
                        help="start the emulators and keep them running until Ctrl+C")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        configure_logging(config["logging"]["level"])
        names = config["testing"]["ammeters"] or list(config["ammeters"])
        if args.keep_running:
            with EmulatorManager(config, names):
                print("Emulators running - press Ctrl+C to stop.")
                try:
                    threading.Event().wait()
                except KeyboardInterrupt:
                    print("\nStopping emulators.")
            return 0
        if args.demo_only:
            with EmulatorManager(config, names):  # waits until every port is listening (no fixed sleep)
                demo_requests(config)
            return 0

        framework = AmmeterTestFramework(args.config)
        with EmulatorManager(config, names):
            demo_requests(config)
            # Emulators are already up: the framework must not start a second set on the same ports.
            framework.config["testing"]["start_emulators"] = False
            result = framework.run()
    except (ConfigError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(format_console_summary(result, framework.config["analysis"]["statistical_metrics"]))
    print(f"\nResults saved in: {result['run_dir']}")
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
