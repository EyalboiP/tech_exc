import copy

import pytest

from src.utils.config import ConfigError, apply_overrides, load_config, validate_config


def test_shipped_config_is_valid_and_matches_readme():
    config = load_config("config/config.yaml")
    ports = {n: c["port"] for n, c in config["ammeters"].items()}
    assert ports == {"greenlee": 5000, "entes": 5001, "circutor": 5002}
    assert config["ammeters"]["circutor"]["command"] == "MEASURE_CIRCUTOR -get_measurement"


def test_missing_file():
    with pytest.raises(ConfigError, match="not found"):
        load_config("does/not/exist.yaml")


def test_invalid_yaml(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(str(bad))


@pytest.mark.parametrize("mutate,message", [
    (lambda c: c["ammeters"].clear(), "at least one ammeter"),
    (lambda c: c["ammeters"]["entes"].update(port=c["ammeters"]["greenlee"]["port"]), "already used"),
    (lambda c: c["ammeters"]["entes"].update(port="x"), "port"),
    (lambda c: c["ammeters"]["entes"].update(command=""), "command"),
    (lambda c: c["testing"].update(ammeters=["nope"]), "unknown ammeter"),
    (lambda c: c["testing"].update(timeout_seconds=0), "timeout"),
    (lambda c: c["testing"]["sampling"].update(measurements_count=-1), "measurements_count"),
    (lambda c: c["fault_simulation"].update(drop_rate=2), "drop_rate"),
    (lambda c: c["analysis"].update(statistical_metrics=["bogus"]), "unknown metric"),
    (lambda c: c["analysis"]["visualization"].update(plot_types=["pie"]), "unknown type"),
    (lambda c: c["logging"].update(level="LOUD"), "logging.level"),
])
def test_validation_errors(make_config, mutate, message):
    config = copy.deepcopy(make_config())
    mutate(config)
    with pytest.raises(ConfigError, match=message):
        validate_config(config)


def test_overrides_including_explicit_null(make_config):
    config = make_config()
    out = apply_overrides(config, {"testing.sampling.measurements_count": None, "logging.level": "DEBUG"})
    assert out["testing"]["sampling"]["measurements_count"] is None
    assert out["logging"]["level"] == "DEBUG"
    assert config["testing"]["sampling"]["measurements_count"] == 10  # original untouched
