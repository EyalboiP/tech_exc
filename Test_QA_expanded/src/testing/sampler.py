"""Timed measurement sampling."""
import logging
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional, Protocol
import threading

from src.utils.config import ConfigError

logger = logging.getLogger(__name__)


class Reader(Protocol):
    def read(self) -> float: ...


@dataclass(frozen=True)
class SamplingPlan:
    count: int
    frequency_hz: float
    duration_s: float


@dataclass
class Sample:
    index: int
    timestamp: float            # wall-clock epoch seconds when the request started
    offset_s: float             # seconds since sampling began
    value: Optional[float]      # amperes; None if the measurement failed
    latency_ms: float
    error: Optional[str] = None  # "ErrorClass: message" for failed measurements

    def to_dict(self) -> Dict:
        return asdict(self)


def resolve_sampling(count: Optional[float], duration_s: Optional[float],
                     frequency_hz: Optional[float]) -> SamplingPlan:
    """
    Combine the three sampling parameters. At least two must be given; the third is
    derived with   duration = count / frequency   (each sample owns one 1/frequency slot).
    If all three are given they must agree (within one sample).
    """
    given = [v is not None for v in (count, duration_s, frequency_hz)]
    if sum(given) < 2:
        raise ConfigError("Sampling needs at least two of: measurements_count, "
                          "total_duration_seconds, sampling_frequency_hz")
    if count is not None and (count < 1 or int(count) != count):
        raise ConfigError(f"measurements_count must be a positive integer (got {count})")
    if duration_s is not None and duration_s <= 0:
        raise ConfigError(f"total_duration_seconds must be > 0 (got {duration_s})")
    if frequency_hz is not None and frequency_hz <= 0:
        raise ConfigError(f"sampling_frequency_hz must be > 0 (got {frequency_hz})")

    if count is None:
        count = max(1, round(duration_s * frequency_hz))
    elif frequency_hz is None:
        frequency_hz = count / duration_s
    elif duration_s is None:
        duration_s = count / frequency_hz
    elif abs(count - duration_s * frequency_hz) >= 1:
        raise ConfigError(
            f"Inconsistent sampling: {count} measurements at {frequency_hz} Hz take "
            f"{count / frequency_hz:.3f}s, not {duration_s}s. Provide only two of the three.")
    count = int(count)
    return SamplingPlan(count=count, frequency_hz=float(frequency_hz), duration_s=count / frequency_hz)


def run_sampling(reader: Reader, plan: SamplingPlan, stop_event: Optional[threading.Event] = None,
                 clock: Callable[[], float] = time.perf_counter,
                 wall_clock: Callable[[], float] = time.time,
                 sleep: Optional[Callable[[float], None]] = None) -> List[Sample]:
    """
    Take plan.count measurements, one every 1/plan.frequency_hz seconds.

    Sample i is scheduled at start + i/frequency (absolute schedule), so a slow reading does
    not shift every later sample (no cumulative drift). A failed reading is recorded as a
    Sample with value=None instead of aborting the run. If stop_event is set the loop
    ends early and the samples collected so far are returned.
    """
    stop_event = stop_event or threading.Event()
    wait = sleep or stop_event.wait
    interval = 1.0 / plan.frequency_hz
    samples: List[Sample] = []
    start = clock()
    for i in range(plan.count):
        delay = start + i * interval - clock()
        if delay > 0:
            wait(delay)
        if stop_event.is_set():
            logger.warning("Sampling interrupted after %d/%d samples", i, plan.count)
            break
        t0 = clock()
        timestamp = wall_clock()
        try:
            value, error = reader.read(), None
        except Exception as exc:  # AmmeterError and anything unexpected: record, keep going
            value, error = None, f"{type(exc).__name__}: {exc}"
            logger.debug("Sample %d failed: %s", i, error)
        t1 = clock()
        samples.append(Sample(index=i, timestamp=timestamp, offset_s=t0 - start, value=value,
                              latency_ms=(t1 - t0) * 1000.0, error=error))
    return samples
