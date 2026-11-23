"""Configuration loading, defaults and validation."""
import copy
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]

STAT_METRICS = ("mean", "median", "std", "min", "max", "variance", "cv")
PLOT_TYPES = ("time_series", "histogram", "boxplot")

DEFAULT_CONFIG: Dict[str, Any] = {
    "testing": {
        "host": "localhost",
        "start_emulators": True,      # False -> use emulators that are already running
        "startup_timeout_seconds": 5.0,
        "ammeters": None,             # None -> every ammeter defined under `ammeters:`
        "timeout_seconds": 2.0,       # per-measurement socket timeout
        "retries": 0,                 # extra attempts per measurement (0 keeps error rates honest)
        "sampling": {
            "measurements_count": None,
            "total_duration_seconds": None,
            "sampling_frequency_hz": None,
        },
    },
    "ammeters": {},
    "fault_simulation": {
        "enabled": False,
        "drop_rate": 0.0,
        "garbage_rate": 0.0,
        "delay_rate": 0.0,
        "delay_ms": 0.0,
        "seed": None,
    },
    "analysis": {
        "statistical_metrics": ["mean", "median", "std", "min", "max"],
        "conformance_z_threshold": 4.0,
        "visualization": {"enabled": True, "plot_types": list(PLOT_TYPES)},
    },
    "result_management": {
        "results_dir": "results",
        "save_json": True,
        "save_csv": True,
        "save_sqlite": True,
        "html_report": True,
    },
    "logging": {"level": "INFO"},
}


class ConfigError(ValueError):
    """Raised for a missing, malformed or inconsistent configuration."""


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Return a new dict: `override` merged on top of `base` (recursively)."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def apply_overrides(config: Dict, overrides: Optional[Dict[str, Any]]) -> Dict:
    """Apply {"testing.sampling.measurements_count": 50}-style overrides (a None value sets the key to null)."""
    config = copy.deepcopy(config)
    for dotted, value in (overrides or {}).items():
        node = config
        *parents, leaf = dotted.split(".")
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
    return config


def _resolve_config_path(config_path: str) -> Path:
    path = Path(config_path)
    if path.is_absolute() or path.exists():
        return path
    return PROJECT_ROOT / path  # lets the framework run from any working directory


def load_config(config_path: str = "config/config.yaml", validate: bool = True) -> Dict:
    """Load the YAML file, fill in defaults and (optionally) validate it."""
    path = _resolve_config_path(config_path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with open(path, 'r', encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config file {path} is not valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError(f"Config file {path} must contain a mapping at the top level")
    config = deep_merge(DEFAULT_CONFIG, loaded)
    if validate:
        validate_config(config)
    return config


def _number(value: Any, name: str, minimum: Optional[float] = None, allow_none: bool = False) -> None:
    if value is None and allow_none:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number (got {value!r})")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be >= {minimum} (got {value})")


def validate_config(config: Dict) -> None:
    """Raise ConfigError describing the first problem found."""
    ammeters = config.get("ammeters")
    if not isinstance(ammeters, dict) or not ammeters:
        raise ConfigError("`ammeters` must define at least one ammeter (name -> port, command)")

    ports = {}
    for name, cfg in ammeters.items():
        if not isinstance(cfg, dict):
            raise ConfigError(f"ammeters.{name} must be a mapping with `port` and `command`")
        port = cfg.get("port")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ConfigError(f"ammeters.{name}.port must be an integer 1-65535 (got {port!r})")
        if port in ports:
            raise ConfigError(f"ammeters.{name}.port {port} is already used by '{ports[port]}'")
        ports[port] = name
        command = cfg.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ConfigError(f"ammeters.{name}.command must be a non-empty string")

    testing = config["testing"]
    selected = testing.get("ammeters")
    if selected is not None:
        if not isinstance(selected, list) or not selected:
            raise ConfigError("testing.ammeters must be a non-empty list of ammeter names (or null for all)")
        unknown = [n for n in selected if n not in ammeters]
        if unknown:
            raise ConfigError(f"testing.ammeters references unknown ammeter(s): {unknown}")
    _number(testing.get("timeout_seconds"), "testing.timeout_seconds", 0)
    if testing["timeout_seconds"] <= 0:
        raise ConfigError("testing.timeout_seconds must be > 0")
    _number(testing.get("retries"), "testing.retries", 0)
    _number(testing.get("startup_timeout_seconds"), "testing.startup_timeout_seconds", 0)

    sampling = testing["sampling"]
    _number(sampling.get("measurements_count"), "testing.sampling.measurements_count", 1, allow_none=True)
    _number(sampling.get("total_duration_seconds"), "testing.sampling.total_duration_seconds", 0, allow_none=True)
    _number(sampling.get("sampling_frequency_hz"), "testing.sampling.sampling_frequency_hz", 0, allow_none=True)

    faults = config["fault_simulation"]
    for key in ("drop_rate", "garbage_rate", "delay_rate"):
        _number(faults.get(key), f"fault_simulation.{key}", 0)
        if faults[key] > 1:
            raise ConfigError(f"fault_simulation.{key} must be <= 1 (got {faults[key]})")
    if faults["drop_rate"] + faults["garbage_rate"] > 1:
        raise ConfigError("fault_simulation.drop_rate + garbage_rate must not exceed 1")
    _number(faults.get("delay_ms"), "fault_simulation.delay_ms", 0)

    analysis = config["analysis"]
    metrics = analysis.get("statistical_metrics")
    if not isinstance(metrics, list) or not metrics:
        raise ConfigError("analysis.statistical_metrics must be a non-empty list")
    bad = [m for m in metrics if m not in STAT_METRICS]
    if bad:
        raise ConfigError(f"analysis.statistical_metrics has unknown metric(s) {bad}; allowed: {list(STAT_METRICS)}")
    _number(analysis.get("conformance_z_threshold"), "analysis.conformance_z_threshold", 0)
    plot_types = analysis["visualization"].get("plot_types") or []
    bad = [p for p in plot_types if p not in PLOT_TYPES]
    if bad:
        raise ConfigError(f"analysis.visualization.plot_types has unknown type(s) {bad}; allowed: {list(PLOT_TYPES)}")

    level = str(config["logging"].get("level", "INFO")).upper()
    if level not in logging.getLevelNamesMapping():
        raise ConfigError(f"logging.level '{level}' is not a valid logging level")
    if not config["result_management"].get("results_dir"):
        raise ConfigError("result_management.results_dir must be set")
