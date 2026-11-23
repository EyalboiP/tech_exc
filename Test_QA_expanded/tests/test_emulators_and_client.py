import socket

import pytest

from Ammeters.faults import DROP, GARBAGE, OK, FaultConfig, FaultInjector
from src.testing.ammeter_client import AmmeterClient, AmmeterConnectionError, AmmeterProtocolError
from src.testing.emulators import EmulatorManager, EmulatorStartupError

RANGES = {"greenlee": (0.01, 100.0), "entes": (5.0, 200.0), "circutor": (0.0001, 0.1)}


def client_for(config, name, **kw):
    cfg = config["ammeters"][name]
    return AmmeterClient(name, cfg["port"], cfg["command"], timeout=1.0, **kw)


def test_every_emulator_answers_with_a_plausible_current(make_config):
    config = make_config()
    with EmulatorManager(config, list(config["ammeters"])):
        for name, (low, high) in RANGES.items():
            for _ in range(20):
                assert low <= client_for(config, name).read() <= high


def test_unknown_command_gets_an_error_reply_and_server_survives(make_config):
    config = make_config()
    with EmulatorManager(config, ["entes"]):
        port = config["ammeters"]["entes"]["port"]
        bad = AmmeterClient("entes", port, "NOPE")
        with pytest.raises(AmmeterProtocolError, match="unknown command"):
            bad.read()
        # an idle connection that sends nothing must not break it either
        with socket.create_connection(("localhost", port)):
            pass
        assert client_for(config, "entes").read() > 0


def test_connection_refused_is_a_clean_error(make_config):
    config = make_config()  # nothing started
    with pytest.raises(AmmeterConnectionError):
        client_for(config, "greenlee").read()


def test_restart_on_same_port_works(make_config):
    config = make_config()
    for _ in range(2):
        with EmulatorManager(config, ["greenlee"]):
            assert client_for(config, "greenlee").read() > 0


def test_port_in_use_is_reported(make_config):
    config = make_config()
    with socket.socket() as blocker:
        blocker.bind(("localhost", config["ammeters"]["greenlee"]["port"]))
        blocker.listen()
        with pytest.raises(EmulatorStartupError, match="port"):
            EmulatorManager(config, ["greenlee"]).start()


def test_fault_drop_and_garbage_surface_as_protocol_errors(make_config):
    config = make_config(fault_simulation={"enabled": True, "drop_rate": 0.5, "garbage_rate": 0.5, "seed": 3})
    with EmulatorManager(config, ["entes"]):
        messages = set()
        for _ in range(20):
            with pytest.raises(AmmeterProtocolError) as exc:
                client_for(config, "entes").read()
            messages.add("garbage" if "non-numeric" in str(exc.value) else "dropped")
        assert messages == {"garbage", "dropped"}


def test_fault_delay_causes_timeouts(make_config):
    config = make_config(fault_simulation={"enabled": True, "delay_rate": 1.0, "delay_ms": 1500})
    with EmulatorManager(config, ["entes"]):
        with pytest.raises(AmmeterConnectionError, match="timeout"):
            client_for(config, "entes").read()


def test_per_ammeter_fault_override(make_config):
    config = make_config()
    config["ammeters"]["entes"]["faults"] = {"drop_rate": 1.0}
    with EmulatorManager(config, ["entes", "greenlee"]):
        with pytest.raises(AmmeterProtocolError):
            client_for(config, "entes").read()
        assert client_for(config, "greenlee").read() > 0


def test_fault_injector_is_reproducible_and_validated():
    seq = lambda: [FaultInjector(FaultConfig(drop_rate=0.3, garbage_rate=0.3, seed=7)).next_action()[0] for _ in range(1)]
    a = FaultInjector(FaultConfig(drop_rate=0.3, garbage_rate=0.3, seed=7))
    b = FaultInjector(FaultConfig(drop_rate=0.3, garbage_rate=0.3, seed=7))
    assert [a.next_action() for _ in range(50)] == [b.next_action() for _ in range(50)]
    assert FaultInjector().next_action() == (OK, 0.0)
    with pytest.raises(ValueError):
        FaultConfig(drop_rate=0.8, garbage_rate=0.5).validate()
    with pytest.raises(ValueError):
        FaultConfig.from_dict({"typo_rate": 1})
    assert {DROP, GARBAGE, OK} == {"drop", "garbage", "ok"}


def test_retries_mask_transient_failures(make_config):
    config = make_config(fault_simulation={"enabled": True, "drop_rate": 0.5, "seed": 11})
    with EmulatorManager(config, ["entes"]):
        client = client_for(config, "entes", retries=15)
        assert all(client.read() > 0 for _ in range(10))
