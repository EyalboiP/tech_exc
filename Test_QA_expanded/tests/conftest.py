import socket

import pytest

from src.utils.config import DEFAULT_CONFIG, deep_merge


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("localhost", 0))
        return s.getsockname()[1]


@pytest.fixture
def make_config(tmp_path):
    """Config using free ports, a temp results dir and a fast sampling plan."""
    def _make(**sections):
        base = {
            "testing": {"sampling": {"measurements_count": 10, "sampling_frequency_hz": 100},
                        "timeout_seconds": 1.0},
            "ammeters": {
                "greenlee": {"port": free_port(), "command": "MEASURE_GREENLEE -get_measurement"},
                "entes": {"port": free_port(), "command": "MEASURE_ENTES -get_data"},
                "circutor": {"port": free_port(), "command": "MEASURE_CIRCUTOR -get_measurement"},
            },
            "result_management": {"results_dir": str(tmp_path / "results")},
            "analysis": {"visualization": {"enabled": False}},
        }
        return deep_merge(deep_merge(DEFAULT_CONFIG, base), sections)
    return _make


@pytest.fixture
def write_config(tmp_path):
    import yaml

    def _write(config: dict) -> str:
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(config))
        return str(path)
    return _write
