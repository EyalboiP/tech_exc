"""Fault (error) simulation for the ammeter emulators.

The injector decides, per request, whether the emulator should behave normally,
answer slowly, close the connection without answering ("drop"), or answer with
garbage. It is disabled unless at least one rate is > 0.
"""
import random
import threading
from dataclasses import dataclass, fields
from typing import Optional, Tuple

DROP = "drop"
GARBAGE = "garbage"
OK = "ok"


@dataclass
class FaultConfig:
    drop_rate: float = 0.0     # probability of closing the connection with no reply
    garbage_rate: float = 0.0  # probability of replying with a non-numeric payload
    delay_rate: float = 0.0    # probability of delaying the reply
    delay_ms: float = 0.0      # how long a delayed reply is held back
    seed: Optional[int] = None  # makes the fault sequence reproducible

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "FaultConfig":
        data = data or {}
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known - {"enabled", "ammeters"}
        if unknown:
            raise ValueError(f"Unknown fault option(s): {sorted(unknown)}")
        cfg = cls(**{k: v for k, v in data.items() if k in known})
        cfg.validate()
        return cfg

    def validate(self) -> None:
        for name in ("drop_rate", "garbage_rate", "delay_rate"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1 (got {value})")
        if self.drop_rate + self.garbage_rate > 1.0:
            raise ValueError("drop_rate + garbage_rate must not exceed 1")
        if self.delay_ms < 0:
            raise ValueError("delay_ms must be >= 0")

    @property
    def enabled(self) -> bool:
        return (self.drop_rate > 0 or self.garbage_rate > 0
                or (self.delay_rate > 0 and self.delay_ms > 0))


class FaultInjector:
    def __init__(self, config: Optional[FaultConfig] = None):
        self.config = config or FaultConfig()
        self._rng = random.Random(self.config.seed)
        self._lock = threading.Lock()

    def next_action(self) -> Tuple[str, float]:
        """Return (action, delay_seconds) for the next request."""
        cfg = self.config
        if not cfg.enabled:
            return OK, 0.0
        with self._lock:
            delay = cfg.delay_ms / 1000.0 if self._rng.random() < cfg.delay_rate else 0.0
            roll = self._rng.random()
        if roll < cfg.drop_rate:
            return DROP, delay
        if roll < cfg.drop_rate + cfg.garbage_rate:
            return GARBAGE, delay
        return OK, delay
