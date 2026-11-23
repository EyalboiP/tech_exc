"""Starts/stops the ammeter emulators in background threads."""
import logging
import threading
import time
from typing import Dict, List, Optional

from Ammeters.base_ammeter import AmmeterEmulatorBase
from Ammeters.faults import FaultConfig
from Ammeters.registry import AMMETER_REGISTRY
from src.utils.config import ConfigError

logger = logging.getLogger(__name__)


class EmulatorStartupError(RuntimeError):
    pass


def build_fault_configs(config: Dict, names: List[str]) -> Dict[str, Optional[FaultConfig]]:
    """Global `fault_simulation` settings, overridable per ammeter via `ammeters.<name>.faults`."""
    global_cfg = config.get("fault_simulation", {})
    result: Dict[str, Optional[FaultConfig]] = {}
    for index, name in enumerate(names):
        per_ammeter = config["ammeters"][name].get("faults")
        if per_ammeter is not None:
            result[name] = FaultConfig.from_dict(per_ammeter)
        elif global_cfg.get("enabled"):
            cfg = FaultConfig.from_dict(global_cfg)
            if cfg.seed is not None:
                cfg.seed += index  # same seed, but a different (still reproducible) sequence per ammeter
            result[name] = cfg
        else:
            result[name] = None
    return result


class EmulatorManager:
    def __init__(self, config: Dict, names: List[str]):
        self.host = config["testing"]["host"]
        self.startup_timeout = config["testing"]["startup_timeout_seconds"]
        faults = build_fault_configs(config, names)
        self.emulators: Dict[str, AmmeterEmulatorBase] = {}
        self._threads: List[threading.Thread] = []
        for name in names:
            cls = AMMETER_REGISTRY.get(name)
            if cls is None:
                raise ConfigError(
                    f"No emulator class registered for '{name}' (known: {sorted(AMMETER_REGISTRY)}). "
                    "Use testing.start_emulators: false to test an external device.")
            self.emulators[name] = cls(config["ammeters"][name]["port"], host=self.host, faults=faults[name])

    def start(self) -> None:
        for name, emulator in self.emulators.items():
            thread = threading.Thread(target=self._serve, args=(emulator,), name=f"emulator-{name}", daemon=True)
            thread.start()
            self._threads.append(thread)
        deadline = time.monotonic() + self.startup_timeout
        for name, emulator in self.emulators.items():
            remaining = max(deadline - time.monotonic(), 0)
            if not emulator.ready_event.wait(remaining):
                self.stop()
                raise EmulatorStartupError(f"{name} emulator did not start within {self.startup_timeout}s")
            if emulator.startup_error is not None:
                self.stop()
                raise EmulatorStartupError(
                    f"{name} emulator could not listen on port {emulator.port}: {emulator.startup_error}. "
                    "Is another process (or an earlier run) still using it?")

    @staticmethod
    def _serve(emulator: AmmeterEmulatorBase) -> None:
        try:
            emulator.start_server()
        except OSError:
            pass  # recorded in emulator.startup_error and reported by start()

    def stop(self) -> None:
        for emulator in self.emulators.values():
            emulator.stop()
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads.clear()

    def __enter__(self) -> "EmulatorManager":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()
