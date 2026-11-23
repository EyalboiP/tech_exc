import threading

import pytest

from src.testing.sampler import resolve_sampling, run_sampling
from src.utils.config import ConfigError


class FakeClock:
    """Deterministic clock: sleeping just advances time."""
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class ScriptedReader:
    def __init__(self, outcomes, clock=None, cost=0.0):
        self.outcomes, self.clock, self.cost, self.calls = list(outcomes), clock, cost, 0

    def read(self):
        outcome = self.outcomes[self.calls % len(self.outcomes)]
        self.calls += 1
        if self.clock:
            self.clock.now += self.cost
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.mark.parametrize("args,expected", [
    ((10, None, 5), (10, 5.0, 2.0)),        # count + frequency -> duration
    ((None, 4, 5), (20, 5.0, 4.0)),         # duration + frequency -> count
    ((10, 5, None), (10, 2.0, 5.0)),        # count + duration -> frequency
    ((10, 2, 5), (10, 5.0, 2.0)),           # all three, consistent
])
def test_resolve_sampling(args, expected):
    plan = resolve_sampling(*args)
    assert (plan.count, plan.frequency_hz, plan.duration_s) == expected


@pytest.mark.parametrize("args", [
    (10, None, None), (None, None, None), (0, None, 5), (10, -1, None), (10, None, 0),
    (10, 100, 5),            # inconsistent triple
    (2.5, None, 5),          # non-integer count
])
def test_resolve_sampling_rejects_bad_input(args):
    with pytest.raises(ConfigError):
        resolve_sampling(*args)


def test_sampling_schedule_is_drift_free():
    clock = FakeClock()
    reader = ScriptedReader([1.0], clock, cost=0.03)  # each read takes 30 ms of a 100 ms slot
    plan = resolve_sampling(10, None, 10)
    samples = run_sampling(reader, plan, clock=clock, wall_clock=clock, sleep=clock.sleep)
    assert len(samples) == 10
    assert [round(s.offset_s, 6) for s in samples] == [round(i * 0.1, 6) for i in range(10)]
    assert all(abs(s.latency_ms - 30) < 1e-6 for s in samples)


def test_failed_readings_are_recorded_not_raised():
    clock = FakeClock()
    reader = ScriptedReader([1.0, ConnectionError("boom"), 2.0], clock)
    samples = run_sampling(reader, resolve_sampling(6, None, 10), clock=clock, wall_clock=clock, sleep=clock.sleep)
    assert [s.value for s in samples] == [1.0, None, 2.0, 1.0, None, 2.0]
    assert samples[1].error.startswith("ConnectionError")


def test_stop_event_returns_partial_results():
    stop = threading.Event()
    clock = FakeClock()

    class StoppingReader(ScriptedReader):
        def read(self):
            if self.calls == 2:
                stop.set()
            return super().read()

    samples = run_sampling(StoppingReader([1.0], clock), resolve_sampling(10, None, 10), stop,
                           clock=clock, wall_clock=clock, sleep=clock.sleep)
    assert len(samples) == 3
